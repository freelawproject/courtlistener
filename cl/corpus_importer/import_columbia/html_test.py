import fnmatch
import logging
import os
import re
import traceback
from glob import glob
from random import shuffle
import dateutil.parser as dparser

import xml.etree.cElementTree as ET


def file_generator(dir_path, random_order=False, limit=None):
    """Generates full file paths to all xml files in `dir_path`.
    
    :param dir_path: The path to get files from.
    :param random_order: If True, will generate file names randomly (possibly
     with repeats) and will never stop generating file names.
    :param limit: If not None, will limit the number of files generated to this
     integer.
    """
    count = 0
    if not random_order:
        for root, dir_names, file_names in os.walk(dir_path):
            file_names.sort()
            for file_name in fnmatch.filter(file_names, '*.xml'):
                yield os.path.join(root, file_name).replace('\\', '/')
                count += 1
                if count == limit:
                    return
    else:
        for root, dir_names, file_names in os.walk(dir_path):
            shuffle(dir_names)
            names = fnmatch.filter(file_names, '*.xml')
            if names:
                shuffle(names)
                yield os.path.join(root, names[0]).replace('\\', '/')
                break
        count += 1
        if count == limit:
            return

# tags for which content will be condensed into plain text
SIMPLE_TAGS = [
    "reporter_caption", "citation", "caption", "court", "docket", "posture"
    ,"date", "hearing_date"
    ,"panel", "attorneys"
]

# regex that will be applied when condensing SIMPLE_TAGS content
STRIP_REGEX = [r'</?citation.*>', r'</?page_number.*>']

# types of opinions that will be parsed
# each may have a '_byline' and '_text' node
OPINION_TYPES = ['opinion', 'dissent', 'concurrence']

def clean_string(s):
    """Clean up strings.

    Accomplishes the following:
     - replaces HTML encoded characters with ASCII versions.
     - removes -, ' ', #, *, ; and ',' from the end of lines
     - converts to unicode.
     - removes weird white space and replaces with spaces.
    """
    # if not already unicode, make it unicode, dropping invalid characters
    # if not isinstance(s, unicode):
    #s = force_unicode(s, errors='ignore')

    # Get rid of HTML encoded chars
    s = s.replace(u'&rsquo;', u'\'').replace(u'&rdquo;', u'\"')\
        .replace(u'&ldquo;', u'\"').replace(u'&nbsp;', u' ')\
        .replace(u'&amp;', u'&').replace(u'%20', u' ').replace(u'&#160;', u' ')

    # smart quotes
    s = s.replace(u'’', u"'").replace(u'‘', u"'").replace(u'“', u'"')\
        .replace(u'”', u'"')

    # Get rid of weird punctuation
    s = s.replace(u'*', u'').replace(u'#', u'').replace(u';', u'')

    # Strip bad stuff from the end of lines. Python's strip fails here because
    # we don't know the order of the various punctuation items to be stripped.
    # We split on the v., and handle fixes at either end of plaintiff or
    # appellant.
    bad_punctuation = '(-|–|_|/|;|,|\s)*'
    bad_endings = re.compile(r'%s$' % bad_punctuation)
    bad_beginnings = re.compile(r'^%s' % bad_punctuation)

    s = s.split(u' v. ')
    cleaned_string = []
    for frag in s:
        frag = re.sub(bad_endings, u'', frag)
        frag = re.sub(bad_beginnings, u'', frag)
        cleaned_string.append(frag)
    s = u' v. '.join(cleaned_string)

    # get rid of '\t\n\x0b\x0c\r ', and replace them with a single space.
    s = u' '.join(s.split())

    return s

def parse_file(file_path, court_fallback=''):
    """Parses a file, turning it into a correctly formatted dictionary, ready to be used by a populate script.

    :param file_path: A path the file to be parsed.
    :param court_fallback: A string used as a fallback in getting the court object.
        The regexes associated to its value in special_regexes will be used.
    """
    raw_info = get_text(file_path)
    if raw_info is None:
        return
    info = {}
    # throughout the process, collect all info about judges and at the end use it to populate info['judges']
    # get basic info
    info['unpublished'] = raw_info['unpublished']
    info['file'] = os.path.splitext(os.path.basename(file_path))[0]
    info['docket'] = ''.join(raw_info.get('docket', [])) or None
    info['citations'] = raw_info.get('citation', [])
    info['attorneys'] = ''.join(raw_info.get('attorneys', [])) or None
    info['posture'] = ''.join(raw_info.get('posture', [])) or None
    #panel_text = ''.join(raw_info.get('panel', []))
    #if panel_text:
    #    judge_info.append(('Panel\n-----', panel_text))
    # get dates
    dates = raw_info.get('date', []) + raw_info.get('hearing_date', [])
    info['dates'] = parse_dates(dates)

    # get case names
    # figure out if this case was heard per curiam by checking the first chunk of text in fields in which this is
    # usually indicated
    info['per_curiam'] = False
    first_chunk = 1000
    for opinion in raw_info.get('opinions', []):
        if 'per curiam' in opinion['opinion'][:first_chunk].lower():
            info['per_curiam'] = True
            break
        if opinion['byline'] and 'per curiam' in opinion['byline'][:first_chunk].lower():
            info['per_curiam'] = True
            break
    # condense opinion texts if there isn't an associated byline
    # print a warning whenever we're appending multiple texts together
    info['opinions'] = []
    for current_type in OPINION_TYPES:
        last_texts = []
        for opinion in raw_info.get('opinions', []):
            if opinion['type'] != current_type:
                continue
            last_texts.append(opinion['opinion'])
            if opinion['byline']:
                #judge_info.append((
                #    '%s Byline\n%s' % (current_type.title(), '-' * (len(current_type) + 7)),
                #    opinion['byline']
                #))
                # add the opinion and all of the previous texts
                info['opinions'].append({
                    'opinion': '\n'.join(last_texts)
                    ,'opinion_texts': last_texts
                    ,'type': current_type
                    ,'byline': opinion['byline']
                })
                last_texts = []
                if current_type == 'opinion': 
                    info['judges'] = opinion['byline']
                    
        # if there are remaining texts without bylines, either add them to the last opinion of this type, or if there
        # are none, make a new opinion without an author
        if last_texts:
            relevant_opinions = [o for o in info['opinions'] if o['type'] == current_type]
            if relevant_opinions:
                relevant_opinions[-1]['opinion'] += '\n%s' % '\n'.join(last_texts)
                relevant_opinions[-1]['opinion_texts'].extend(last_texts)
            else:
                info['opinions'].append({
                    'opinion': '\n'.join(last_texts)
                    ,'opinion_texts': last_texts
                    ,'type': current_type
                    ,'author': None
                    ,'joining': []
                    ,'byline': ''
                })
    # check if opinions were heard per curiam by checking if the first chunk of text in the byline or in
    #  any of its associated opinion texts indicate this
    for opinion in info['opinions']:
        # if there's already an identified author, it's not per curiam
        # otherwise, search through chunks of text for the phrase 'per curiam'
        per_curiam = False
        first_chunk = 1000
        if 'per curiam' in opinion['byline'][:first_chunk].lower():
            per_curiam = True
        else:
            for text in opinion['opinion_texts']:
                if 'per curiam' in text[:first_chunk].lower():
                    per_curiam = True
                    break
        opinion['per_curiam'] = per_curiam
    # construct the plain text info['judges'] from collected judge data
    #info['judges'] = '\n\n'.join('%s\n%s' % i for i in judge_info)

    return info


def get_text(file_path):
    """Reads a file and returns a dictionary of grabbed text.

    :param file_path: A path the file to be parsed.
    """
    with open(file_path, 'r') as f:
        file_string = f.read()
    raw_info = {}
    # used when associating a byline of an opinion with the opinion's text
    current_byline = {
        'type': None
        ,'name': None
    }
    # if this is an unpublished opinion, note this down and remove all <unpublished> tags
    raw_info['unpublished'] = False
    if '<opinion unpublished=true>' in file_string:
        file_string = file_string.replace('<opinion unpublished=true>', '<opinion>')
        file_string = file_string.replace('<unpublished>', '').replace('</unpublished>', '')
        raw_info['unpublished'] = True
    # turn the file into a readable tree
    try:
        root = ET.fromstring(file_string)
    except ET.ParseError:
        # these seem to be erroneously swapped quite often -- try to fix the misordered tags
        #file_string = file_string.replace('</footnote_body></block_quote>', '</block_quote></footnote_body>')
        #root = ET.fromstring(file_string)
        return
    for child in root.iter():
        # if this child is one of the ones identified by SIMPLE_TAGS, just grab its text
        
        if child.tag in SIMPLE_TAGS:
            # strip unwanted tags and xml formatting
            text = get_xml_string(child)
            for r in STRIP_REGEX:
                text = re.sub(r, '', text)
            text = re.sub(r'<.*?>', ' ', text).strip()
            # put into a list associated with its tag
            #if child.tag == 'date':
                #print(text)
                #raise
            raw_info.setdefault(child.tag, []).append(text)
            continue
        for opinion_type in OPINION_TYPES:
            #c if this child is a byline, note it down and use it later
            if child.tag == "%s_byline" % opinion_type:
                current_byline['type'] = opinion_type
                current_byline['name'] = get_xml_string(child)
                break
            # if this child is an opinion text blob, add it to an incomplete opinion and move into the info dict
            if child.tag == "%s_text" % opinion_type:
                # add the full opinion info, possibly associating it to a byline
                raw_info.setdefault('opinions', []).append({
                    'type': opinion_type
                    ,'byline': current_byline['name'] if current_byline['type'] == opinion_type else None
                    ,'opinion': get_xml_string(child)
                })
                current_byline['type'] = current_byline['name'] = None
                break
    return raw_info


def parse_dates(raw_dates, caseyear):
    """Parses the dates from a list of string.
    Returns a list of lists of (string, datetime) tuples if there is a string before the date (or None).

    :param raw_dates: A list of (probably) date-containing strings
    :param caseyear: the year of the case (for checking)
    """
    months = re.compile("january|february|march|april|may|june|july|august|"
                        "september|october|november|december")
    dates = []
    for raw_date in raw_dates:
        # there can be multiple years in a string, so we split on possible
        # indicators
        raw_parts = re.split('(?<=[0-9][0-9][0-9][0-9])(\s|.)', raw_date)

        # index over split line and add dates
        inner_dates = []
        for raw_part in raw_parts:
            # consider any string without either a month or year not a date
            no_month = False
            if re.search(months, raw_part.lower()) is None:
                no_month = True
                if re.search('[0-9][0-9][0-9][0-9]', raw_part) is None:
                    continue
            # strip parenthesis from the raw string (this messes with the date
            # parser)
            raw_part = raw_part.replace('(', '').replace(')', '')
            # try to grab a date from the string using an intelligent library
            try:
                date = dparser.parse(raw_part, fuzzy=True).date()
            except:
                continue
            if date.year > caseyear + 1 or date.year < caseyear - 2:
                date.year = caseyear
                print('Year problem:',)
                

            # split on either the month or the first number (e.g. for a
            # 1/1/2016 date) to get the text before it
            if no_month:
                text = re.compile('(\d+)').split(raw_part.lower())[0].strip()
            else:
                text = months.split(raw_part.lower())[0].strip()
            # remove footnotes and non-alphanumeric characters
            text = re.sub('(\[fn.?\])', '', text)
            text = re.sub('[^A-Za-z ]', '', text).strip()
            # if we ended up getting some text, add it, else ignore it
            if text:
                inner_dates.append((clean_string(text), date))
            else:
                inner_dates.append((None, date))
        dates.append(inner_dates)
    return dates


def get_xml_string(e):
    """Returns a normalized string of the text in <element>.

    :param e: An XML element.
    """

    inner_string = re.sub(r'(^<%s\b.*?>|</%s\b.*?>$)' % (e.tag, e.tag), '', ET.tostring(e).decode("utf-8") )
    return  inner_string.strip()



#dir_path = '/home/elliott/freelawmachine/flp/columbia_data/opinions'
#folders = glob(dir_path+'/*')
folders = glob('*')
folders.sort()

from collections import Counter
html_tab = Counter()

for folder in folders:
    #print(folder)
    for path in file_generator(folder):
        #f = open(path).read()
        #x = f.count('<date>')
        #if x > 1:
        #    print(path)
            #break

        parsed = parse_file(path)
        if parsed is None:
            continue
        #print(parsed['dates'])            
        newname = path.replace('/','_')
        if len(parsed['dates']) == 0:     
            print(path)
            print(open(path).read(), file=open('_nodate/'+newname,'wt'))
            continue
            
        if len(parsed['dates'][0]) == 0:
            #print
            print(path)
            
            print(open(path).read(), file=open('_failparse/'+newname,'wt'))
            
        
#        numops = len(parsed['opinions'])
#        if numops > 0:
#            for op in parsed['opinions']:
#                optext = op['opinion']
#                tags = re.findall('<.*?>',optext)
#                html_tab.update(tags)
#                #if '<block_quote>' in tags:
#                #    print(optext)
#                #    exit()
#                