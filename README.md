# CCCA
Comedy Central Content Analysis (CCCA)

Quick and dirty scraper to record data from Comedy Central (specifically for The Colbert Report and The Daily Show, but would presumably work for other shows with minor modifications). Scrapes the following information:

 - JSON-encoded episode metadata
 - JSON-encoded clip/video metadata for each episode
 - Raw text transcripts for every clip/video

This is not the cleanest or best-optimized crawler, but should work relatively smoothly. We of course should do some sanity checking (e.g. making sure episodes URLs we couldn't access were just down temporarily).

Operates in 3 main phases:

1. Grab JSON episode metadata for every episode, extracted via the http://www.cc.com/shows/show_name/video-guide page, and save to ./episode-metadata_showname
2. For each episode stored in the metadata files, extract a listing of all video clip URLs for that episode and save as text to ./clip-urls_showname
3. For each url saved to the clip-urls file, extract the JSON metadata and rawtext transcript for each clip, saving metadata to ./clip-metadata_showname and transcripts to ./transcripts/showname/, with each transcript in a separate file.

There's a bit of redundancy here we might be able to avoid, but the weird page oranization on cc.com makes this a little tricky. Either way, this method isn't as fast as it could be, but works.# PythonTutorial
