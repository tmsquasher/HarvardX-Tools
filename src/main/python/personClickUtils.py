#!/usr/bin/env python 
''' 
Handy derived data and analysis functions for working with person-click 
datasets in Pandas. Most of these functions get passed a person-click 
DataFrame.

This script uses GeoLite data created by MaxMind, available from
http://www.maxmind.com.

Created on September 18, 2013 

@author: tmullaney
'''

import pandas as pd
import numpy as np
import re
import pytz
import datetime
import dateutil.parser
import trackingLogParser
import math

# DERIVED DATA
# Add columns to person-click datasets. Be careful running on very large 
# DataFrames, as these functions can be slow.
def getAgentInfo(df):
    """
    Returns a dataframe with device, operating system, and browser data.
    """
    from ua_parser import user_agent_parser
    # user_agent_parser
    #   module: https://github.com/tobie/ua-parser
    #   install: pip install pyyaml ua-parser
    def getInfo(agent):
        rec = user_agent_parser.Parse(agent)
        return pd.Series({
            'device': rec['device']['family'], # 'Other' = computer
            'os': rec['os']['family'],
            'browser': rec['user_agent']['family']
            })

    return df['agent'].apply(getInfo)

def getIPInfo(df, geolitecity_dat):
    """
    Returns a dataframe with local time and geolocation data.
    """
    import pygeoip
    # pygeoip
    #   module: https://pypi.python.org/pypi/pygeoip/
    #   install: easy_install pygeoip
    #   dataset: http://dev.maxmind.com/geoip/legacy/geolite/ (GeoLiteCity.dat)
    gi4 = pygeoip.GeoIP(geolitecity_dat, pygeoip.MEMORY_CACHE)

    def getInfo(time_ip_tuple):
        ip = time_ip_tuple[1]
        rec = gi4.record_by_addr(ip)

        # calc local time; sometimes the time_zone isn't in the pygeoip record
        t = time_ip_tuple[0]
        if(len(t) > 5 and t[-6:] == '+00:00'): t = t[:-6]
        tz = rec['time_zone']
        dt = dateutil.parser.parse(str(t)).replace(tzinfo=pytz.utc)
        try: local_time = dt.astimezone(pytz.timezone(tz))
        except Exception: local_time = None

        return pd.Series({
            'local_time': local_time,
            'city': rec['city'],
            'country_name': rec['country_name'],
            'country_code': rec['country_code'],
            'latitude': rec['latitude'],
            'longitude': rec['longitude']
            })

    return df[['time', 'ip']].apply(getInfo, axis=1)

def getStartAndEndWeeks(df, course_start_datetime):
    """
    Returns a dataframe with the start week and end week for each
    unique username in a person-click dataset.

    NOTE: Drops all anonymous user events.
    """
    users = df[['actor', 'time']].groupby('actor')
    
    # person-click events are sorted by time, so first() returns the time of the user's first event
    relative_start = pd.to_datetime(users.first().time) - course_start_datetime 
    relative_end = pd.to_datetime(users.last().time) - course_start_datetime
    
    # first week of the course is considered week 0
    def determineWeek(x):
        if x < 0: return math.floor(x / np.timedelta64(1, 'W'))
        else: return math.ceil(x / np.timedelta64(1, 'W')) - 1
    
    return pd.DataFrame({'start_week': relative_start.apply(determineWeek),
                         'end_week': relative_end.apply(determineWeek)})


# DATA INTEGRITY
# Verify completeness/accuracy of a person-click dataset.
def loadPersonClick(personclick_csv, cols=None):
    """
    Full log person-click datasets can be too large for Pandas'
    built-in CSV reader to work properly. This function loads a 
    dataframe in chunks and concatenates instead. You can optionally
    pass a list of column names to limit which columns get read in
    and save memory.
    """
    it = pd.read_csv(personclick_csv, iterator=True, chunksize=1000, usecols=cols)
    return pd.concat([chunk for chunk in it], ignore_index=True)

def getUniqueDiscardPatterns(df_discards):
    """
    Because we discard log items in parsing a person-click dataset,
    we need to justify each pattern we're discarding, and manually
    check the noise. This function returns a dataframe of these
    patterns and the number of occurrences of each.
    """
    def replaceHashes(event_type):
        hashless = re.sub(r'[0-9a-f]{24,32}', '{HASH}', event_type)
        return re.sub(r'(lecture_[0-9]+)|([a-z]+_l[0-9]+(_[a-z]+)+)', '{NONHASH_ID}', hashless) # vert|cond|poll

    return df_discards.event_type.apply(replaceHashes).value_counts()

def countAnonymousUserEvents(df, pct=True):
    """
    When users aren't logged in, logged events don't have usernames.
    This function returns the number of events without usernames.
    """
    n_anonymous = len(df[df.actor.isnull()])
    n_total = len(df)
    return float(n_anonymous) / n_total if pct else n_anonymous

def getAxisLookupFails(df):
    """
    Sometimes courseware events will be logged that can't be found
    in the Course Axes. When this happens, we don't have a meaningful
    'object_name' in the person-click dataset. This function returns
    a dataframe of all lookup fails.
    """
    return df[df.object_name.apply(lambda x: 'Axis Lookup Failed' in str(x))]

def makeVerbExampleTable(df):
    """
    Makes a DataFrame where each type of verb in the dataset gets
    a row, and examples are filled in for the object, result, meta,
    event_type, and event columns.
    """
    ex_cols = ['verb', 'object_name', 'object_type', 'result', 'meta', 'event', 'event_type']
    return df[ex_cols].groupby(df.verb).last()

def makePersonLevel(df):
    """
    Makes a DataFrame where rows are unique usernames, columns are
    verb types, and values are the number of occurrences of each 
    verb type per user. Also includes a column for 'days_active'.
    NOTE: 'df' only needs to have columns for actor, verb, and time.
    """
    # calc days active (rough measure based on UTC)
    user_dates = df[["actor", "time"]]
    user_dates["time"] = pd.to_datetime(user_dates["time"]).apply(lambda x: x.date())
    user_dates = user_dates.groupby("actor").agg(lambda x: len(x.unique()))

    # calc verb counts
    user_verbs = df[["actor", "verb"]].groupby([df["actor"], df["verb"]]).size().reset_index()
    user_verbs = user_verbs.pivot(index="actor", columns="verb", values=0)
    
    result = pd.DataFrame(user_verbs, columns=trackingLogParser.possible_verbs).fillna(0)
    result["days_active"] = user_dates
    
    return result
