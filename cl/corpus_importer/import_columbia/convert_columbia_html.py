# -*- coding: utf-8 -*-
"""
Created on Wed Jun 15 16:32:17 2016

@author: elliott
"""

import re

def convert_columbia_html(text):
    
    conversions = [('italic','em'),
                   ('block_quote','blockquote'),
                    ('bold','strong'),
                    ('underline','u'),
                    ('strikethrough','strike'),
                    ('superscript','sup')
                    ('subscript','sub')]
    
    for (pattern, replacement) in conversions:
        text = re.sub('<'+pattern+'>', '<'+replacement+'>', text)
        text = re.sub('</'+pattern+'>', '</'+replacement+'>', text)
        
    return text