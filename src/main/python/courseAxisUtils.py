#!/usr/bin/env python 
''' 
Utility functions for working with Course Axis CSV files. 

Created on October 27, 2013 

@author: tmullaney
'''

import json
import urllib2
from time import sleep

def youtubeDuration(youtube_id, delay_secs=0):
    '''
    Returns the duration (in seconds) of a video for a given YouTube ID.
    Uses the YouTube API and attempts to work around undocumented rate 
    limits. 
    '''
    if youtube_id is '': return None
    sleep(delay_secs)

    try:
        url = "http://gdata.youtube.com/feeds/api/videos/" + youtube_id + "?v=2&alt=jsonc"
        data = urllib2.urlopen(url).read().decode("utf-8")
    except Exception, e:
        error = str(e)
        if "504" in error or "403" in error: 
            # rate-limit issue: try again with double timeout
            new_delay = max(1.0, delay_secs * 2.0)
            print "[Rate-limit] <%s> - Trying again with delay: %s" % (youtube_id, str(new_delay))
            return youtube_api_duration(youtube_id, new_delay)
        else:
            print "[Error] <%s> - Unable to get duration.\n%s" % (youtube_id, url)
            return None
    
    d = json.loads(data)
    return d["data"]["duration"]