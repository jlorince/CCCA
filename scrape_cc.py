import urllib2 as ul
import json
from bs4 import BeautifulSoup
import datetime
import os
import cPickle
import time

"""
Quick and dirty scraper to record data from Comedy Central (specifically for for The Colbert Report and The Daily Show, but would presumably work for other shows with minor modifications) the following information:

    A: JSON-encoded episode metadata
    B: JSON-encoded clip/video metadata for each episode
    C: Raw text transcripts for every clip/video

This is not the cleanest or best-optimized crawler, but should work relatively smoothly. We of course should do some sanity checking (e.g. making sure episodes URLs we couldn't access were just down temporarily).

Operates in 3 main phases:

    1: Grab JSON episode metadata for every episode, extracted via the http://www.cc.com/shows/show_name/video-guide page, and save to ./episode-metadata_showname
    2: For each episode stored in the metadata files, extract a listing of all video clip URLs for that episode and save as text to ./clip-urls_showname
    3: For each url saved to the clip-urls file, extract the JSON metadata and rawtext transcript for each clip, saving metadata to ./clip-metadata_showname and transcripts to ./transcripts/showname/, with each transcript in a separate file.

There's a bit of redundancy here we might be able to avoid, but the weird page oranization on cc.com makes this a little tricky. Either way, this method isn't as fast as it could be, but works (and given the small number of episodes/clips speed isn't a huge issue).
"""

max_attempts = 10

### Get episode-level metadata
for show in ('the-daily-show-with-jon-stewart','the-colbert-report'):

    filename = 'episode_metadata'+show

    with open(filename,'a') as fout:

        # main page with links to all episodes
        root_url = 'http://www.cc.com/shows/'+show+'/video-guide'
        root_url_text = ul.urlopen(root_url).read()

        # had to do some guesswork to figure this out, but this feed contains the episode urls
        for line in root_url_text.split('\n'):
            if 'triforceManifestFeed' in line:
                feed_info = json.loads(line[line.find('=')+1:].strip()[:-1])
                break
        # and this has the link to the next page (which corresponds to the "load more" button on the UI, I think)
        next_page = feed_info['manifest']['zones']['t2_lc_promo1']['feed']

        # load json and dump to file for each entry in the feed, until we don't have a "next page" any more
        cnt = 0
        while next_page:
            episode_listing = json.loads(ul.urlopen(next_page).read())
            for ep in episode_listing['result']['items']:
                print cnt,ep['title']
                fout.write(json.dumps(ep)+'\n')
                cnt += 1
            next_page = episode_listing['result'].get('nextPageURL')

### Get clip url listing for each episode

for show in ('the-daily-show-with-jon-stewart','the-colbert-report'):

    # in case we've encountered an errror and had to restart, check which episodes we've already processed
    filename = 'clip-urls_'+show
    done = set()
    if os.path.exists(filename):
        with open(filename,'r') as fin:
            for line in fin:
                airDate = line.strip().split()[0]
                done.add(airDate)

    # for each episode we've recorded in the episode-metadata file...
    with open('episode-metadata_'+show,'r') as fin, open(filename,'a') as fout:
        cnt = 0
        for line in fin:

            ep = json.loads(line.strip())
            # we use episode ID and airDate here because, for some reason, a few Colbert episodes don't have episode number info
            try:
                epid = ep['season']['episodeNumber']
            except:
                epid = 'None'
            airDate = ep.get('airDate')

            print cnt,epid,airDate
            cnt += 1

            # if we've already processed this episode, skip to the next one
            if airDate in done:
                continue

            else:
                # simple HTTP error handling loop
                success = False
                attempts = 0
                while (success==False) and (attempts<max_attempts):
                    try:
                        url = ep.get('url')
                        clip_urls = []
                        if url:
                            html = ul.urlopen(url).read()

                            # ditto on the guesswork to figure out where the clip listing for each episode was stored
                            feed_info = None
                            for line in html.split('\n'):
                                if 'triforceManifestFeed' in line:
                                    feed_info = json.loads(line[line.find('=')+1:].strip()[:-1])
                                    break

                            # grab URLs from the relevant feeds:

                            # tier 4 contains the scrollable list of clips (but not all episodes have this)
                            if 't4_lc_promo1' in feed_info['manifest']['zones']:
                                clip_listing = json.loads(ul.urlopen(feed_info['manifest']['zones']['t4_lc_promo1']['feed']).read())['result']['playlist']['videos']
                                clip_urls += [clip['url'] for clip in clip_listing]

                            # tier 2 contains the "featured" (i.e. big) clip for the episode (but again, not all episodes have all this)
                            # this feed actually has the clip metadata we would need, but tier 2 does not, so for now we just record the URLs and grab all the metadata in a separate pass - this is something we could optimize if needed
                            if 't2_lc_promo1' in feed_info['manifest']['zones']:
                                featured_video_url = json.loads(ul.urlopen(feed_info['manifest']['zones']['t2_lc_promo1']['feed']).read())['result'].get('episodeVideoURL')

                                if (featured_video_url != None) and (featured_video_url not in clip_urls):
                                    clip_urls.append(featured_video_url)

                        # now write everything to file, in format:
                        fout.write('\t'.join([airDate,epid]+clip_urls)+'\n')
                        fout.flush()
                        success = True

                    except ul.HTTPError:
                        time.sleep(3)
                        attempts += 1
                        continue

### Get metadata and transcript for each clip

for show in ('the-daily-show-with-jon-stewart','the-colbert-report'):

    # in case we've encountered an errror and had to restart, check which clips we've already processed
    filename = 'clip-metadata_'+show
    done = set()
    if os.path.exists(filename):
        with open(filename,'r') as fin:
            for line in fin:
                url = line.strip().split('\t')[2]
                done.add(url)

    # Each line in our input file has a list of URLs, so iterate over lines, then over URLs
    with open('clip-urls_'+show,'r') as fin, open(filename,'a') as fout:

        for line in fin:
            for url in line.strip().split('\t')[2:]:
                # if we've already processed the clip, skip to the next one
                if url in done:
                    continue
                else:
                    # outer error handling loop for grabbing the metadata
                    success = False
                    attempts = 0
                    while (success==False) and (attempts<max_attempts):
                        try:
                            # open episode URL
                            html = ul.urlopen(url).read()
                            feed_info = None
                            for line in html.split('\n'):
                                if 'triforceManifestFeed' in line:
                                    feed_info = json.loads(line[line.find('=')+1:].strip()[:-1])
                                    break
                            # here we only care about the tier 2 feed, which contains the actual video
                            clip = json.loads(ul.urlopen(feed_info['manifest']['zones']['t2_lc_promo1']['feed']).read())['result']
                            transcript_url = clip['transcriptURL']['url']
                            metadata = clip['video']
                            # we use episode ID and airDate here because, for some reason, a few Colbert episodes don't have episode number info
                            try:
                                epid = metadata['season']['episodeNumber']
                            except:
                                epid = 'None'
                            airDate = metadata.get('airDate')
                            title = metadata.get('title')

                            # inner error handling loop for grabbing the transcript
                            transcript_success = False
                            transcript_attempts = 0
                            print epid,title,url
                            transcript = ''
                            while (transcript_success==False) and (transcript_attempts<max_attempts):
                                # here we just load the transcript from the URL as raw text and dump directly to file
                                try:
                                    transcript = BeautifulSoup(ul.urlopen(clip_url)).findAll('div',{'class':'transcript'})
                                    if transcript:
                                        transcript = transcript[0].text.encode('utf8')
                                    transcript_success = True
                                except ul.HTTPError:
                                    time.sleep(3)
                                    transcript_attempts += 1
                                    continue
                            # even if we had an error, write transcript to file (just blank in the case of error) to facilitate later data cleanup
                             with open('transcripts/'+show+'/'+str(airDate)+'_'+str(epid)+'_'+title,'w') as transcript_file:
                                transcript_file.write(transcript)
                            # now write the metadata to file
                            metadata_txt = json.dumps(metadata)
                            fout.write('\t'.join([str(airDate),str(epid),url,metadata_txt])+'\n')
                            fout.flush()
                            success = True

                        except ul.HTTPError:
                            time.sleep(3)
                            attempts += 1
                            continue



