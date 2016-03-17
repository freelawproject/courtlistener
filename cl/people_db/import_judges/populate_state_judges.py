# -*- coding: utf-8 -*-

from datetime import date

from cl.corpus_importer.import_columbia.parse_opinions import get_court_object
from cl.people_db.models import Person, Position, Education, Race, PoliticalAffiliation, Source, ABARating
from cl.people_db.import_judges.judge_utils import get_school, process_date, get_select, get_races, get_party, get_appointer, get_suffix

def make_state_judge(item, testing=False):
    """Takes the state judge data <item> and associates it with a Judge object.
    
    Saves the judge to the DB.
    """

    date_dob, date_granularity_dob = process_date(item['birthyear'], 
                                                  item['birthmonth'], 
                                                  item['birthday']) 
    date_dod, date_granularity_dod = process_date(item['deathyear'], 
                                                  item['deathmonth'], 
                                                  item['deathday'])  
    
    if item['firstname'] == '':
        return
    
    check = Person.objects.filter(name_first=item['firstname'], name_last=item['lastname'], date_dob=date_dob)
    if len(check) > 0:
        print('Warning: ' + item['firstname'] + ' ' + item['lastname'] + ' ' + str(date_dob) + ' exists.') 
        person = check[0]          
    else:
        
        person = Person(
            name_first = item['firstname'],
            name_middle = item['midname'],
            name_last = item['lastname'],
            name_suffix = get_suffix(item['suffname']),
            gender = item['gender'],        
            date_dob = date_dob,
            date_granularity_dob = date_granularity_dob,
            date_dod = date_dod,
            date_granularity_dod = date_granularity_dod                         
        )
        
        if not testing:
            person.save()
        
    courtid = get_court_object(item['court'] + ' of ' + item['state'])
    
    if courtid is None:
        raise
  
    # assign start date
    date_start, date_granularity_start = process_date(item['startyear'], 
                                                      item['startmonth'], 
                                                      item['startday'])
    date_termination, date_granularity_termination = process_date(item['endyear'], 
                                                                  item['endmonth'], 
                                                                  item['endday'])    
    
    judgeship = Position(
        person = person,
        court_id = courtid,
        position_type = 'jud',
        date_start = date_start,
        date_granularity_start = date_granularity_start,
        date_termination = date_termination,
        date_granularity_termination = date_granularity_termination,        
        #how_selected = get_select(courtid,item['startyear']),
        termination_reason = item['howended']
    )
    
    if not testing:
        judgeship.save()

    if not pd.isnull(item['college']):
        if ';' in item['college']:
            colls = [x.strip() for x in item['college'].split(';')]
        else:
            colls = [item['college'].strip()]
        for coll in colls:
            school = get_school(coll)
            if school is not None:
                college = Education(
                    person = person,       
                    school = school,
                    degree_level = 'ba',
                )   
                if not testing:    
                    college.save()
    
    if not pd.isnull(item['lawschool']):
        if ';' in item['lawschool']:
            lschools = [x.strip() for x in item['lawschool'].split(';')]
        else:
            lschools = [item['lawschool'].strip()]
        
        for L in lschools:
            lschool = get_school(L)    
            if lschool is not None:
                lawschool = Education(
                    person = person,
                    school = lschool,
                    degree_level = 'jd',
                    )
                if not testing:    
                    lawschool.save()
        
    # iterate through job variables and add to career if applicable
    for jobvar in ['prevjudge','prevprivate','prevpolitician','prevprof',
                   'postjudge', 'postprivate', 'postpolitician', 'postprof']:
        if pd.isnull(item[jobvar]) or item[jobvar] == 0:
            continue
        position_type = None                     
        if 'judge' in jobvar:
            position_type = 'jud'
        elif 'private' in jobvar:
            position_type = 'prac'
        elif 'politician' in jobvar:
            position_type = 'legis'
        elif 'prof' in jobvar:
            position_type = 'prof'            
            
        job_start = None
        job_end = None          
        if 'prev' in jobvar:
            job_start = date_start.year - 1
            job_end = date_start.year - 1
        if 'post' in jobvar:
            if date_termination is None:
                continue
            job_start = date_termination.year + 1
            job_end = date_termination.year + 1    
            
        job = Position(
            person = person,
            position_type = position_type,
            date_start = date(job_start, 1, 1),
            date_granularity_start = '%Y',
            date_termination = date(job_end,1,1),
            date_granularity_termination = '%Y'
        )       
        if not testing:   
            job.save()
    
    if not pd.isnull(item['politics']):
        politics = PoliticalAffiliation(
            person = person,
            political_party = item['politics']
        )  
        if not testing: 
            politics.save()
    
    if not pd.isnull(item['links']):
        links = item['links']
        if ';' in links:
            urls = [x.strip() for x in links.split(';')]
        else:
            urls = [links]
        for url in urls:
            source = Source(
                person = person,
                notes = item['notes']
            )
            if not testing: 
                source.save()                 

#if __name__ == '__main__':
import pandas as pd
import numpy as np
textfields = ['firstname','midname','lastname','gender',
           'howended']
df = pd.read_excel('/vagrant/flp/columbia_data/judges/supreme-court-judgebios-2016-02-27.xlsx', 0)    
for x in textfields:
    df[x] = df[x].replace(np.nan,'',regex=True)
for i, row in df.iterrows():   
    make_state_judge(dict(row), testing=False)

#df = pd.read_excel('/vagrant/flp/columbia_data/judges/iac-judgebios-2016-01-19.xlsx', 0)   
#for i, row in df.iterrows():    
#    make_state_judge(dict(row), testing=True)
