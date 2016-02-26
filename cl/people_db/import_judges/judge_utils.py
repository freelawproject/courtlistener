# -*- coding: utf-8 -*-
"""
Created on Wed Feb 17 12:31:34 2016

@author: elliott
"""
from datetime import date
from cl.corpus_importer.import_columbia.parse_opinions import get_court_object
from cl.people_db.models import School
import pandas as pd

GRANULARITY_YEAR = '%Y'
GRANULARITY_MONTH = '%Y-%m'
GRANULARITY_DAY = '%Y-%m-%d'

def process_date(year,month,day):
    """ return date object and accompanying granularity """
    if pd.isnull(year) or year in ['n/a', 'N/A', 'present']:
        pdate = None
        granularity = None
    elif pd.isnull(month):
        pdate = date(int(year),1,1)
        granularity = GRANULARITY_YEAR
    elif pd.isnull(day):
        pdate = date(int(year),int(month),1)
        granularity = GRANULARITY_MONTH
    else:
        pdate = date(int(year),int(month),int(day))
        granularity = GRANULARITY_DAY
    return pdate, granularity
    
def get_court(courtname):    
    courtid = get_court_object(courtname)
    return courtid

def get_school(schoolname):
    school = School.objects.filter(name=schoolname)
    if len(school) == 0:
        return None
    else:
        return school[0]

def get_party(partystr):
    return 'N'   

def get_appointer(appointstr):
    return appointstr

def get_suffix(suffstr):
    suffdict = {'Jr': 'jr',
                'Sr': 'sr',
                'I': '1',
                'II': '2',
                'III': '3',
                'IV': '4'}
    if pd.isnull(suffstr):
        return None
    else:
        return suffdict[suffstr]    
    
racedict =  {'White': 'w',
             'Black': 'b',
             'African American': 'b',
             'African Am.': 'b',
             'American Indian': 'i',
             'Alaska Native': 'i',
             'Asian': 'a',            
             'Asian American': 'a',
             'Asian Am.': 'a',
             'Native Hawaiian':'p',
             'Pacific Islander': 'p',            
             'Pacific Isl.': 'p',        
             'Hispanic': 'h',
             'Latino': 'h'}            

def get_races(str_race):
    if '/' in str_race:
        rawraces = [x.strip() for x in str_race.split('/')]
    else:
        rawraces = [str_race]
    races = []
    for rawrace in rawraces: 
        races.append(racedict[rawrace])
    return races

abadict =  dict([(v,k) for (k,v) in [('ewq', 'Exceptionally Well Qualified'),
        ('wq', 'Well Qualified'),
        ('q', 'Qualified'),
        ('nq', 'Not Qualified'),
        ('nqa', 'Not Qualified By Reason of Age')]])
        
def get_aba(abastr):
    aba = abadict[abastr]
    return aba
    

select_data = pd.read_excel('/vagrant/flp/columbia_data/judges/stateyeardata.xlsx',0)

def get_select(state,year):
    select_dict = {'P': 'e_part',
               'NP': 'e_non_part',
               'G': 'a_gov',
               'L': 'a_legis',
               'M': 'a_gov'
              }
    return 'P'
 
    
 
