# -*- coding: utf-8 -*-

import pandas as pd
import re
from datetime import date
from cl.people_db.models import Person, Position, Race, \
    PoliticalAffiliation, GRANULARITY_DAY, GRANULARITY_YEAR

def make_president(item, testing=False):
    """Takes the federal judge data <item> and associates it with a Judge object.
    Returns a Judge object.
    """

    m,d,y = [int(x) for x in item['Born'].split('/')]
    date_dob = date(y,m,d)
    dob_city = item['birth city'].strip()
    dob_state = item['birth state'].strip()
    
    date_dod, dod_city, dod_state = None, '', ''
    if not pd.isnull(item['Died']):
        m,d,y = [int(x) for x in item['Died'].split('/')]
        date_dod = date(y,m,d)     
        dod_city = item['death city'].strip()
        dod_state = item['death state'].strip()
        death_gran = GRANULARITY_DAY
    else:
        death_gran = ''

    if not pd.isnull(item['midname']):
        if len(item['midname']) == 1:
            item['midname'] = item['midname'] + '.'
    
    # instantiate Judge object
    person = Person(
            name_first=item['firstname'],
            name_middle=item['midname'],
            name_last=item['lastname'],
            gender='m',            
            cl_id=item['cl_id'],

            date_dob=date_dob,
            date_granularity_dob=GRANULARITY_DAY,
            dob_city=dob_city,
            dob_state=dob_state,
            date_dod=date_dod,
            date_granularity_dod=death_gran,
            dod_city=dod_city,
            dod_state=dod_state,
            religion=item['Religion']
    )

    if not testing:
        person.save()

    if item['lastname'] == 'Obama':    
        race = Race.objects.get(race='b')
    else:
        race = Race.objects.get(race='w')
    if not testing:
        person.race.add(race)        
    
    party = item['party'].lower()
    politics = PoliticalAffiliation(
            person=person,
            political_party=party,
            source='b'
    )
    if not testing:
        politics.save()

    position = Position(
            person=person,
            position_type='pres',
            date_start=date(item['term_start'],1,1),
            date_granularity_start=GRANULARITY_YEAR,
            date_termination=date(item['term_end'],1,1),
            date_granularity_termination=GRANULARITY_YEAR,
            location_city = 'Washington',
            location_state = 'DC'
    )

    if not testing:
        position.save()

    if not pd.isnull(item['start2']):
            position = Position(
            person=person,
            position_type='pres',
            date_start=date(item['start2'],1,1),
            date_granularity_start=GRANULARITY_YEAR,
            date_termination=date(item['end2'],1,1),
            date_granularity_termination=GRANULARITY_YEAR,
            location_city = 'Washington',
            location_state = 'DC'
        )   
        if not testing:
            position.save()
