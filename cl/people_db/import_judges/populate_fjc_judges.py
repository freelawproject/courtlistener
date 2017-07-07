# -*- coding: utf-8 -*-

import re
from datetime import date

import pandas as pd
from localflavor.us.us_states import STATES_NORMALIZED

from cl.corpus_importer.court_regexes import fd_pairs, fb_pairs
from cl.people_db.import_judges.judge_utils import get_school, process_date, \
    get_races, get_party, get_suffix, get_aba, get_degree_level, \
    process_date_string
from cl.people_db.models import Person, Position, Education, Race, \
    PoliticalAffiliation, ABARating, GRANULARITY_DAY, GRANULARITY_YEAR


def get_fed_court_object(raw_court):
    for regex, value in fd_pairs:
        if re.search(regex, raw_court):
            return value
    return None


def transform_employ(string):
    if pd.isnull(string):
        return [None], [None], [None], [None]
    string_list = re.split('<BR>|;|<br>', string)
    #  separate dates from the rest
    employ_list = [[a] if a is None or a.startswith('Nominated') else re.split("\,+\s+(?=\d)+|\,+\s+(?=\-)", a, 1) for a in string_list]

    #  extract position and location
    for j in range(len(employ_list)):
        if len(employ_list[j]) > 1:
            A = employ_list[j][0].split(',')
            if len(A) == 1:
                employ_list[j].insert(1, None)
            if len(A) == 2:
                employ_list[j][0] = A[0]
                employ_list[j].insert(1, A[1])
            elif len(A) >= 3:
                position = ",".join(A[:-2])
                location = A[-2] + "," + A[-1]
                employ_list[j][0] = position
                employ_list[j].insert(1, location)
        else:
            employ_list[j].insert(1, None)
            employ_list[j].insert(2, None)
    #  extract start dates and end dates from dates
    j = 0
    while j < len(employ_list):
        if employ_list[j][-1] is None:  # in case there are
            employ_list[j].insert(-1, None)
        else:
            c = employ_list[j][:]
            B = c[-1].split(',')
            employ_list[j][-1] = B[0]
            n = len(B)
            for k in range(1, n):
                d = c[:]
                employ_list.insert(j + k, d)
                employ_list[j + k][-1] = B[k]
            tmp_year = employ_list[j].pop()
            if len(tmp_year.split('-')) >= 1:
                if len(tmp_year.split('-')) == 1:
                    employ_list[j].extend([tmp_year, None])
                else:
                    employ_list[j].extend(tmp_year.split('-'))
            else:
                employ_list[j].append(None)
        j += 1
    employ_list = [list(e) for e in zip(*employ_list)]
    position, location, start_year, end_year = employ_list[0],employ_list[1],employ_list[2],employ_list[3]
    return position, location, start_year, end_year


def transform_bankruptcy(string):
    month_list = ['June', 'March', 'January', 'February', 'April', 'May', 'July', 'August', 'September', 'October',
                  'November', 'December', 'Fall', 'Spring']
    month = ['June', 'March', 'January', 'February', 'April', 'May', 'July', 'August', 'September', 'October', 'November',
         'December']
    season = ['Spring', 'Fall']

    if pd.isnull(string):
        return [None], [None], [None], [None]
    if 'Allotment as Circuit Justice' in string:
        return [None], [None], [None], [None]

    string_list = str(string)
    string_list = re.split('<BR>|;|<br>', string_list)
    bankruptcy_list = [None if a is None else re.split("\,+\s+(?=\d)+", a, 1) if not any(
        month in a for month in month_list) else re.split(
        ",+\s+(?=June|March|January|February|April|May|July|August|September|October|November|December|Fall|Spring)+",
        a, 1)
                       for a in string_list]
    #  extract position and location
    for j in range(len(bankruptcy_list)):
        if len(bankruptcy_list[j]) > 1:
            A = bankruptcy_list[j][0].split(',')
            if len(A) == 1:
                bankruptcy_list[j].insert(1, None)
            if len(A) == 2:
                bankruptcy_list[j][0] = A[0]
                bankruptcy_list[j].insert(1, A[1])
            elif len(A) >= 3:
                position = ",".join(A[:-2])
                location = A[-2] + "," + A[-1]
                bankruptcy_list[j][0] = position
                bankruptcy_list[j].insert(1, location)
        else:
            bankruptcy_list[j].insert(1, None)
            bankruptcy_list[j].insert(2, None)
    #  extract dates into start date and end date for each job
    j = 0
    while j < len(bankruptcy_list):
        if bankruptcy_list[j][-1] is None:  # empty cell
            bankruptcy_list[j].insert(-1, None)
        else:
            if any(word in bankruptcy_list[j][-1] for word in month) or bankruptcy_list[j][-1].startswith(
                    '1') or \
                    bankruptcy_list[j][-1].startswith('2'):
                tmp_year = bankruptcy_list[j].pop()
                if len(tmp_year.split('-')) == 1: bankruptcy_list[j].extend([tmp_year, None])
                else: bankruptcy_list[j].extend(tmp_year.split('-'))
            elif any(word in bankruptcy_list[j][-1] for word in season):
                c = bankruptcy_list[j][:]
                B = c[-1].split(',')
                bankruptcy_list[j][-1] = B[0]
                n = len(B)
                for k in range(1, n):
                    d = c[:]
                    bankruptcy_list.insert(j + k, d)
                    bankruptcy_list[j + k][-1] = B[k]
                tmp_year = bankruptcy_list[j].pop()
                if len(tmp_year.split('-')) == 1: bankruptcy_list[j].extend([tmp_year, None])
                else: bankruptcy_list[j].extend(tmp_year.split('-'))
                if len(bankruptcy_list[j]) == 3:
                    bankruptcy_list[j].append(None)
            else: bankruptcy_list[j].append(None)
        j += 1
    bankruptcy_list = [list(e) for e in zip(*bankruptcy_list)]
    position, location, start_year, end_year = bankruptcy_list
    return position, location, start_year, end_year


def add_positions_from_row(item, person, testing, fix_nums=None):
    # add position items (up to 6 of them)
    prev_politics = None
    for posnum in range(1, 7):
        # Save the position if we're running all positions or specifically
        # fixing this one.
        save_this_position = (fix_nums is None or posnum in fix_nums)
        if posnum > 1:
            pos_str = ' (%s)' % posnum
        else:
            pos_str = ''

        if pd.isnull(item['Court Name' + pos_str]):
            continue
        courtid = get_fed_court_object(item['Court Name' + pos_str])
        if courtid is None:
            raise

        date_nominated = process_date_string(
            item['Nomination Date Senate Executive Journal' + pos_str])
        date_recess_appointment = process_date_string(
            item['Recess Appointment date' + pos_str])
        date_referred_to_judicial_committee = process_date_string(
            item['Referral date (referral to Judicial Committee)' + pos_str])
        date_judicial_committee_action = process_date_string(
            item['Committee action date' + pos_str])
        date_hearing = process_date_string(item['Hearings' + pos_str])
        date_confirmation = process_date_string(
            item['Senate Vote Date (Confirmation Date)' + pos_str])

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
            date_granularity_termination = GRANULARITY_DAY

        # check duplicate position
        dupe_search = Position.objects.filter(
            person=person,
            position_type='jud',
            date_start=date_start,
            date_termination=date_termination,
            court_id=courtid,
        )
        if len(dupe_search) > 0:
            print('Duplicate position:', dupe_search)
            continue

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
            appoint_search = Position.objects.filter(
                person__name_first__iexact=first,
                person__name_last__iexact=last)
            if len(appoint_search) > 1:
                appoint_search = Position.objects.filter(
                    person__name_first__iexact=first,
                    person__name_last__iexact=last,
                    person__name_middle__iexact=mid,
                    position_type='pres',
                )
            if len(appoint_search) > 1:
                appoint_search = Position.objects.filter(
                    person__name_first__iexact=first,
                    person__name_last__iexact=last,
                    person__name_middle__iexact=mid,
                    position_type='pres',
                    date_start__lte=date_nominated,
                    date_termination__gte=date_nominated
                )
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
            date_granularity_start=GRANULARITY_DAY,
            date_termination=date_termination,
            date_granularity_termination=date_granularity_termination,
            date_retirement=date_retirement,

            appointer=appointer,

            voice_vote=voice_vote,
            votes_yes=votes_yes,
            votes_no=votes_no,
            vote_type='s',
            how_selected='a_pres',
            termination_reason=term_reason
        )

        if not testing and save_this_position:
            position.save()

        # set party
        p = item['Party Affiliation of President' + pos_str]
        if not pd.isnull(p) and p not in ['Assignment', 'Reassignment']:
            party = get_party(item['Party Affiliation of President' + pos_str])
            if prev_politics is None:
                if pd.isnull(date_nominated):
                    politicsgran = ''
                else:
                    politicsgran = GRANULARITY_DAY
                politics = PoliticalAffiliation(
                    person=person,
                    political_party=party,
                    date_start=date_nominated,
                    date_granularity_start=politicsgran,
                    source='a',
                )
                if not testing and save_this_position:
                    politics.save()
                prev_politics = party
            elif party != prev_politics:
                # account for changing political affiliation
                politics.date_end = date_nominated
                politics.date_granularity_end = GRANULARITY_DAY
                if not testing and save_this_position:
                    politics.save()
                politics = PoliticalAffiliation(
                    person=person,
                    political_party=party,
                    date_start=date_nominated,
                    date_granularity_start=GRANULARITY_DAY,
                    source='a'
                )
                if not testing and save_this_position:
                    politics.save()
        rating = get_aba(item['ABA Rating' + pos_str])
        if rating is not None:
            nom_year = date_nominated.year
            aba = ABARating(
                person=person,
                rating=rating,
                year_rated=nom_year
            )
            if not testing and save_this_position:
                aba.save()


def get_bankruptcy_court(raw_court):
    for regex, value in fb_pairs:
        if re.search(regex, raw_court):
            return value
    return None


def update_bankruptcy_and_magistrate(testing=False):
    # update bankrupcty positions
    positions = Position.object.filter(job_title__icontains='Bankruptcy')
    for position in positions:
        location = position.location
        bcourt = get_bankruptcy_court(location)
        if bcourt is None:
            continue
        position.court_id = bcourt
        position.position_type = 'jud'
        if not testing:
            position.save()

        positions = Position.object.filter(job_title__icontains='Magistrate')
        for position in positions:
            location = position.location
            mcourt = get_fed_court_object(location)
            position.court_id = mcourt
            position.position_type = 'm-jud'
            if not testing:
                position.save()


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
    name = "%s: %s %s %s" % (item['cl_id'], item['firstname'], item['lastname'],
                             str(date_dob))
    fjc_check = Person.objects.filter(fjc_id=item['Judge Identification Number'])
    if len(fjc_check) > 0:
        print ('Warning: %s exists' % name)
        return

    pres_check = Person.objects.filter(name_first=item['firstname'],
                                  name_last=item['lastname'], date_dob=date_dob)

    if not testing:
        print ("Now processing: %s" % name)
    if len(pres_check) > 0:
        print ('%s is a president.' % name)
        person = pres_check[0]
        person.fjc_id = item['Judge Identification Number']

    else:
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
                item['midname'] += '.'

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

    add_positions_from_row(item, person, testing)

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
    titles, locations, startyears, endyears = transform_employ(item['Employment text field'])
    titles2, locations2, startyears2, endyears2 = transform_bankruptcy(item['Bankruptcy and Magistrate service'])
    titles = titles + titles2
    locations = locations + locations2
    startyears = startyears + startyears2
    endyears = endyears + endyears2

    for i in range(len(titles)):
        job_title = titles[i]
        if pd.isnull(job_title) or job_title=='' or job_title.startswith('Nominated'):
            continue
        location = locations[i]
        start_year = startyears[i]
        end_year = endyears[i]

        job_title = job_title.strip()
        if pd.isnull(start_year) or start_year == '':
            #print
            #print(name)
            #print(job_title,location,start_year,end_year)
            #print('No start date.')
            continue
        else:
            try:
                start_year = int(start_year)
            except:
                continue
            date_start = date(start_year,1,1)
            date_start_granularity = GRANULARITY_YEAR
        if not pd.isnull(end_year) and end_year.isdigit():
            end_year = int(end_year)
            date_end = date(end_year,1,1)
            date_end_granularity = GRANULARITY_YEAR
        else:
            date_end = None
            date_end_granularity = ''

        if not pd.isnull(location):
            location = location.strip()
            if ',' in location:
                city, state = [x.strip() for x in location.split(',')]
                org = ''
                if state in STATES_NORMALIZED.values():
                    pass
                elif state.lower() in STATES_NORMALIZED.keys():
                    state = STATES_NORMALIZED[state.lower()]
                else:
                    city, state = '', ''
                    org = location
            else:
                city, state = '', ''
                org = location
             # test for schools and courts
        else:
            city, state, org = '', '', ''

        position = Position(
                person=person,
                job_title=job_title,

                date_start=date_start,
                date_granularity_start=date_start_granularity,
                date_termination=date_end,
                date_granularity_termination=date_end_granularity,

                location_city=city,
                location_state=state,
                organization_name=org
        )
        if not testing:
            try:
                position.save()
            except Exception:
                continue
