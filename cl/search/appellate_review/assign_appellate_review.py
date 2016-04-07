# -*- coding: utf-8 -*-
"""
Created on Thu Apr  7 16:35:29 2016

@author: elliott
"""
import pandas as pd
from cl.search.models import AppellateReview


df = pd.read_excel('filename', 0)

for i, row in df.iterrows():
    
    upper = row.upper_court
    lower = row.lower_court
    
    if not pd.isnull(row.date_start):
        start = row.date_start
    else:
        start = None
        
    if not pd.isnull(row.date_end):
        end = row.date_end
    else:
        end = None
        
    review = AppellateReview(
                upper_court = upper,
                lower_court = lower,
                date_start = start,
                date_end = end)
    
    review.save()
    
    