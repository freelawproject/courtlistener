# -*- coding: utf-8 -*-
"""
Created on Thu Jun 16 14:31:21 2016

@author: elliott
"""

import os
from collections import defaultdict, Counter

os.chdir('/home/elliott/freelawmachine/flp/columbia_data')

file_lists = defaultdict(list)
for line in open('import_columbia_unknown_exceptions2.log'):
    if 'Unknown exception in file' in line:
        i = line.find('opinions/') + len('opinions/')
        j = line.rfind("'")
        currfile = line[i:j]
        
    if 'Error:' in line:
        file_lists[line].append(currfile)
        #print(line)
        
for k, v in file_lists.items():
    for x in v:
        print((x+'\n'),end="", file=open(k[:5]+'.txt','at'))

import re
    
f = open('import_columbia_known_exceptions2.log')

cite_tab = Counter()

courtid_tab = Counter()

currfile = ''
for line in f:
    if 'exception in file' in line:
        i = line.find('opinions/') + len('opinions/')
        j = line.rfind("'")
        currfile = line[i:j]
        court = currfile.split('/documents')[0]

    if 'Failed to get a citation' in line:
        seg = line.split("'")[1]
        
        newseg = re.sub('\d','#',seg)
        #print(newseg)
        #if 'Ct. Sup.' not in newseg:
        #    if 'Ohio App.' not in newseg:
        #        if 'Okla. Cr.' not in newseg:
        cite_tab[newseg] += 1
    
    if 'Failed to find a court ID' in line:
        seg = line.split('"')[1]
        
        courtid_tab[court,seg] += 1


cite_tab.most_common()

courtid_tab.most_common()