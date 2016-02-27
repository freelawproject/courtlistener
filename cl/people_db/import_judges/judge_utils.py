# -*- coding: utf-8 -*-
"""
Created on Wed Feb 17 12:31:34 2016

@author: elliott
"""
from datetime import date
from cl.people_db.models import School, GRANULARITY_YEAR, GRANULARITY_MONTH, GRANULARITY_DAY
import pandas as pd

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
    
def get_school(schoolname):
    
    schools = School.objects.filter(name__iexact=schoolname)
    if len(schools) == 1:
        school = schools[0]
        if school.is_alias_of is not None:
            return school.is_alias_of
        else:
            return school
            
    print('No exact matches: ' + schoolname + '. Running "contains".')
    
    schools = School.objects.filter(name__icontains=schoolname)  
    if len(schools) == 1:
        school = schools[0]
        if school.is_alias_of is not None:
            return school.is_alias_of
        else:
            return school
    if len(schools) > 1:
        print('Multiple school matches:',schoolname,schools)
        return None

    #print('No fuzzy matches: ' + schoolname )

    filterwords = ['college','university','of','law', 'school', 'u']

    normname = schoolname.lower()
    for f in filterwords:
        normname = normname.replace(f,'').strip()
    
    schools = School.objects.filter(name__icontains=normname)  
    if len(schools) == 1:
        school = schools[0]
        if school.is_alias_of is not None:
            return school.is_alias_of
        else:
            return school
    if len(schools) > 1:
        print('Multiple school matches:',normname,schools)
        return None

    return None


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
              
def get_races(str_race):
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
    if '/' in str_race:
        rawraces = [x.strip() for x in str_race.split('/')]
    else:
        rawraces = [str_race]
    races = []
    for rawrace in rawraces: 
        races.append(racedict[rawrace])
    return races
        
def get_aba(abastr):
    abadict =  dict([(v,k) for (k,v) in [('ewq', 'Exceptionally Well Qualified'),
        ('wq', 'Well Qualified'),
        ('q', 'Qualified'),
        ('nq', 'Not Qualified'),
        ('nqa', 'Not Qualified By Reason of Age')]])
    if pd.isnull(abastr):
        return None
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
 
    
 
