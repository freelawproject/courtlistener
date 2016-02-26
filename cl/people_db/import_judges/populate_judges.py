# -*- coding: utf-8 -*-

from django.utils.timezone import now
from datetime import date

from cl.people_db.models import Person, Position, Education, Race, PoliticalAffiliation, Source, ABARating

from cl.people_db.import_judges.judge_utils import get_court, get_school, process_date, get_select, get_races
from cl.people_db.import_judges.judge_utils import get_party, get_appointer, get_suffix
    
def make_state_judge(item, testing=False):
    """Takes the state judge data <item> and associates it with a Judge object.
    Returns a Judge object.
    """

    date_dob, date_granularity_dob = process_date(item['birthyear'], 
                                                  item['birthmonth'], 
                                                  item['birthday']) 
    date_dod, date_granularity_dod = process_date(item['deathyear'], 
                                                  item['deathmonth'], 
                                                  item['deathday'])  
    
    # instantiate Judge object    
    person = Person(
        date_created=now(),
        date_modified=now(),

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
        
    appointer = None #get_appointer(state,date_appointed)
    predecessor = None # get_predecessor
    courtid = get_court(item['court'])
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
    
    judgeship = Position(
        date_created=now(),
        date_modified=now(),
        person = person,
        appointer = appointer,
        predecessor = predecessor,
        court_id = courtid,
        position_type = 'jud',
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
    
    if not testing:
        judgeship.save()

    school = get_school(item['college'])
    if school is not None:
        college = Education(
            date_created=now(),
            date_modified=now(),
            person = person,       
            school = school,
            degree = 'BA',
            )   
        if not testing:    
            college.save()
    
    lschool = get_school(item['lawschool'])    
    if lschool is not None:
        lawschool = Education(
            date_created=now(),
            date_modified=now(),
            person = person,
            school = lschool,
            degree = 'JD',
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
            position_type = 'judge'
        elif 'private' in jobvar:
            position_type = 'prac'
        elif 'politician' in jobvar:
            position_type = 'pol'
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
            date_created=now(),
            date_modified=now(),
            person = person,
            position_type = position_type,
            date_start = date(job_start,1,1),
            date_granularity_start = '%Y',
            date_termination = date(job_end,1,1),
            date_granularity_termination = '%Y'
        )       
        if not testing:   
            job.save()
    
    if not pd.isnull(item['politics']):
        party = None
        if item['politics'].lower() == 'd':
            party = 'd'
        elif item['politics'].lower() == 'r':
            party = 'r'
        if party is not None:
            politics = PoliticalAffiliation(
                date_created=now(),
                date_modified=now(),
                person = person,
                political_party = party            
                )  
            if not testing: 
                politics.save()
    
    if not pd.isnull(item['links']):
        links = item['links']
        if ';' in links:
            urls = [x.strip() for x in links.split(';')]
        else:
            urls = [links]
        notestr = ''
        for v in ['notes1','notes2','notes3']:
            if not pd.isnull(item[v]):
                notestr = notestr + ' ; ' + item[v].strip()
        if notestr == '':
            notestr = None
        for url in urls:
            source = Source(
            date_created=now(),
            date_modified=now(),
            person = person,
            notes = notestr
            )
            if not testing: 
                source.save()                

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
        date_created=now(),
        date_modified=now(),

        name_first = item['Judge First Name'],
        name_middle = item['Judge Middle Name'],
        name_last = item['Judge Last Name'],
        name_suffix = item['Suffix'],
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
        date_created=now(),
        date_modified=now(),
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
        date_created=now(),
        date_modified=now(),
        person = person,
        school = get_school(item['college']),
        degree = 'BA',
        )    
    college.save()
    
    lawschool = Education(
        date_created=now(),
        date_modified=now(),
        person = person,
        school = get_school(item['lawschool']),
        degree = 'JD',
        )
    lawschool.save()
        
    # iterate through job variables and add to career if applicable
#    for jobvar in ['prevjudge','prevprivate','prevpolitician','prevprof',
#                   'postjudge', 'postprivate', 'postpolitician', 'postprof']:
#        if not item[jobvar]:
#            continue
#        job_type = None                     
#        if 'judge' in jobvar:
#            job_type = 'j'
#        elif 'private' in jobvar:
#            job_type = 'prac'
#        elif 'politician' in jobvar:
#            job_type = 'pol'
#        elif 'prof' in jobvar:
#            job_type = 'prof'            
#            
#        job_start = None
#        job_end = None          
#        if 'prev' in jobvar:
#            job_start = date_start.year - 1
#            job_end = date_start.year - 1
#        if 'post' in jobvar:
#            job_start = date_termination.year + 1
#            job_end = date_termination.year + 1    
#            
#        job = Career(
#            date_created=now(),
#            date_modified=now(),
#            judge = judge,
#            job_type = job_type,
#            date_start = date(job_start,1,1),
#            date_granularity_start = 'Year',
#            date_end = date(job_end,1,1),
#            date_granularity_end = 'Year'
#        )
#        
#        job.save()
    
    party = get_party(item['Party Affiliation of President'])    
    
    if party is not None:
        politics = PoliticalAffiliation(
            date_created=now(),
            date_modified=now(),
            judge = judge,
            political_party = party,
            source = 'a'
            )    
        politics.save()
    
    rating = item['ABA Rating']
    if rating is not None:
        aba = ABARating
            

if __name__ == '__main__':

    import pandas as pd

    # make state judges    
    df = pd.read_excel('/vagrant/flp/columbia_data/judges/supreme-court-judgebios-2016-02-17.xlsx', 0)    
    for i, row in df.iterrows():    
        make_state_judge(dict(row), testing=True)
    
    # make federal judges
    df = df = pd.read_excel('/vagrant/flp/columbia_data/judges/fjc-data.xlsx')
    for i, row in df.iterrows():    
        make_federal_judge(dict(row))