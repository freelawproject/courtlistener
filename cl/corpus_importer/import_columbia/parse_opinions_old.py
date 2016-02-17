# -*- coding: utf-8 -*-
"""Functions to parse Court data in XML format and write to csv"""
import xml.etree.cElementTree as ET
import re
from glob import glob
from collections import Counter, defaultdict
from lxml import html
from random import shuffle
import os
import sys
import pickle
import geonamescache

# sys.path.append("/Users/divyasingh/Dropbox/ash-naidu/court-listener")
from regexes_columbia import state_pairs, special_regexes, folderdict
from parse_dates import parseDates
from parse_judges import parseJudges, parsePanelJudges

skipels = set(['center','italic','bold', 'block_quote', 'underline',
               'page_number', 'opinion', 'citation_line','strikethrough',
               'superscript','heading', 'superscript','subscript','table', 'img',
               'html', 'cross_reference'])

listels = set(['cross_reference', 'footnote_body', 'footnote_number',
               'footnote_reference', 'opinion_text', 'opinion_byline',
               'dissent_byline','dissent_text',
               'concurrence_byline','concurrence_text'
               ])
seen = listels | set([
        "court","subcourt","panel",'posture', 'citation',
               'syllabus', 'attorneys', 'hearing_date', 'date',
               "report", 'reporter_caption', 'caption','docket','unpublished', 'body'])
foot=set(['footnote_body', 'footnote_number', 'footnote_reference'])
#So this works, yay.
class CaseNameTweaker(object):
    def __init__(self):
        acros = [u'a.g.p.', u'c.d.c.', u'c.i.a.', u'd.o.c.', u'e.e.o.c.',
                 u'e.p.a.', u'f.b.i.', u'f.c.c.', u'f.d.i.c.', u'f.s.b.',
                 u'f.t.c.', u'i.c.c.', u'i.n.s.', u'i.r.s.', u'n.a.a.c.p.',
                 u'n.l.r.b.', u'p.l.c.', u's.e.c.', u's.p.a.', u's.r.l.',
                 u'u.s.', u'u.s.a.', u'u.s.e.e.o.c.', u'u.s.e.p.a.']
        acros_sans_dots = [acro.replace(u'.', u'') for acro in acros]
        # corp_acros = ['L.L.C.', 'L.L.L.P.', 'L.L.P.', 'L.P.', 'P.A.', 'P.C.',
        #              'P.L.L.C.', ]
        # corp_acros_sans_dots = [acro.replace('.', '') for acro in corp_acros]
        common_names = [u'state', u'people', u'smith', u'johnson']
        ags = [u'Akerman', u'Ashcroft', u'Barr', u'Bates', u'Bell', u'Berrien',
               u'Biddle', u'Black', u'Bonaparte', u'Bork', u'Bradford',
               u'Breckinridge', u'Brewster', u'Brownell', u'Butler',
               u'Civiletti', u'Clark', u'Clement', u'Clifford', u'Crittenden',
               u'Cummings', u'Cushing', u'Daugherty', u'Devens', u'Evarts',
               u'Filip', u'Garland', u'Gerson', u'Gilpin', u'Gonzales',
               u'Gregory', u'Griggs', u'Grundy', u'Harmon', u'Hoar', u'Holder',
               u'Jackson', u'Johnson', u'Katzenbach', u'Keisler', u'Kennedy',
               u'Kleindienst', u'Knox', u'Lee', u'Legaré', u'Levi', u'Lincoln',
               u'Lynch', u'MacVeagh', u'Mason', u'McGranery', u'McGrath',
               u'McKenna', u'McReynolds', u'Meese', u'Miller', u'Mitchell',
               u'Moody', u'Mukasey', u'Murphy', u'Nelson', u'Olney', u'Palmer',
               u'Pierrepont', u'Pinkney', u'Randolph', u'Reno', u'Richardson',
               u'Rodney', u'Rogers', u'Rush', u'Sargent', u'Saxbe', u'Smith',
               u'Speed', u'Stanbery', u'Stanton', u'Stone', u'Taft', u'Taney',
               u'Thornburgh', u'Toucey', u'Wickersham', u'Williams', u'Wirt']
        # self.corp_acros = corp_acros + corp_acros_sans_dots
        self.corp_identifiers = [u'Co.', u'Corp.', u'Inc.', u'Ltd.']
        bad_words = acros + acros_sans_dots + common_names + ags + \
            self.make_geographies_list()
        self.bad_words = [s.lower() for s in bad_words]
        super(CaseNameTweaker, self).__init__() 
    @staticmethod
    def make_geographies_list():
        """Make a flat list of cities, counties and states that we can exclude
        from short names.
        """
        geonames = geonamescache.GeonamesCache()
        # Make a list of cities with big populations.
        cities = [v[u'name'] for v in
                  geonames.get_cities().values() if (
                      v[u'countrycode'] == u'US' and
                      v[u'population'] > 150000
                  )]
        counties = [v[u'name'] for v in geonames.get_us_counties()]
        states = [v[u'name'] for v in geonames.get_us_states().values()]
        return cities + counties + states
    def make_case_name_short(self, s):
        """Creates short case names where obvious ones can easily be made."""
        parts = [part.strip().split() for part in s.split(u' v. ')]
        if len(parts) == 1:
            # No v.
            if s.lower().startswith(u'in re'):
                # Starts with 'in re'
                # In re Lissner --> In re Lissner
                return s
            if s.lower().startswith(u'matter of'):
                # Starts with 'matter of' --> [['matter', 'of', 'lissner']]
                return u'In re %s' % parts[0][2]
        elif len(parts) == 2:
            # X v. Y --> [['X'], ['Y']]
            # X Y Z v. A B --> [['X', 'Y', 'Z'], ['A', 'B']]
            if len(parts[0]) == 1:
                if parts[0][0].lower() not in self.bad_words:
                    # Simple case: Langley v. Google
                    return parts[0][0]
                elif len(parts[1]) == 1:
                    # Plaintiff was a bad_word. Try the defendant.
                    # Dallas v. Lissner
                    if parts[1][0].lower() not in self.bad_words:
                        return parts[1][0]
            elif len(parts[0]) > 1:
                # Plaintiff part is longer than a single word, focus on the
                # defendant.
                if len(parts[1]) == 1:
                    # If the defendant is a single word.
                    if parts[1][0].lower() not in self.bad_words:
                        # That's not a bad word.
                        return parts[1][0]
        # More than 1 instance of v. or otherwise no matches --> Give up.
        return u''
      
def textFromElements(tree,num):
    """takes in an Element Tree and a list/set of elements and
        returns the text of the elements as a list of dictionaries"""
    texts = defaultdict(list)
    texts["fileNum"] = num
    root=tree.getroot()
    for child in root.iter():
        if child.tag in skipels:
            continue
        #print child.tag
        l = ET.tostring(child)
        l=l.decode("utf-8") 
        #ignore tags inside of the tag, such as <center> and <italic>
        text =  re.sub(r'<.*?>', ' ', l)
        #replaces tags with spaces
        text = text.strip()
        if child.tag not in seen:
            seen.add(child.tag)
            print( '***'+child.tag, num)
            #print( text)
        texts[child.tag].append(text)
    texts.default_factory = lambda: None
    return(texts)

# def getOpinion(tree, string):
#     """takes in opinion text and returns the text in proper format"""
#     text=""
#     footnotes=""
#     root=tree.getroot()
#     count=1
#     for root in root.iter():
#         if (root.tag=='footnote_body'):
#             temp=ET.tostring(root)
#             temp=temp.decode("utf-8")
#             temp=re.sub(r'<.*?>', ' ', temp)
#             temp=temp.strip()
#             temp=temp.replace("\n", " ")
#             temp=re.sub(r'\[fn.*?\]', " ", temp)
#             footnotes=footnotes+str(count)+'. '+temp
#             count=count+1
#         if root.tag==string:
#             for child in root:
#                 if child.tag=='cross_reference':
#                     continue
#                 if child.tag=='footnote_body':
#                     continue
#                 else:
#                     l = ET.tostring(child)
#                     l=l.decode("utf-8")
#                     t =  re.sub(r'<.*?>', ' ', l)
#                     t=re.sub(r'\[fn.*?\]', " ", t)
#                     t=re.sub(r'\[.*\]', " ", t)
#                     t=t.strip()
#                     text=text+t
#     text=text+'\n\n NOTES \n\n'+footnotes
#     return text

def getOpinions(tree, string):
    """grabs full xml opinion texts from an opinion node"""
    texts = []
    root = tree.getroot()
    for root in root.iter():
        if root.tag == string:
            text = ET.tostring(root).decode('utf-8')
            texts.append(text)
    return texts
  
def getAttorneys(text):
    #Returns list of attorneys for the case
    attorneys=" "
    line="".join(str(x) for x in text)
    line=re.sub(r'<.*?>', ' ', line)
    textsplit=line.split()
    for i in range(0, len(textsplit)):
        if textsplit[i][-1]==',':
            attorneys=attorneys+textsplit[i][:-1]+', '
    return attorneys
  
def get_court_object(newdict,subsub):
    #get court code from string
    courtname =newdict['court']
    if courtname is None:
        print ('no court name:')
        print (courtname)# + 'not found'
        return None
    #continue  
    courtname="".join(str(x) for x in courtname)  
    if '.' in courtname:
        j = courtname.find('.')
        courtname = courtname[:j]
        subcourtname = courtname[j+1:].strip()
    if ',' in courtname:
        j = courtname.find(',')
        courtname = courtname[:j]
        subcourtname = courtname[j+1:].strip()                    
    for regex, value in state_pairs:
        if re.search(regex, courtname):
            return value
    if subsub in special_regexes:
        for regex, value in special_regexes:
            if re.search(regex, courtname):
                return value
          
def getRepcitation(tree):
    """returns the correct format for reporter_citation=casename"""
    root=tree.getroot()
    for root in root.iter():
        if root.tag!='reporter_caption':
            continue
        else:
            temp = ET.tostring(root)
            temp=temp.decode("utf-8")
            temp = re.sub(r'</?citation.*>', '', temp)
            temp=re.sub(r'<.*?>', ' ', temp)
            temp=temp.strip()
    return temp
  
def get(num=None):
    """
    Returns court data parsed from XML files.

    :param num: The maximumum number of files to grab data from. If None, will return data from all files.
    """
    # e.g., data/usb/alabama/court_opinions/documents/*.xml
    # folders = glob('/Users/divyasingh/Dropbox/ash-naidu/court-listener/maine/')
    folders = glob('/Users/Jeff/Dropbox/ash-naidu/court-listener/maine')
    shuffle(folders)
    for folder in folders:
        subfolders = glob(folder + '/*')
        for subfolder in subfolders:
            print (subfolder)
            global casedata
            casedata=[]
            subsub = subfolder[9:]   # this is the first part of the file path
            #courtcode = subfolder.split('/')[-1]
            files = glob(subfolder + '/documents/*xml')
            shuffle(files)
            #get the data
            count=0
            for f in files:
                d={}
                filenum = f.split('/')[-1][:-4]
                #splits by '/' and from the last word removes .xml
                try:
                    tree = ET.parse(f)
                    global newdict
                    newdict = textFromElements(tree,filenum)
                except ET.ParseError as e:
                    print (e)
                    #print (f)
                    continue
                # get courtid, opinion_text, dissent_text
                d['filenum']=filenum
                d['dissent_byline']=None
                if subsub!=None:
                    d['courtid'] = get_court_object(newdict,subsub)
                if newdict['opinion_byline']!=None:
                    d['opinion_byline'] = parseJudges(newdict['opinion_byline'])
                if newdict['dissent_byline']!=None:
                    d['dissent_byline'] = parseJudges(newdict['dissent_byline'])
                if newdict['panel']!=None:
                    d['panel'] = parsePanelJudges(newdict['panel'])
                #d['concurrenc_judges']=d['panel'].difference(d['dissent_judge'])
                if newdict['date']!=None:
                    if newdict['hearing_date']!=None:
                        temp=newdict['date']+newdict['hearing_date']
                        d['dates'] = parseDates(temp)
                    else:
                        d['dates']=parseDates(newdict['date'])
                if newdict['posture']!=None:
                    d['posture'] = newdict['posture']
                if newdict['caption']!=None:
                    d['casename_full'] = newdict['caption']
                    d['casename_full']="".join(str(x) for x in d['casename_full'])
                if newdict['reporter_caption']!=None:
                    d['casename'] = getRepcitation(tree)
                    shortener = CaseNameTweaker()
                d['casename_short'] = shortener.make_case_name_short(d['casename'])
                if newdict['docket']!=None:
                    d['docket'] = newdict['docket']
                if newdict['citation']!=None:
                    d['citation'] = newdict['citation']
                if newdict['opinion_text']!=None:
                    d['opinion_text']=getOpinions(tree, 'opinion_text')
                if newdict['dissent_text']!=None:
                    d['dissent_text']=getOpinions(tree, 'dissent_text')
                if newdict['concurrence_text']!=None:
                    d['concurrence_text']=getOpinions(tree, 'concurrence_text')
                if newdict['attorneys']!=None:
                    d['attorneys']=getAttorneys(newdict['attorneys'])
                print("File no "+filenum+" scanned")
                casedata.append(d)
                print (count)
                count=count+1

                if count == num:
                    return casedata
    return casedata

# main()
#
# # Get opinion text(dissent, concurrence)
# #Get docket number: Many files don't have docket number, ??
# #Get attorneys
# #How to deal with cross references in the text?
# import csv
# with open('/Users/divyasingh/Dropbox/ash-naidu/court-listener/output1.csv', 'w') as csvfile:
#     fieldnames=['filenum', 'courtid', 'opinion_byline', 'dissent_byline','dates','posture', 'casename_full', 'casename_short', 'casename','panel', 'docket', 'citation', 'opinion_text', 'dissent_text', 'attorneys']
#     writer=csv.DictWriter(csvfile, fieldnames=fieldnames)
#     writer.writeheader()
#     for j in range(1,len(casedata)):
#         writer.writerow(casedata[j])







