# -*- coding: utf-8 -*-
"""
Created on Wed Feb 17 12:31:34 2016

@author: elliott
"""
from datetime import date
from cl.corpus_importer.import_columbia.populate_opinions import get_court_object
from cl.search.models import School

def process_date(year,month,day):
    # return date object and accompanying granularity
    if year is None:
        pdate = None
        granularity = None
    elif month is None:
        pdate = date(year,1,1)
        granularity = 'Year'
    elif day is None:
        pdate = date(year,month,1)
        granularity = 'Month'
    else:
        pdate = date(year,month,day)
        granularity = 'Day'
    return pdate, granularity
    
def get_court(courtname):    
    courtid = get_court_object(courtname)
    return courtid

def get_school(schoolname):
    school = School.objects.filter(name='schoolname')
    return school

select_dict = {
              }

    SELECTION_METHODS = (
        ('e_part', 'Partisan Election'),
        ('e_non_part', 'Non-Partisan Election'),
        ('a_pres', 'Appointment (Governor)'),
        ('a_gov', 'Appointment (President)'),
        ('a_legis', 'Appointment (Legislature)'),
    )
    TERMINATION_REASONS = (
        ('ded', 'Death'),
        ('retire_vol', 'Voluntary Retirement'),
        ('retire_mand', 'Mandatory Retirement'),
        ('resign', 'Resigned'),
        ('other_pos', 'Appointed to Other Judgeship'),
        ('lost', 'Lost Election'),
        ('abolished', 'Court Abolished'),
        ('bad_judge', 'Impeached and Convicted'),
        ('recess_not_confirmed', 'Recess Appointment Not Confirmed'),
    )

def get_select(how_selected):
    return None

def get_end(how_ended):
    return None    
    
    
    