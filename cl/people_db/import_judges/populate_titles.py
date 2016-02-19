# -*- coding: utf-8 -*-

from django.utils.timezone import now
from datetime import date

from cl.judges.models import Title

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
    
def make_title(item):
    """Takes the chief judge data <item> and associates it with a Title object.
    Returns a Title object.
    """    
   
    date_start, date_granularity_start = process_date(item['startyear'], 
                                                  item['startmonth'], 
                                                  item['startday']) 
                                                  
    date_end, date_granularity_end = process_date(item['startyear'], 
                                                  item['startmonth'], 
                                                  item['startday']) 
    
    title = Title(
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
        
    return title
    
    


if __name__ == '__main__':

    
    import pandas as pd
    
    df = pd.read_excel('_')
    
    for i, row in df.iterrows():    
        R = make_retention(dict(row))
    