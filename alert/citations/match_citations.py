#!/usr/bin/env python
# encoding utf-8

import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import sys
sys.path.append("/var/www/court-listener")

from django.conf import settings
from alert.search.models import Court
from alert.lib import sunburnt

from datetime import date, datetime
import string

DEBUG = True

REPORTER_DATES = {'F.': (1880, 1924),
                  'F.2d': (1924, 1993),
                  'F.3d': (1999, date.today().year),
                  'F. Supp.': (1933, 1998),
                  'F. Supp. 2d': (1998, date.today().year),
                  'L. Ed.': (1790, 1956),
                  'L. Ed. 2d.': (1956, date.today().year)}

QUERY_LENGTH = 10

# Store court values to avoid repeated DB queries
courts = Court.objects.all().values('citation_string', 'courtUUID')


def build_date_range(start_year, end_year):
    '''Build a date range to be handed off to a solr query.'''
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    date_range = '[%sZ TO %sZ]' % (start.isoformat(),
                                   end.isoformat())
    return date_range

def make_name_param(defendant, plaintiff):
    '''Remove punctuation tokens and return cleaned string plus its length in 
    tokens.
    '''
    token_list = defendant.split()
    if plaintiff:
        token_list.extend(plaintiff.split())
    # Filter out stand-alone punctuation, which Solr doesn't like
    query_words = [t for t in token_list if t not in string.punctuation]
    return (u' '.join(query_words), len(query_words))

def reverse_match(conn, results, citing_doc):
    '''Uses the case name of the found document to verify that it is a match on
    the original.
    '''
    params = {}
    for result in results:
        case_name_tokens = result['caseName'].split()
        num_tokens = len(case_name_tokens)
        # Avoid overly long queries
        start = max(num_tokens - QUERY_LENGTH, 0)
        query_tokens = case_name_tokens[start:]
        query = ' '.join(query_tokens)
        # ~ performs a proximity search for the preceding phrase
        # See: http://wiki.apache.org/solr/SolrRelevancyCookbook#Term_Proximity
        params['q'] = '"%s"~%d %s' % (query, len(query_tokens), citing_doc.documentSHA1)
        new_results = conn.raw_query(**params).execute()
        if len(new_results) == 1:
            return [result]
    return []

def case_name_query(conn, params, citation, citing_doc):
    query, length = make_name_param(citation.defendant, citation.plaintiff)
    params['q'] = "caseName:(%s)" % query
    # Non-precedential documents shouldn't be cited
    params['fq'].append('status:Precedential')
    results = []
    # Use Solr minimum match search, starting with requiring all words to match,
    # and decreasing by one word each time until a match is found
    for num_words in xrange(length, 0, -1):
        params['mm'] = num_words
        new_results = conn.raw_query(**params).execute()
        if len(new_results) >= 1:
            # For 1 result, make sure case name of match actually appears in citing doc
            # For multiple results, use same technique to potentially narrow down
            return reverse_match(conn, new_results, citing_doc)
        # Else, try again
        results = new_results
    return results

def match_citation(citation, citing_doc):
    # TODO: Create shared solr connection to use across multiple citations/documents
    conn = sunburnt.SolrInterface(settings.SOLR_URL, mode='r')
    main_params = {}
    # Take 1: Use citation
    main_params['fq'] = []
    if citation.year:
        start_year = end_year = citation.year
    else:
        end_year = citing_doc.dateFiled.year
        start_year = 1754 # Earliest case in the db
        if citation.reporter in REPORTER_DATES:
            reporter_start, reporter_end = REPORTER_DATES[citation.reporter]
            start_year = max(start_year, reporter_start)
            end_year = min(end_year, reporter_end)
    date_param = 'dateFiled:%s' % build_date_range(start_year, end_year)
    main_params['fq'].append(date_param)
    if not citation.court and citation.reporter in ["U.S.", "U. S."]:
        citation.court = "SCOTUS"
    if citation.court:
        for court in courts:
            # Use startswith because citations are often missing final period, e.g. "2d Cir"
            if court['citation_string'].startswith(citation.court):
                court_param = 'court_exact:%s' % court['courtUUID']
                main_params['fq'].append(court_param)

    citation_param = 'westCite:"%s"' % citation.base_citation()
    main_params['fq'].append(citation_param)
    results = conn.raw_query(**main_params).execute()
    if len(results) == 1:
        return results, True
    if len(results) > 1:
        if citation.defendant: # Refine using defendant, if there is one
            results = case_name_query(conn, main_params, citation, citing_doc)
        return results, True

    # Take 2: Use case name
    if not citation.defendant:
        return [], False
    # Remove citation parameter
    main_params['fq'].remove(citation_param)
    return case_name_query(conn, main_params, citation, citing_doc), False


if __name__ == '__main__':
    exit(0)
