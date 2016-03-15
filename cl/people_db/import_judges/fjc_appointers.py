# -*- coding: utf-8 -*-
"""
Created on Sun Feb 28 13:19:57 2016

@author: elliott
"""

def set_appointer(item):
    
    for posnum in range(1,7):
        if posnum > 1:
            pos_str = '(%s)'%posnum
        else:
            pos_str = ''
        name = item['President name'+pos_str])
