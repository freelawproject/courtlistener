# -*- coding: utf-8 -*-

import re

from cl.corpus_importer.court_regexes import fd_pairs
from cl.people_db.models import Person, Position, Education, Race, PoliticalAffiliation, Source, ABARating
from cl.people_db.import_judges.judge_utils import get_school, process_date, get_races, \
                                                    get_party, get_suffix, get_aba, get_degree_level

def get_court_object(raw_court):
    if '.' in raw_court:
        j = raw_court.find('.')
        raw_court = raw_court[:j]
    if ',' in raw_court:
        j = raw_court.find(',')
        raw_court = raw_court[:j]
    for regex, value in fd_pairs:
        if re.search(regex, raw_court):
            return value
    return None

    
def make_federal_judge(item, testing=False):
    """Takes the federal judge data <item> and associates it with a Judge object.
    Returns a Judge object.
    """        

    date_dob, date_granularity_dob = process_date(item['Birth year'], 
                                                  item['Birth month'], 
                                                  item['Birth day']) 
    
    dob_city = item['Place of Birth (City)']
    dob_state = item['Place of Birth (State)']
    
    check = Person.objects.filter(fjc_id=item['Judge Identification Number'])
    if len(check) > 0:
        print('Warning: ' + item['firstname'] + ' ' + item['lastname'] + ' ' + str(date_dob) + ' exists.')  
        


    date_dod, date_granularity_dod = process_date(item['Death year'], 
                                                  item['Death month'], 
                                                  item['Death day'])                                                    

    dod_city = item['Place of Death (City)']
    dod_state = item['Place of Death (State)']
        
    # instantiate Judge object    
    person = Person(
        name_first = item['firstname'],
        name_middle = item['midname'],
        name_last = item['lastname'],
        name_suffix = get_suffix(item['suffname']),
        gender = item['gender'],        
        fjc_id = item['Judge Identification Number'],
        
        date_dob = date_dob,
        date_granularity_dob = date_granularity_dob,
        dob_city = dob_city,
        dob_state = dob_state,
        date_dod = date_dod,
        date_granularity_dod = date_granularity_dod,                      
        dod_city = dod_city,
        dod_state = dod_state
    )
    
    if not testing:
        person.save()
        
#    listraces = get_races(item['race'])
#    races = [Race(race=r) for r in listraces]
#    for r in races:
#        if not testing:
#            r.save()
#            person.race.add(r)
    
    # add position items (up to 6 of them)   
    for posnum in range(1,7):
        if posnum > 1:
            pos_str = ' (%s)'%posnum
        else:
            pos_str = ''
     
        if pd.isnull(item['Court Name'+pos_str]):
            continue
        courtid = get_court_object(item['Court Name'+pos_str])                        
        if courtid is None:
            raise
        
        date_nominated = item['Nomination Date Senate Executive Journal']
        date_recess_appointment = item['Recess Appointment date']
        date_referred_to_judicial_committee = item['Referral date (referral to Judicial Committee)']
        date_judicial_committee_action = item['Committee action date']
        date_hearing = item['Hearings']
        date_confirmation = item['Senate Vote Date (Confirmation Date)']
        
        # assign start date
        date_start = item['Commission Date'+pos_str]
        date_termination = item['Date of Termination'+pos_str]        
        date_retirement = item['Retirement from Active Service'+pos_str]
    
        date_confirmation = None
        votes_yes = None
        votes_no = None
        
        position = Position(
            person = person,
            court_id = courtid,
            position_type = 'jud',
            
            date_nominated = date_nominated,      
            date_recess_appointment = date_recess_appointment,
            date_referred_to_judicial_committee=date_referred_to_judicial_committee,
            date_judicial_committee_action=date_judicial_committee_action,
            date_hearing=date_hearing,
            date_confirmation = date_confirmation,
            date_start = date_start,
            date_granularity_start = '%Y-%m-%d',
            date_termination = date_termination,
            date_granularity_termination = '%Y-%m-%d',
            date_retirement = date_retirement,
            
            votes_yes = votes_yes,
            votes_no = votes_no,
            how_selected = 'a_pres',
            termination_reason = item['Termination specific reason'+pos_str]
        )
        
        if not testing:
            position.save()

        # set party                
        p = item['Party Affiliation of President'+pos_str]
        if p is not None and p not in ['Assignment','Reassignment']:
            party = get_party(item['Party Affiliation of President'+pos_str])        
            politics = PoliticalAffiliation(
                person = person,
                political_party = party,
                source = 'a'
                )    
            if not testing:    
                politics.save()       
        
        rating = get_aba(item['ABA Rating'+pos_str])
        if rating is not None:
            aba = ABARating(
                person = person,
                rating = rating
            )
            if not testing:
                aba.save()

    # add education items (up to 5 of them)
    for schoolnum in range(1,6):
        if schoolnum  > 1:
            school_str = ' (%s)'%schoolnum
        else:
            school_str = ''
        
        schoolname = item['Name of School'+school_str]
        if pd.isnull(schoolname):
            continue
        degtype = item['Degree'+school_str]        
        deg_level = get_degree_level(degtype)
        degyear = item['Degree year'+school_str]
        school = get_school(schoolname)
        if school is not None:
            degree = Education(
                        person = person,       
                        school = school,
                        degree = degtype,
                        degree_level = deg_level,
                        degree_year = degyear
                    )   
            if not testing:
                degree.save()
     

  
    

#if __name__ == '__main__':
import pandas as pd
import numpy as np
textfields = ['firstname','midname','lastname','gender',
              'Place of Birth (City)','Place of Birth (State)',
              'Place of Death (City)','Place of Death (State)']

df = pd.read_excel('/vagrant/flp/columbia_data/judges/fjc-data.xlsx',0)
for x in textfields:
    df[x] = df[x].replace(np.nan,'',regex=True)

for i, row in df.iterrows():    
    make_federal_judge(dict(row),testing=False)



# test courts
missing_courts = set()  

for i, row in df.iterrows():   
    for posnum in range(1,7):
        if posnum > 1:
            pos_str = ' (%s)'%posnum
        else:
            pos_str = ''
        if pd.isnull(row['Court Name'+pos_str]):
            continue
        courtid = get_court_object(row['Court Name'+pos_str])                        
        if courtid is None:
            missing_courts.add(row['Court Name'+pos_str])