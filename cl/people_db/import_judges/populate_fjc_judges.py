# -*- coding: utf-8 -*-

from django.utils.timezone import now
from datetime import date

from cl.corpus_importer.import_columbia.parse_opinions import get_court_object
from cl.people_db.models import Person, Position, Education, Race, PoliticalAffiliation, Source, ABARating
from cl.people_db.import_judges.judge_utils import get_school, process_date, get_select, get_races,
                                                    get_party, get_appointer, get_suffix, get_aba
    
def make_federal_judge(item):
    """Takes the federal judge data <item> and associates it with a Judge object.
    Returns a Judge object.
    """        

    date_dob, date_granularity_dob = process_date(item['Birth year'], 
                                                  item['Birth monthy'], 
                                                  item['Birth day']) 
    
    dob_city = item['Place of Birth (City)']
    dob_state = item['Place of Birth (State)']
    
    date_dod, date_granularity_dod = process_date(item['Death year'], 
                                                  item['Death month'], 
                                                  item['Death day'])  

    dod_city = item['Place of Death (City)']
    dod_state = item['Place of Death (State)']
    
    listraces = get_races(item['Race or Ethnicity'])
    races = [Race(race=r) for r in listraces]
    
    # instantiate Judge object    
    person = Person(
        name_first = item['Judge First Name'],
        name_middle = item['Judge Middle Name'],
        name_last = item['Judge Last Name'],
        name_suffix = get_suffix(item['Suffix']),
        gender = item['Gender'].lower(),
        race = races,
        fjc_id = item['Judge Identification Number'],
        
        date_dob = date_dob,
        date_granularity_dob = date_granularity_dob,
        dob_city = dob_city,
        dob_state = dob_state,
        date_dod = date_dod,
        date_granularity_dod = date_granularity_dod   ,                      
        dod_city = dod_city,
        dod_state = dod_state
    )
    
    person.save()
        
    appointer = get_appointer(item['President name'])
    predecessor = None # get_predecessor
    courtid = get_court(item['Court Name'])
    date_nominated = None
    date_elected = None
    
    # assign start date
    date_start, date_granularity_start = process_date(item['startyear'], 
                                                      item['startmonth'], 
                                                      item['startday'])
    date_termination, date_granularity_termination = process_date(item['endyear'], 
                                                                  item['endmonth'], 
                                                                  item['endday'])    
    date_retirement, _ = process_date(item['senioryear'], 
                                      item['seniormonth'], 
                                      item['seniorday'])  

    date_confirmation = None
    votes_yes = None
    votes_no = None
    
    position = Position(
        person = person,
        appointer = appointer,
        predecessor = predecessor,
        court_id = courtid,
        date_nominated = date_nominated,
        date_elected = date_elected,
        date_confirmation = date_confirmation,
        date_start = date_start,
        date_granularity_start = date_granularity_start,
        date_termination = date_termination,
        date_granularity_termination = date_granularity_termination,
        date_retirement = date_retirement,
        votes_yes = votes_yes,
        votes_no = votes_no,
        how_selected = get_select(courtid,item['startyear']),
        termination_reason = item['howended']
    )
    
    position.save()

    college = Education(
        person = person,
        school = get_school(item['college']),
        degree = 'BA',
        )    
    college.save()
    
    lawschool = Education(
        person = person,
        school = get_school(item['lawschool']),
        degree = 'JD',
        )
    lawschool.save()
        
    party = get_party(item['Party Affiliation of President'])    
    
    if party is not None:
        politics = PoliticalAffiliation(
            person = person,
            political_party = party,
            source = 'a'
            )    
        politics.save()
    
    rating = get_aba(item['ABA Rating'])
    if rating is not None:
        aba = ABARating(
            person = person,
            rating = rating
        )
        aba.save()

if __name__ == '__main__':
    import pandas as pd
    df = pd.read_excel('/vagrant/flp/columbia_data/judges/fjc-data.xlsx')
    for i, row in df.iterrows():    
        make_federal_judge(dict(row))
