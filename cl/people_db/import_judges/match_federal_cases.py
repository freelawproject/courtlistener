# -*- coding: utf-8 -*-
"""
Created on Fri Mar 18 18:27:09 2016

@author: elliott
"""

import pandas as pd
from datetime import datetime as dt
from cl.lib.import_lib import find_person
from cl.corpus_importer.import_columbia.parse_judges import find_judges

#df = pd.read_csv('document_data_5000.sql', sep='\t',header=None)
#df = df[[3,4,17]]
#df.columns = ['date_filed','court_id','judges']
#df.to_csv('/home/elliott/vmware/freelawmachine/flp/columbia_data/judges/fed-judges-test.csv')

df = pd.read_csv('/vagrant/flp/columbia_data/judges/fed-judges-test.csv')

cas = ['ca'+str(n) for n in range(1,12)]

matchcount = 0
panelcount = 0
zerocount = 0

for i, row in df.iterrows():
    #if row.court_id not in cas:
    #    continue
    if pd.isnull(row.judges):
        continue  
    
    judges = find_judges(row.judges)    
    date_filed = dt.strptime(row.date_filed, "%Y-%m-%d")    
    candidates = []
    for judge in judges:        
        candidates.append(find_person(judge, row.court_id, case_date=date_filed))    
    
    candidates = [c for c in candidates if c is not None]
    
    if len(candidates) == 1:
        author = candidates[0]
    if len(candidates) > 1:
        panel = candidates
    
    if len(candidates) == 1:
        matchcount += 1
    if len(candidates) > 1:
        panelcount += 1
    if len(candidates) == 0:
        zerocount += 1
    
        
