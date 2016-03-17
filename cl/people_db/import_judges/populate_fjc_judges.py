# -*- coding: utf-8 -*-

import re

from cl.corpus_importer.court_regexes import fd_pairs
from cl.people_db.models import Person, Position, Education, Race, PoliticalAffiliation, Source, ABARating
from cl.people_db.import_judges.judge_utils import get_school, process_date, get_races, \
                                                    get_party, get_suffix, get_aba, get_degree_level, \
                                                    process_date_string

def get_court_object(raw_court):
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
    # if foreign-born, leave blank for now.
    if len(dob_state) > 2:
        dob_state = ''
    
    check = Person.objects.filter(fjc_id=item['Judge Identification Number'])
    if len(check) > 0:
        print('Warning: ' + item['firstname'] + ' ' + item['lastname'] + ' ' + str(date_dob) + ' exists.')  
        return


    date_dod, date_granularity_dod = process_date(item['Death year'], 
                                                  item['Death month'], 
                                                  item['Death day'])                                                    

    dod_city = item['Place of Death (City)']
    dod_state = item['Place of Death (State)']
    # if foreign-dead, leave blank for now.
    if len(dod_state) > 2:
        dod_state = ''
        
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
#    races = [Race.objects.get(race=r) for r in listraces]
#    for r in races:
#        if not testing:            
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
        
        date_nominated = process_date_string(item['Nomination Date Senate Executive Journal'])
        date_recess_appointment = process_date_string(item['Recess Appointment date'])
        date_referred_to_judicial_committee = process_date_string(item['Referral date (referral to Judicial Committee)'])
        date_judicial_committee_action = process_date_string(item['Committee action date'])
        date_hearing = process_date_string(item['Hearings'])
        date_confirmation = process_date_string(item['Senate Vote Date (Confirmation Date)'])
        
        # assign start date
        date_start = process_date_string(item['Commission Date'+pos_str])
        if pd.isnull(date_start) and not pd.isnull(date_recess_appointment):
            date_start = date_recess_appointment
        if pd.isnull(date_start):
            # if still no start date, skip
            continue
        date_termination = process_date_string(item['Date of Termination'+pos_str])        
        date_retirement = process_date_string(item['Retirement from Active Service'+pos_str])
        
        if date_termination is None:
            date_granularity_termination = ''
        else:
            date_granularity_termination = '%Y-%m-%d'
    
        votes_yes = None
        votes_no = None
        
        termdict = {'Abolition of Court':'abolished',
                    'Death':'ded',
                    'Reassignment':'other_pos',
                    'Appointment to Another Judicial Position': 'other_pos',
                    'Impeachment & Conviction':'bad_judge',
                    'Recess Appointment-Not Confirmed':'recess_not_confirmed',
                    'Resignation':'resign',
                    'Retirement':'retire_vol'
                    }
        term_reason = item['Termination specific reason'+pos_str]
        if pd.isnull(term_reason):
            term_reason = ''
        else:
            term_reason = termdict[term_reason]
        
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
            date_granularity_termination = date_granularity_termination,
            date_retirement = date_retirement,
            
            votes_yes = votes_yes,
            votes_no = votes_no,
            how_selected = 'a_pres',
            termination_reason = term_reason
        )
        
        if not testing:
            position.save()

        # set party                
        p = item['Party Affiliation of President'+pos_str]
        if not pd.isnull(p) and p not in ['Assignment','Reassignment']:
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
        
        if pd.isnull(item['Degree'+school_str]):
            degs = ['']
        else:
            degs = [x.strip() for x in item['Degree'+school_str].split(';')]
        for degtype in degs:            
            deg_level = get_degree_level(degtype)
            degyear = item['Degree year'+school_str]
            try: 
                int(degyear)
            except:
                degyear = None
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
     
    if not pd.isnull(item['Employment text field']):        
        notes = item['Employment text field']        
        source = Source(
            person = person,
            notes = notes
        )
        if not testing: 
            source.save()  

    if not pd.isnull(item['Bankruptcy and Magistrate service']):        
        notes = item['Bankruptcy and Magistrate service']        
        source = Source(
            person = person,
            notes = notes
        )
        if not testing: 
            source.save() 
  
    

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

