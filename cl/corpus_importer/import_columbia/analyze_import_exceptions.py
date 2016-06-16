# -*- coding: utf-8 -*-
"""
Created on Thu Jun 16 14:31:21 2016

@author: elliott
"""

from collections import defaultdict

file_lists = defaultdict(list)
for line in open('import_columbia_unknown_exceptions.log'):
    if 'Unknown exception in file' in line:
        i = line.find('opinions/') + len('opinions/')
        j = line.rfind("'")
        currfile = line[i:j]
        
    if 'Error:' in line:
        file_lists[line].append(currfile)
        
for k, v in file_lists.items():
    print((k,v),end="", file=open(k[:100]+'.txt','wt'))

import re
    
f = open('import_columbia_known_exceptions.log')

cite_tab = Counter()

for line in f:
    if 'Failed to get a citation' in line:
        seg = line.split("'")[1]
        
        newseg = re.sub('\d','#',seg)
        #print(newseg)
        if 'Ct. Sup.' not in newseg:
            cite_tab[newseg] += 1
        
cite_tab.most_common()[:100]