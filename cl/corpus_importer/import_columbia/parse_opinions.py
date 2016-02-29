# -*- coding: utf-8 -*-

# Functions to parse court data in XML format into a list of dictionaries.

import xml.etree.cElementTree as ET
import re
import traceback
from random import shuffle
import os
import fnmatch
import geonamescache
import dateutil.parser as dparser
import logging

from regexes_columbia import state_pairs, special_regexes
from parse_judges import find_judges

# tags for which content will be condensed into plain text
SIMPLE_TAGS = [
    "reporter_caption", "citation", "caption", "court", "docket", "posture"
    ,"date", "hearing_date"
    ,"panel", "attorneys"
]

# regex that will be applied when condensing SIMPLE_TAGS content
STRIP_REGEX = [r'</?citation.*>', r'</?page_number.*>']

# types of opinions that will be parsed
# each must have both a '_byline' and '_text' node
OPINION_TYPES = ['opinion', 'dissent', 'concurrence']


def output(m=''):
    print m
    logging.info(m)


def parse_many(dir_path,
               limit=None,
               random_order=True,
               status_interval=10,
               court_fallback_regex=r"data/([a-z_]+?/[a-z_]+?)/",
               log=None):
    """Runs the parse method on all the xml files in the given directory tree up to the given limit.
    Yields dictionaries returned by the parse method.
    Prints parsing tracebacks instead of raising exceptions.

    :param dir_path: The directory to parse the files of.
    :param limit: A limit on how many files to parse. If None, will parse all.
    :param random_order: If true, will parse the files in a random order.
    :param status_interval: How often a status update will be given.
    :param court_fallback_regex: Regex that matches a file's path (always has '/' delimiters) for a string to be used
        as a fallback in getting the court object. The regexes associated to its value in special_regexes will be used.
    :param log: Either None or the file to log output to. Will be overwritten.
    """
    # get an initial number of files that we're going to be dealing with
    if log:
        print "Logging to '%s'." % log
        logging.basicConfig(filename=log, filemode='w', level=logging.DEBUG, format='%(message)s')
    if limit:
        total = limit
    else:
        output("Getting an initial count of the files to be parsed ...")
        total = 0
        for _, _, file_names in os.walk(dir_path):
            total += len(fnmatch.filter(file_names, '*.xml'))
    # go through the files, yielding parsed files and printing status updates as we go
    count = 0
    for root, dir_names, file_names in os.walk(dir_path):
        if random_order:
            shuffle(dir_names)
            shuffle(file_names)
        for file_name in fnmatch.filter(file_names, '*.xml'):
            path = os.path.join(root, file_name).replace('\\', '/')
            # grab the fallback text from the path if it's there
            court_fallback = ''
            if court_fallback_regex:
                matches = re.compile(court_fallback_regex).findall(path)
                if matches:
                    court_fallback = matches[0]
            # try to parse the file and print any exceptions with full tracebacks
            try:
                yield parse_file(path, court_fallback=court_fallback)
            except Exception as e:
                # print simple exception summaries for known problems
                if 'mismatched tag' in str(e):
                    output("Mismatched tag exception encountered in file '%s':%s" % (path, str(e).split(':', 1)[1]))
                else:
                    # otherwise, print generic traceback
                    output()
                    output("Exception encountered in file '%s':" % path)
                    logging.exception('')
                    print traceback.format_exc()
                    output()
                yield {}
            # status update
            count += 1
            if count % status_interval == 0:
                output("Parsed %s out of %s." % (count, total))
            if count == limit:
                return


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
    info['case_name_full'] = condense_whitespace(caps2title(''.join(raw_info.get('caption', [])))) or None
    info['case_name'] = condense_whitespace(caps2title(''.join(raw_info.get('reporter_caption', [])))) or None
    shortener = CaseNameTweaker()
    info['case_name_short'] = condense_whitespace(caps2title(shortener.make_case_name_short(info['case_name'])))
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
    Returns a list of lists of datetime objects or tuples of (string,datetime) if there is a string before the date

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
                date = dparser.parse(raw_part, fuzzy = True).date()
            except:
                continue
            # split on either the month or the first number (e.g. for a 1/1/2016 date) to get the text before it
            if no_month:
                text = re.compile('(\d+)').split(raw_part.lower())[0].strip()
            else:
                text = months.split(raw_part.lower())[0].strip()
            # if we ended up getting some text, add it, else ignore it
            if text:
                inner_dates.append((text,date))
            else:
                inner_dates.append((date,))
        dates.append(inner_dates)
    return dates


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
        if not s:
            return None
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


def caps2title(line):
    """Replaces all ALL CAPS words with Title Case."""
    return ''.join([s.title() if s.isupper() else s for s in re.split('([^a-zA-Z])', line)])


def condense_whitespace(line):
    """Condenses multiple whitespaces into a single one."""
    return ' '.join(line.split())


def get_court_object(raw_court, fallback=''):
    """Get the court object from a string.

    :param raw_court: A raw court string, parsed from an XML file.
    :param fallback: If fail to find one, will apply the regexes associated to this key in special_regexes.
    """
    if '.' in raw_court:
        j = raw_court.find('.')
        raw_court = raw_court[:j]
    if ',' in raw_court:
        j = raw_court.find(',')
        raw_court = raw_court[:j]
    for regex, value in state_pairs:
        if re.search(regex, raw_court):
            return value
    if fallback in special_regexes:
        for regex, value in special_regexes:
            if re.search(regex, raw_court):
                return value


if __name__ == '__main__':
    for i in parse_many(r'C:\Users\Jeff\Dropbox\court-listener\data', limit=100, status_interval=1000):
        pass
    # parsed = parse_file("test_opinions/0b59c80d9043a003.xml")
    # pass
