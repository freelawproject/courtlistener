# -*- coding: utf-8 -*-
"""
Created on Wed Feb 17 12:31:34 2016

@author: elliott
"""
from datetime import date, datetime
from cl.people_db.models import School, GRANULARITY_YEAR, GRANULARITY_MONTH, GRANULARITY_DAY
import pandas as pd
import re

def process_date(year,month,day):
    """ return date object and accompanying granularity """
    if pd.isnull(year) or year in ['n/a', 'N/A', 'present']:
        pdate = None
        granularity = ''
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

def process_date_string(date_input):
    
    if pd.isnull(date_input):
        return None
    
    date_object = datetime.strptime(date_input, '%m/%d/%Y')
    
    return date_object

from collections import Counter
C = Counter() # for fixing school names.
    
def get_school(schoolname, testing=False):
    "Takes the name of a school from judges data and tries to match to a unique School object."        
    
    if schoolname.isspace():
        return None
        
    schools = School.objects.filter(name__iexact=schoolname)
    if len(schools) == 1:
        school = schools[0]
        if school.is_alias_of is not None:
            return school.is_alias_of
        else:
            return school
            
    #print('No exact matches: ' + schoolname + '. Running "contains".')
    
    schools = School.objects.filter(name__icontains=schoolname)  
    if len(schools) > 1:
        schools = [x for x in schools if not x.is_alias_of]
    if len(schools) == 1:
        school = schools[0]
        if school.is_alias_of is not None:
            #print(schoolname,'matched to',school.is_alias_of)
            return school.is_alias_of
        else:
            #print(schoolname,'matched to',school)
            return school
    if len(schools) > 1:
        #print('Multiple matches:',schoolname,[x.name for x in schools])
        C[schoolname+ ',' + ','.join([x.name for x in schools])] += 1
        return None

    #print('No fuzzy matches: ' + schoolname )

    filterwords = ['college','university','of','law', 'school', 'u', 'the']

    normname = ''
    normwords = schoolname.lower().split()
    for f in normwords:
        if f not in filterwords:
            normname = normname + ' ' + f
    normname = normname.strip()
    
    if normname.isspace():
        print('Fully normed:',schoolname)
        return None
    
    schools = School.objects.filter(name__icontains=normname)  
    if len(schools) == 1:
        school = schools[0]
        if school.is_alias_of is not None:
            #print(schoolname,'matched to',school.is_alias_of)
            return school.is_alias_of
        else:
            #print(schoolname,'matched to',school)
            return school
    if len(schools) > 1:
        #print('Multiple normalized matches:',schoolname,[x.name for x in schools])
        C[schoolname+ ',' + ','.join([x.name for x in schools])] += 1
        return None
    #print('No matches:',schoolname,normname)    
    C[schoolname+',no-matches'] += 1
    return None

def get_degree_level(degstr):
    if pd.isnull(degstr) or degstr == '':
        return ''
    degdict = {'ba': ['ba','ab','bs','bae','barch','bba','bbs','bcs',
                      'bsee','phb','blitt','littb'],
               'aa': ['aa','as', 'aas'],
               'ma': ['ma','ms', 'msc','am', 'mst','mfa','mph','msw','mia','mpa','msed'
                       'mbe','mssp','mcit','mes','mse','mcp','mpa',
                       'mpp','mdiv', 'mls'],               
               'llb': ['llb','bsl','bl'],
               'jd': ['jd'], 
               'llm': ['llm','ml', 'mjs', 'mj'],
               'jsd': ['jsd','sjd'],
               'phd': ['phd','edd','ded','dma','dphil'],     
               'md': ['md','dmd','rn'],
               'mba': ['mba'],
              }
    deg = re.sub(r"[^a-z]+", '', degstr.lower())
    for k in degdict:
        if deg in degdict[k]:
            return k    
    
    if deg.startswith('b'):
        return 'ba'
    if deg.startswith('m'):
        return 'ma'
    print(degstr+' not in degdict.')    
    return ''
               
def get_party(partystr):
    partydict =  dict([(v,k) for (k,v) in [('d', 'Democrat'),
        ('r', 'Republican'),
        ('i', 'Independent'),
        ('g', 'Green'),
        ('l', 'Libertarian'),
        ('f', 'Federalist'),
        ('w', 'Whig'),
        ('j', 'Jeffersonian Republican')]])
    return partydict[partystr]   

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
        return ''
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
             'Pac. Isl.': 'p',
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
 
    
 
