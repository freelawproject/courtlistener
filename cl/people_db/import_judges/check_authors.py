# -*- coding: utf-8 -*-
"""
Created on Wed Apr 20 19:47:49 2016

@author: elliott
"""

from collections import Counter

panels = 0
authors = 0 

string_misses = Counter()
name_misses = Counter()
word_misses = Counter()
court_misses = Counter()
court = None

for line in open('assigning-authors-log.txt','rt'):
    
    if 'Judge string' in line:
        judges = line.split(':')[1].strip()
        continue    
    if 'Panel assigned' in line:
        panels += 1
        continue
    if 'Author assigned' in line:
        authors += 1
        continue
    if 'No match' in line:
        string_misses[court,judges] += 1
        continue
    if 'No judge' in line:
        seg1,seg2 = line[20:].strip().split(',')
        name = seg1[:-1]
        court = seg2[10:-2]
        name_misses[court,name] += 1
        court_misses[court] += 1
        word_misses[name] += 1
        