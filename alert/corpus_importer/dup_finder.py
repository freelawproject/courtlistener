from collections import OrderedDict
import string
import os
from alert.lib.solr_core_admin import get_term_frequency

os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import sys
execfile('/etc/courtlistener')
sys.path.append(INSTALL_ROOT)

from django.conf import settings
from alert.lib import sunburnt
from alert.lib.string_diff import find_confidences, gen_diff_ratio, get_cosine_similarity
import datetime
import re

DEBUG = True


def build_date_range(date_filed, range=5):
    """Build a date range to be handed off to a solr query

    """
    after = date_filed - datetime.timedelta(days=range)
    before = date_filed + datetime.timedelta(days=range + 1)
    date_range = '[%sZ TO %sZ]' % (after.isoformat(),
                                   before.isoformat())
    return date_range


class StopWords(object):
    """A very simple object that can hold stopwords, but that is only initialized once."""
    stop_words = get_term_frequency(result_type='list')


def get_good_words(word_list, stop_words_size=500):
    """Cleans out stop words, abbreviations, etc. from a list of words"""
    stopwords = StopWords().stop_words
    good_words = []
    for word in word_list:
        # Clean things up
        word = re.sub(r"'s", '', word)
        word = word.strip('*,();"')

        # Boolean conditions
        stop = word in stopwords[:stop_words_size]
        bad_stuff = re.search('[0-9./()!:&\']', word)
        too_short = (len(word) <= 1)
        is_acronym = (word.isupper() and len(word) <= 3)
        if any([stop, bad_stuff, too_short, is_acronym]):
            continue
        else:
            good_words.append(word)
    # Eliminate dups, but keep order.
    return list(OrderedDict.fromkeys(good_words))


def make_case_name_solr_query(caseName, court, date_filed, DEBUG=False):
    """Grab words from the content and returns them to the caller.

    This function attempts to choose words from the content that would return
    the fewest cases if queried. Words are selected from the case name and the
    content.
    """
    main_params = {
        'fq': [
            'court_exact:%s' % court,
            'dateFiled:%s' % build_date_range(date_filed, range=15)
        ],
        'rows': 100,
        'caller': 'corpus_importer',
    }

    case_name_q_words = []
    case_name_words = caseName.split()
    if ' v. ' in caseName.lower():
        v_index = case_name_words.index('v.')
        # The first word of the defendant and the last word in the plaintiff that's
        # not a bad word.
        plaintiff_a = get_good_words(case_name_words[:v_index])
        defendant_a = get_good_words(case_name_words[v_index + 1:])
        if plaintiff_a:
            case_name_q_words.append(plaintiff_a[-1])
        if defendant_a:
            # append the first good word that's not already in the array
            try:
                case_name_q_words.append([word for word in defendant_a if word not in case_name_q_words][0])
            except IndexError:
                # When no good words left in defendant_a
                pass
    elif 'in re ' in caseName.lower() or 'matter of ' in caseName.lower() or 'ex parte' in caseName.lower():
        try:
            subject = re.search('(?:(?:in re)|(?:matter of)|(?:ex parte)) (.*)', caseName, re.I).group(1)
        except TypeError:
            subject = ''
        good_words = get_good_words(subject.split())
        if good_words:
            case_name_q_words.append(good_words[0])
    else:
        case_name_q_words = get_good_words(caseName.split())
    if case_name_q_words:
        main_params['fq'].append('caseName:(%s)' % ' '.join(case_name_q_words))

    return main_params


def get_dup_stats(doc):
    """The heart of the duplicate algorithm. Returns stats about the case as
    compared to other cases already in the system. Other methods can call this
    one, and can make decisions based on the stats generated here.

    If no likely duplicates are encountered, stats are returned as zeroes.

    Process:
        1. Refine the possible result set down to just a few candidates.
        2. Determine their likelihood of being duplicates according to a
           number of measures:
            - Similarity of case name
            - Similarity of docket number
            - Comparison of content length
    """
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
    DEBUG = True

    ##########################################
    # 1: Refine by date, court and case name #
    ##########################################
    main_params = make_case_name_solr_query(
        doc.citation.case_name,
        doc.docket.court_id,
        doc.date_filed,
        DEBUG=DEBUG,
    )
    main_params['caller'] = 'corpus_importer'
    if DEBUG:
        print "    - main_params are: %s" % main_params
    candidates = conn.raw_query(**main_params).execute()

    if not len(candidates) and doc.citation.docket_number is not None:
        # Try by docket number rather than case name
        clean_docket_number_words = []
        for word in doc.citation.docket_number.split():
            if not re.search('\d', word):
                # Must have numbers.
                continue
            word = word.strip(string.punctuation)
            regex = re.compile('[%s]' % re.escape(string.punctuation))
            if regex.search(re.sub('-', '', word)):
                # Can only have hyphens after stripping
                continue
            clean_docket_number_words.append(word)
        docket_q = ' OR '.join(clean_docket_number_words)
        if docket_q:
            main_params = {
                'fq': [
                    'court_exact:%s' % doc.docket.court_id,
                    'dateFiled:%s' % build_date_range(doc.date_filed, range=15),
                    'docketNumber:(%s)' % docket_q
                ],
                'rows': 100,
                'caller': 'corpus_importer',
            }
            if DEBUG:
                print "    - main_params are: %s" % main_params
            candidates = conn.raw_query(**main_params).execute()

    if not len(candidates) and doc.docket.court_id == 'scotus':
        if doc.citation.federal_cite_one:
            # Scotus case, try by citation.
            main_params = {
                'fq': [
                    'court_exact:%s' % doc.docket.court_id,
                    'dateFiled:%s' % build_date_range(doc.date_filed, range=90),  # Creates ~6 month span.
                    'citation:(%s)' % ' '.join([re.sub(r"\D", '', w) for w in doc.citation.federal_cite_one.split()])
                ],
                'rows': 100,
                'caller': 'corpus_importer',
            }
            if DEBUG:
                print "    - main_params are: %s" % main_params
            candidates = conn.raw_query(**main_params).execute()

    stats = {'candidate_count': len(candidates)}
    if not len(candidates):
        return stats, candidates

    #########################################
    # 2: Attempt filtering by docket number #
    #########################################
    # Two-step process. First we see if we have any exact hits.
    # Second, if there were exact hits, we forward those onwards. If not, we
    # forward everything.
    remaining_candidates = []
    if doc.citation.docket_number:
        new_docket_number = re.sub("(\D|0)", "", doc.citation.docket_number)
        for candidate in candidates:
            if candidate.get('docketNumber'):
                # Get rid of anything in the docket numbers that's not a digit
                result_docket_number = re.sub("(\D|0)", "", candidate['docketNumber'])
                # Get rid of zeroes too.
                if new_docket_number == result_docket_number:
                    remaining_candidates.append(candidate)

    if len(remaining_candidates) > 0:
        # We had one or more exact hits! Use those.
        candidates = remaining_candidates
    else:
        # We just let candidates from step one get passed through by doing nothing.
        pass

    stats = {'candidate_count': len(candidates)}

    ##############################
    # 3: Find the best case name #
    ##############################
    confidences = find_confidences(candidates, doc.citation.case_name)
    stats['case_name_similarities'] = confidences

    #####################################################################
    # 4: Check content length, gestalt difference and cosine similarity #
    #####################################################################
    percent_diffs, gestalt_diffs, cos_sims = [], [], []
    new_stripped_content = re.sub('\W', '', doc.body_text).lower()
    for candidate in candidates:
        candidate_stripped_content = re.sub('\W', '', candidate['text']).lower()

        # Calculate the difference in text length and their gestalt difference
        try:
            length_diff = abs(len(candidate_stripped_content) - len(new_stripped_content))
        except ZeroDivisionError:
            length_diff = 0
        try:
            percent_diff = float(length_diff) / len(new_stripped_content)
        except ZeroDivisionError:
            percent_diff = 0
        cos_sim = get_cosine_similarity(doc.body_text, candidate['text'])
        percent_diffs.append(percent_diff)
        gestalt_diffs.append(gen_diff_ratio(candidate_stripped_content, new_stripped_content))
        cos_sims.append(cos_sim)

    stats['length_diffs'] = percent_diffs
    stats['gestalt_diffs'] = gestalt_diffs
    stats['cos_sims'] = cos_sims

    return stats, candidates
