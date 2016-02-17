# -*- coding: utf-8 -*-
"""
Created on Wed Feb 17 12:31:34 2016

@author: elliott
"""
from datetime import date
from cl.corpus_importer.import_columbia.populate_opinions import get_court_object
from cl.search.models import School

def process_date(year,month,day):
    """ return date object and accompanying granularity """
    if year is None:
        pdate = None
        granularity = None
    elif month is None:
        pdate = date(year,1,1)
        granularity = 'Year'
    elif day is None:
        pdate = date(year,month,1)
        granularity = 'Month'
    else:
        pdate = date(year,month,day)
        granularity = 'Day'
    return pdate, granularity
    
def get_court(courtname):    
    courtid = get_court_object(courtname)
    return courtid

def get_school(schoolname):
    school = School.objects.filter(name='schoolname')
    return school


select_dict = {'P': 'e_part',
               'NP': 'e_non_part',
               'G': 'a_gov',
               'L': 'a_legis',
               'M': 'a_gov'
              }

import pandas as pd
select_data = pd.read_csv('/home/elliott/research/datasets/judges/clean/court/stateyeardata.csv')

def get_select(state,year):
    return None
 
    
    
    