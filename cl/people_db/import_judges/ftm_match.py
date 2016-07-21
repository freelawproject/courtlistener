# -*- coding: utf-8 -*-
"""
Created on Wed Jul 20 14:54:04 2016

@author: elliott
"""

import pandas as pd
import requests

from courtid_levels import courtid2statelevel

mike = '2e5862fbdc62562c0758d8a6623887d4'
elliott = 'd254c8e7475dfed1f8b2eb8016506dfc'

base = 'http://api.followthemoney.org/?f-core=1&c-exi=1&gro=c-t-id&APIKey=%s&mode=json' % mike

leveldict = {
    'H': 'J',
    'M': 'K',
    'L': 'D'
}

candidate_eid_lists = {}

for courtid, (state, level) in courtid2statelevel.items():

    qstate = '&s=' + state
    qlevel = '&c-r-ot=' + leveldict[level]

    for year in range(1989, 2017):
        candidate_eid_lists[courtid] = []
        qyear = '&y=' + str(year)
        url = base + qstate + qyear + qlevel  # + qlastname + qlevel
        data = requests.get(url).json()

        if data['records'] == ['No Records']:
            print(courtid, year, 'skipped.')
            continue
        print(courtid, year)

        for item in data['records']:
            name = item['Candidate']['Candidate']
            eid = item['Candidate']['id']

            # add an eid, name, year tuple to this court's list
            candidate_eid_lists[courtid].append((eid, name, year))

pd.to_pickle(candidate_eid_lists, 'candidate_eid_lists.pkl')

judges = pd.read_csv('judges.csv')
judges['date_start'] = pd.to_datetime(judges['date_start'], errors='coerce')
judges['date_end'] = pd.to_datetime(judges['date_end'], errors='coerce')

judgeid2eid = {}
eid2judgeid = {}

for i, row in judges.iterrows():

    startyear = row.date_start.year
    if not pd.isnull(row.date_end):
        endyear = row.date_end.year
    else:
        endyear = None

    judgeid = row.judgeid
    lastname = row.name_last
    courtid = row.courtid
    if courtid not in courtid2statelevel:
        # Limit this to only state courts.
        continue

    judges_in_court = candidate_eid_lists[courtid]

    # check last name
    matches = [j for j in judges_in_court if lastname.lower() in j[1].lower()]

    print("Matched judges in court '%s': %s" % (courtid, matches))

    eids = set(j[0] for j in matches)

    # if a unique match, save to the dictionary
    if len(eids) == 1:
        judgeid2eid[judgeid] = eid
        eid2judgeid[eid] = judgeid

pd.to_pickle(judgeid2eid, 'judgeid2eid.pkl')
pd.to_pickle(judgeid2eid, 'eid2judgeid.pkl')
