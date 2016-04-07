# -*- coding: utf-8 -*-
"""
Created on Thu Apr  7 16:47:28 2016

@author: elliott
"""

from cl.search.models import OpinionsCited

opinion_list = []


for opinion in opinion_list:
    
    # get list of cited opinions from reviewed courts
    cited = OpinionsCited.objects.filter(citing_opinion=opinion,
                                         cited_opinion.court_id.lower_courts_reviewed
                                         )
    
    # if any of them have the same party names, set link.
    
    # if no matches, run search of lower courts in last 4 years
    
    # check party names
    
    # if unique match, set link
    
    # otherwise, skip
    

    