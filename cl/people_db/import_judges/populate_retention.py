# -*- coding: utf-8 -*-

from django.utils.timezone import now
from datetime import date

from cl.people_db.models import RetentionEvent

def process_date(year,month,day):
    """
    return date object and accompanying granularity
    """
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
    return None

def get_ret_type(court,retdate):
    return None
    
def make_retention(item):
    """Takes the retention/reelection <item> and associates it with a RetentionEvent object.
    Returns a RetentionEvent object.
    """    
   
    date_retention, date_granularity_retention = process_date(item['year'], 
                                                  item['month'], 
                                                  item['day']) 
    courtid = get_court(item['court'])
    
    try:
        won = item['votes_yes'] > item['votes_no']
    except:
        pass
    
    event = RetentionEvent(
        date_created=now(),
        date_modified=now(),

        retention_type = get_ret_type(courtid,date_retention),
        date_retention = date_retention,
        date_granularity_retention = date_granularity_retention,
        votes_yes = item['votes_yes'],
        votes_no = item['votes_no'],
        unopposed = bool(item['unopposed']),
        won = won        
    )
        
    return event
    
if __name__ == '__main__':

    
    import pandas as pd
    
    df = pd.read_excel('_')
    
    for i, row in df.iterrows():    
        R = make_retention(dict(row))
    