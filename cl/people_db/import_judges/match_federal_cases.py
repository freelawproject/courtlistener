# -*- coding: utf-8 -*-
"""
Created on Fri Mar 18 18:27:09 2016

@author: elliott
"""

import pandas as pd
from cl.lib.import_lib import find_person
from cl.corpus_importer.import_columbia import find_judges

df = pd.read_csv('document_data_50.sql', sep='\t',header=None)

df = df[[3,4,17]]

df.columns = ['date_filed','court_id','judges']

for i, row in df.iterrows():
    
    if pd.isnull(row.judges):
        continue
    
    judges = find_judges(row.judges)
    
    for judge in judges:
        print(judge)
    
        candidates = find_person(judge, )
