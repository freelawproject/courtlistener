# -*- coding: utf-8 -*-

import pandas as pd
import re

from cl.corpus_importer.court_regexes import fd_pairs
from cl.people_db.models import Person, Position, Education, Race, \
    PoliticalAffiliation, Source, ABARating
from cl.people_db.import_judges.judge_utils import get_school, process_date, \
    get_races, get_party, get_suffix, get_aba, get_degree_level, \
    process_date_string


def get_court_object(raw_court):
    for regex, value in fd_pairs:
        if re.search(regex, raw_court):
            return value
    return None

def process_career(career_string):    
    """Extract data from Employment Text Field"""
    
    if pd.isnull(career_string):
        return(None,None,None,None)        
        
    items = re.split('<BR>|;|<br>', career_string)
    
    positions, locations,startyears, endyears = [], [], []
        
    for item in items:
        if item.startswith('Nominated'):
            # this means there was a nomination that didnt pass
            # need to extract this somehow
            return(None,None,None,None)                           
        else:
            itemsplit = re.split("\,+\s+(?=\d)+", item, 1)
        
            if len(itemsplit) > 1:
                A = itemsplit[0].split(',')
                if len(A) == 1:
                    employ_list[i][j].insert(1, None)
                if len(A) == 2:
                    employ_list[i][j][0] = A[0]
                    employ_list[i][j].insert(1, A[1])
                elif len(A) >= 3:
                    position = ",".join(A[:-2])
                    location = A[-2] + "," + A[-1]
                    employ_list[i][j][0] = position
                    employ_list[i][j].insert(1, location)
            else:
                employ_list[i][j].insert(1, None)
                employ_list[i][j].insert(2, None)
    employ_list = [[[None if a == 'None' else a for a in col] for col in row] for row in employ_list]
    print('Employment Text Field list saved as employ_list')
    
    return(positions, locations,startyears, endyears)

# test process career
    
def process_bankrupty_magistrates(career_string):    
    '''Extract data from the Bankruptcy and Magistrate Service Field'''
    
    month_list = ['June','March','January','February','April','May','July','August','September','October','November','December','Fall','Spring']
    bankruptcy_field_pd = wb['Bankruptcy and Magistrate service'].str.split('<BR>|;|<br>', expand=True)
    bankruptcy_array = pd.np.array(bankruptcy_field_pd)
    bankruptcy_list = bankruptcy_array.tolist()
    bankruptcy_list = [[str(a) if a is not str else a for a in row] for row in bankruptcy_list]
    bankruptcy_list = [[None if a is None else re.split("\,+\s+(?=\d)+", a, 1) if not any(
        month in a for month in month_list) else re.split(
        ",+\s+(?=June|March|January|February|April|May|July|August|September|October|November|December|Fall|Spring)+", a, 1)
                        for a in row] for row in bankruptcy_list]
    for i in range(len(bankruptcy_list)):
        for j in range(len(bankruptcy_list[1])):
            if len(bankruptcy_list[i][j]) > 1:
                B = bankruptcy_list[i][j][0].split(',')
                if len(B) == 1:
                    bankruptcy_list[i][j].insert(1, None)
                if len(B) == 2:
                    bankruptcy_list[i][j][0] = B[0]
                    bankruptcy_list[i][j].insert(1, B[1])
                elif len(B) >= 3:
                    position = ",".join(B[:-2])
                    location = B[-2] + "," + B[-1]
                    bankruptcy_list[i][j][0] = position
                    bankruptcy_list[i][j].insert(1, location)
            else:
                bankruptcy_list[i][j].insert(1, None)
                bankruptcy_list[i][j].insert(2, None)
    bankruptcy_list = [[[None if a == 'None' else a for a in col] for col in row] for row in bankruptcy_list]
    print('Bankruptcy and Magistrate Service saved as bankruptcy_list')


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
        print(
        'Warning: ' + item['firstname'] + ' ' + item['lastname'] + ' ' + str(
            date_dob) + ' exists.')
        return

    date_dod, date_granularity_dod = process_date(item['Death year'],
                                                  item['Death month'],
                                                  item['Death day'])

    dod_city = item['Place of Death (City)']
    dod_state = item['Place of Death (State)']
    # if foreign-dead, leave blank for now.
    if len(dod_state) > 2:
        dod_state = ''

    if not pd.isnull(item['midname']):
        if len(item['midname']) == 1:
            item['midname'] = item['midname'] + '.'


    # instantiate Judge object
    person = Person(
            name_first=item['firstname'],
            name_middle=item['midname'],
            name_last=item['lastname'],
            name_suffix=get_suffix(item['suffname']),
            gender=item['gender'],
            fjc_id=item['Judge Identification Number'],
            cl_id=item['cl_id'],

            date_dob=date_dob,
            date_granularity_dob=date_granularity_dob,
            dob_city=dob_city,
            dob_state=dob_state,
            date_dod=date_dod,
            date_granularity_dod=date_granularity_dod,
            dod_city=dod_city,
            dod_state=dod_state
    )

    if not testing:
        person.save()

    listraces = get_races(item['race'])
    races = [Race.objects.get(race=r) for r in listraces]
    for r in races:
        if not testing:
            person.race.add(r)

    prev_politics = None
    # add position items (up to 6 of them)
    for posnum in range(1, 7):
        if posnum > 1:
            pos_str = ' (%s)' % posnum
        else:
            pos_str = ''

        if pd.isnull(item['Court Name' + pos_str]):
            continue
        courtid = get_court_object(item['Court Name' + pos_str])
        if courtid is None:
            raise

        date_nominated = process_date_string(
                item['Nomination Date Senate Executive Journal'])
        date_recess_appointment = process_date_string(
                item['Recess Appointment date'])
        date_referred_to_judicial_committee = process_date_string(
                item['Referral date (referral to Judicial Committee)'])
        date_judicial_committee_action = process_date_string(
                item['Committee action date'])
        date_hearing = process_date_string(item['Hearings'])
        date_confirmation = process_date_string(
                item['Senate Vote Date (Confirmation Date)'])

        # assign start date
        date_start = process_date_string(item['Commission Date' + pos_str])
        if pd.isnull(date_start) and not pd.isnull(date_recess_appointment):
            date_start = date_recess_appointment
        if pd.isnull(date_start):
            # if still no start date, skip
            continue
        date_termination = process_date_string(
                item['Date of Termination' + pos_str])
        date_retirement = process_date_string(
                item['Retirement from Active Service' + pos_str])

        if date_termination is None:
            date_granularity_termination = ''
        else:
            date_granularity_termination = '%Y-%m-%d'


        # assign appointing president
        if not pd.isnull(item['Renominating President name' + pos_str]):
            appointstr = item['Renominating President name' + pos_str]
        else:
            appointstr = item['President name' + pos_str]
        appointer = None
        if appointstr not in ['Assignment', 'Reassignment']:
            names = appointstr.split()
            
            if len(names) == 3:
                first, mid, last = names
            else:
                first, last = names[0], names[-1]
                mid = ''
            appoint_search = Position.objects.filter(person__name_first__iexact=first,
                       person__name_last__iexact=last)
            if len(appoint_search) > 1:
                appoint_search = Position.objects.filter(person__name_first__iexact=first,
                                                   person__name_last__iexact=last,
                                                   person__name_middle__iexact=mid)
            if len(appoint_search) == 0:
                print(names, appoint_search)                   
            if len(appoint_search) > 1:
                print(names, appoint_search)                   
            if len(appoint_search) == 1:
                appointer = appoint_search[0]                

        # senate votes data
        votes = item['Senate vote Ayes/Nays' + pos_str]
        if not pd.isnull(votes):
            votes_yes, votes_no = votes.split('/')
        else:
            votes_yes = None
            votes_no = None
        if item['Senate voice vote' + pos_str] == "Yes":
            voice_vote = True
        else:
            voice_vote = False

        termdict = {'Abolition of Court': 'abolished',
                    'Death': 'ded',
                    'Reassignment': 'other_pos',
                    'Appointment to Another Judicial Position': 'other_pos',
                    'Impeachment & Conviction': 'bad_judge',
                    'Recess Appointment-Not Confirmed': 'recess_not_confirmed',
                    'Resignation': 'resign',
                    'Retirement': 'retire_vol'
                    }
        term_reason = item['Termination specific reason' + pos_str]
        if pd.isnull(term_reason):
            term_reason = ''
        else:
            term_reason = termdict[term_reason]
            


        position = Position(
                person=person,
                court_id=courtid,
                position_type='jud',

                date_nominated=date_nominated,
                date_recess_appointment=date_recess_appointment,
                date_referred_to_judicial_committee=date_referred_to_judicial_committee,
                date_judicial_committee_action=date_judicial_committee_action,
                date_hearing=date_hearing,
                date_confirmation=date_confirmation,
                date_start=date_start,
                date_granularity_start='%Y-%m-%d',
                date_termination=date_termination,
                date_granularity_termination=date_granularity_termination,
                date_retirement=date_retirement,
                
                appointer = appointer,

                voice_vote=voice_vote,
                votes_yes=votes_yes,
                votes_no=votes_no,
                vote_type = 's',
                how_selected='a_pres',
                termination_reason=term_reason
        )

        if not testing:
            position.save()

        # set party
        p = item['Party Affiliation of President' + pos_str]
        if not pd.isnull(p) and p not in ['Assignment', 'Reassignment']:
            party = get_party(item['Party Affiliation of President' + pos_str])
            if prev_politics is None:
                politics = PoliticalAffiliation(
                        person=person,
                        political_party=party,
                        date_start = date_nominated,
                        source='a'
                )
                if not testing:
                    politics.save()
                prev_politics = party
            elif party != prev_politics:
                # account for changing political affiliation
                politics.date_end = date_nominated
                if not testing:
                    politics.save()
                politics = PoliticalAffiliation(
                        person=person,
                        political_party=party,
                        date_start = date_nominated,
                        source='a'
                )
                if not testing:
                    politics.save()
        rating = get_aba(item['ABA Rating' + pos_str])
        if rating is not None:
            nom_year = date_nominated.year
            aba = ABARating(
                    person=person,
                    rating=rating,
                    year_rated=nom_year
            )
            if not testing:
                aba.save()

    # add education items (up to 5 of them)
    for schoolnum in range(1, 6):
        if schoolnum > 1:
            school_str = ' (%s)' % schoolnum
        else:
            school_str = ''

        schoolname = item['Name of School' + school_str]
        if pd.isnull(schoolname):
            continue

        if pd.isnull(item['Degree' + school_str]):
            degs = ['']
        else:
            degs = [x.strip() for x in item['Degree' + school_str].split(';')]
        for degtype in degs:
            deg_level = get_degree_level(degtype)
            degyear = item['Degree year' + school_str]
            try:
                int(degyear)
            except:
                degyear = None
            school = get_school(schoolname)
            if school is not None:
                degree = Education(
                    person=person,
                    school=school,
                    degree_detail=degtype,
                    degree_level=deg_level,
                    degree_year=degyear
                )
                if not testing:
                    degree.save()

    # Non-judicial positions
    #jobs = process_career(item['Employment text field'])
    #for job in jobs:
        

    
    if not pd.isnull(item['Employment text field']):
        notes = item['Employment text field']
        source = Source(
                person=person,
                notes=notes
        )
        if not testing:
            source.save()

    if not pd.isnull(item['Bankruptcy and Magistrate service']):
        notes = item['Bankruptcy and Magistrate service']
        source = Source(
                person=person,
                notes=notes
        )
        if not testing:
            source.save()


