# -*- coding: utf-8 -*-
"""
Created on Sun Feb 28 13:19:57 2016

@author: elliott
"""

def set_chief(item):
    
    for posnum in range(1,7):
        if posnum > 1:
            pos_str = '(%s)'%posnum
        else:
            pos_str = ''
        chief_start = item['Date of Service as Chief Judge (begin)'+pos_str]
        