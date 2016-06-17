# -*- coding: utf-8 -*-
"""
Created on Fri Jun 17 13:46:31 2016

@author: elliott
"""

import re

def amendment_count(text):
    
    numbers = list(range(1,11))
    
    ordinals = ['first','second','third','fourth','fifth','sixth',
                'seventh','eighth','ninth','tenth']
    
    romans = ['i','ii','iii','iv','v','vi','vii','viii','ix','x']
    
    normtext = re.sub('[^a-z0-9 ]','',text.lower())
    
    counts = {}
    
    for i,n in enumerate(numbers):
        
        counts[n] = 0
        
        counts[n] += normtext.count(ordinals[i] + ' amendment')
        counts[n] += normtext.count('amendment '+str(n))
        counts[n] += normtext.count('amend '+str(n))
        counts[n] += normtext.count('amendment '+romans[i])
        counts[n] += normtext.count('amend '+romans[i])
    
    return(counts)