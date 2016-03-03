# -*- coding: utf-8 -*-

# Functions to parse court data in XML format into a list of dictionaries.

import xml.etree.cElementTree as ET
import re
import os
import dateutil.parser as dparser

from juriscraper.lib.string_utils import titlecase, harmonize, clean_string, CaseNameTweaker

from regexes_columbia import STATE_PAIRS, SPECIAL_REGEXES
from parse_judges import find_judges


# initialized once since it takes resources
CASE_NAME_TWEAKER = CaseNameTweaker()

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


def parse_file(file_path, court_fallback=''):
    """Parses a file, turning it into a correctly formatted dictionary, ready to be used by a populate script.

    :param file_path: A path the file to be parsed.
    :param court_fallback: A string used as a fallback in getting the court object.
        The regexes associated to its value in special_regexes will be used.
    """
    raw_info = get_text(file_path)
    info = {}
    # get basic info
    info['unpublished'] = raw_info['unpublished']
    info['file'] = os.path.splitext(os.path.basename(file_path))[0]
    info['docket'] = ''.join(raw_info.get('docket', [])) or None
    info['citations'] = raw_info.get('citation', [])
    info['attorneys'] = ''.join(raw_info.get('attorneys', [])) or None
    info['posture'] = ''.join(raw_info.get('posture', [])) or None
    info['court_id'] = get_court_object(''.join(raw_info.get('court', [])), court_fallback) or None
    info['panel'] = find_judges(''.join(raw_info.get('panel', []))) or []
    # get dates
    dates = raw_info.get('date', []) + raw_info.get('hearing_date', [])
    info['dates'] = parse_dates(dates)
    # get case names
    info['case_name_full'] = format_case_name(''.join(raw_info.get('caption', []))) or None
    info['case_name'] = format_case_name(''.join(raw_info.get('reporter_caption', []))) or None
    info['case_name_short'] = CASE_NAME_TWEAKER.make_case_name_short(info['case_name']) or None
    # get opinions
    info['opinions'] = []
    for opinion in raw_info.get('opinions', []):
        full_opinion = {
            'opinion': opinion['opinion']
            ,'type': opinion['type']
            ,'author': None
            ,'joining': []
        }
        if opinion['byline']:
            judges = find_judges(opinion['byline'])
            if judges:
                full_opinion['author'] = judges[0]
            if len(judges) > 1:
                full_opinion['joining'] = judges[1:]
        info['opinions'].append(full_opinion)
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
        file_string = file_string.replace('</footnote_body></block_quote>', '</block_quote></footnote_body>')
        root = ET.fromstring(file_string)
    for child in root.iter():
        # if this child is one of the ones identified by SIMPLE_TAGS, just grab its text
        if child.tag in SIMPLE_TAGS:
            # strip unwanted tags and xml formatting
            text = get_xml_string(child)
            for r in STRIP_REGEX:
                text = re.sub(r, '', text)
            text = re.sub(r'<.*?>', ' ', text).strip()
            # put into a list associated with its tag
            raw_info.setdefault(child.tag, []).append(text)
            continue
        for opinion_type in OPINION_TYPES:
            # if this child is a byline, note it down and use it later
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


def get_xml_string(e):
    """Returns a normalized string of the text in <element>.

    :param e: An XML element.
    """
    inner_string = re.sub(r'(^<%s\b.*?>|</%s\b.*?>$)' % (e.tag, e.tag), '', ET.tostring(e))
    return  inner_string.decode('utf-8').strip()


def parse_dates(raw_dates):
    """Parses the dates from a list of string.
    Returns a list of lists of (string, datetime) tuples if there is a string before the date (or None).

    :param raw_dates: A list of (probably) date-containing strings
    """
    months = re.compile("january|february|march|april|may|june|july|august|september|october|november|december")
    dates = []
    for raw_date in raw_dates:
        # there can be multiple years in a string, so we split on possible indicators
        raw_parts = re.split('(?<=[0-9][0-9][0-9][0-9])(\s|.)', raw_date)
        #index over split line and add dates
        inner_dates = []
        for raw_part in raw_parts:
            # consider any string without either a month or year not a date
            no_month = False
            if re.search(months, raw_part.lower()) is None:
                no_month = True
                if re.search('[0-9][0-9][0-9][0-9]', raw_part) is None:
                    continue
            # try to grab a date from the string using an intelligent library
            try:
                date = dparser.parse(raw_part, fuzzy=True).date()
            except:
                continue
            # split on either the month or the first number (e.g. for a 1/1/2016 date) to get the text before it
            if no_month:
                text = re.compile('(\d+)').split(raw_part.lower())[0].strip()
            else:
                text = months.split(raw_part.lower())[0].strip()
            # if we ended up getting some text, add it, else ignore it
            if text:
                inner_dates.append((clean_string(text), date))
            else:
                inner_dates.append((None, date))
        dates.append(inner_dates)
    return dates


def format_case_name(n):
    """Applies standard harmonization methods after normalizing with lowercase."""
    return titlecase(harmonize(n.lower()))


def get_court_object(raw_court, fallback=''):
    """Get the court object from a string. Searches through `STATE_PAIRS`.

    :param raw_court: A raw court string, parsed from an XML file.
    :param fallback: If fail to find one, will apply the regexes associated to this key in `SPECIAL_REGEXES`.
    """
    if '.' in raw_court:
        j = raw_court.find('.')
        raw_court = raw_court[:j]
    if ',' in raw_court:
        j = raw_court.find(',')
        raw_court = raw_court[:j]
    for regex, value in STATE_PAIRS:
        if re.search(regex, raw_court):
            return value
    if fallback in SPECIAL_REGEXES:
        for regex, value in SPECIAL_REGEXES:
            if re.search(regex, raw_court):
                return value


if __name__ == '__main__':
    parsed = parse_file("test_opinions/0b59c80d9043a003.xml")
    pass
