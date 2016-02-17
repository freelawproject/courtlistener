# -*- coding: utf-8 -*-
"""
Methods to extract judges from lists in text files
"""

import re
import string


abblist=["J.","c.","Justice","justice","c.j.", "C.", "c.", "j.", "CJ", 
	 "C", "J", "JJ++", "ARJ++", "Chief", "PRIOR", "cj", "c", "J",
	 "chief", "OF", "Chief Justice", "DISSENT", "Chief-Justice", 
	 "chief justice", "JJ", "JJ.", "++", "FN*","JJ++", "FURTHER", 
	 "C.J.", "PAGE", "DID", "NOT", "SIT", "CONFERENCES", "NO", "SUBMITTED", 
	 "PARTICIPATE", "PARTICIPATION", "ISSUANCE", "CONSULTATION","HIS", "RESUL", 
	 "FURTH", "EVEN", "THOUGH", "ARGUMENT", "AS", "QUALIFIED", "PRESENT", 
	 "MAJORITY", "SPECIALLY", "IN","THE", "CONCURRENCE", "ARGUMENT", "INITIAL", 
	 "CONCURRING", "FINAL", "MAY", "DISSENTING", "OPINION", "DECISION", "CONFERENCE", 
	 "THIS", "ADOPTED", "BUT", "RETIRED", "BEFORE", "CERTIFIED", "SAT", "ORAL", 
	 "RESIGNED", "CASE", "MEMBER", "TIME", "TO", "PREPARATION", "JOINED", "RETIRED", 
	 "ACTIVE", "JUSTICE", "ON", "ORDER", "WHILE", "HE", "ORDER", "CHIEF", "AT", 
	 "PARTICIPATED", "WAS", "ADOPTED", "FELLOWS", "A", "PARTICIPATED", "ALTHOUGH", 
	 "AVAILABLE", "JUSTICE", "AUTHORIZED",  "CONTINUE", "CAPACITY","DIED", "PARTICIPATE"]    

starting_word=["PANEL", "BEFORE", "SITTING:", "SITTING", "PANEL:"]


def parse_judge(line):
    words = line.split()
    for word in words:
        if word not in abblist:
            word=re.sub(",", "",word)
            return word
         

def parse_panel_judges(line):
    if not line:
        return []
    judges = []
    #for line in lines:
     #don't consider emtpy lines
    line=line.replace(",", "")
    line=line.replace(".", "")
    line=line.upper()
    #if not line.split():
    #   continue
    #only consider lines which start with Before
    if (line.split()[0]!=None) & (line.split()[0] not in starting_word):
        judges=judges+[line.split()[0]]
    else:
        line = line.strip(line.split()[0])
        line = ''.join(ch for ch in line if ch not in set(string.punctuation)).strip()
        line = line.replace("AND","")
        #Replaces "and" with whitespace in the string
        line = line.split()
        for i in range(0, len(line)):
            try:
                val = int(line[i])
            except ValueError:
                val=0
                if (line[i] not in abblist) & (line[i] not in judges) :
                    judges=judges+[line[i]]
    return (judges)
