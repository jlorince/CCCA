import urllib2 as ul
import json
from bs4 import BeautifulSoup
import datetime
import os
import cPickle
import time
from httplib import BadStatusLine


max_attempts = 10

### Get episode-level metadata
# probably should add some error handling here, too
for show in ('the-daily-show-with-jon-stewart','the-colbert-report'):

    filename = 'data/episode_metadata'+show

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
    filename = 'data/clip-urls_'+show
    done = set()
    if os.path.exists(filename):
        with open(filename,'r') as fin:
            for line in fin:
                airDate = line.strip().split()[0]
                done.add(airDate)

    # for each episode we've recorded in the episode-metadata file...
    with open('data/episode-metadata_'+show,'r') as fin, open(filename,'a') as fout:
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
                        #clip_urls = []
                        fout.write('\t'.join([airDate,epid]+clip_urls)+'\n')
                        fout.flush()
                        success = True

                    except (ul.HTTPError, BadStatusLine):
                        time.sleep(3)
                        attempts += 1
                        continue
                if success == False:
                    fout.write('ERROR LOADING EPISODE URL\n')

### Get metadata and transcript for each clip

for show in ('the-daily-show-with-jon-stewart','the-colbert-report'):

    # in case we've encountered an errror and had to restart, check which clips we've already processed
    filename = 'data/clip-metadata_'+show
    done = set()
    if os.path.exists(filename):
        with open(filename,'r') as fin:
            for line in fin:
                url = line.strip().split('\t')[2]
                done.add(url)

    # Each line in our input file has a list of URLs, so iterate over lines, then over URLs
    cnt = 0
    with open('data/clip-urls_'+show,'r') as fin, open(filename,'a') as fout:

        for line in fin:
            for url in line.strip().split('\t')[2:]:
                cnt += 1
                # if we've already processed the clip, skip to the next one
                if url in done:
                    continue
                else:
                    # simple error handling loop
                    success = False
                    attempts = 0
                    while (success==False) and (attempts<max_attempts):
                        try:
                            # open episode URL
                            if url:
                                html = ul.urlopen(url).read()
                            else:
                                break
                            feed_info = None
                            for _line in html.split('\n'):
                                if 'triforceManifestFeed' in _line:
                                    feed_info = json.loads(_line[_line.find('=')+1:].strip()[:-1])
                                    break
                            # kludge - sometimes we successfully load the URL, but don't find the feed??
                            if not feed_info:
                                print 'no feed_info?'
                                time.sleep(3)
                                continue

                            # here we only care about the tier 2 feed, which contains the actual video
                            clip = json.loads(ul.urlopen(feed_info['manifest']['zones']['t2_lc_promo1']['feed']).read())['result']
                            metadata = clip['video']
                            # we use episode ID and airDate here because, for some reason, a few Colbert episodes don't have episode number info
                            try:
                                epid = metadata['season']['episodeNumber']
                            except:
                                epid = 'None'
                            airDate = metadata.get('airDate')
                            title = metadata.get('title').replace('/','-')

                            transcript = BeautifulSoup(html).findAll('div',{'class':'transcript'})
                            if transcript:
                                transcript = transcript[0].text.encode('utf8')
                            else:
                                transcript = ''
                            # even if we had an error, write transcript to file (just blank in the case of error) to facilitate later data cleanup
                            with open('data/transcripts/'+show+'/'+str(airDate)+'_'+str(epid)+'_'+title,'w') as transcript_file:
                                transcript_file.write(transcript)

                            print cnt,epid,title,url

                            # now write the metadata to file
                            metadata_txt = json.dumps(metadata)
                            fout.write('\t'.join([str(airDate),str(epid),url,metadata_txt])+'\n')
                            fout.flush()
                            success = True

                        except  (ul.HTTPError, BadStatusLine):
                            time.sleep(3)
                            attempts += 1
                            continue



