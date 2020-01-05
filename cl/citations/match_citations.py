#!/usr/bin/env python
# encoding utf-8

from datetime import date, datetime

from django.conf import settings
from reporters_db import REPORTERS

from cl.citations.find_citations import strip_punct
from cl.lib import sunburnt

DEBUG = True

QUERY_LENGTH = 10


def build_date_range(start_year, end_year):
    """Build a date range to be handed off to a solr query."""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    date_range = "[%sZ TO %sZ]" % (start.isoformat(), end.isoformat())
    return date_range


def make_name_param(defendant, plaintiff=None):
    """Remove punctuation and return cleaned string plus its length in tokens.
    """
    token_list = defendant.split()
    if plaintiff:
        token_list.extend(plaintiff.split())
        # Strip out punctuation, which Solr doesn't like
    query_words = [strip_punct(t) for t in token_list]
    return u" ".join(query_words), len(query_words)


def reverse_match(conn, results, citing_doc):
    """Uses the case name of the found document to verify that it is a match on
    the original.
    """
    params = {"fq": ["id:%s" % citing_doc.pk]}
    for result in results:
        case_name, length = make_name_param(result["caseName"])
        # Avoid overly long queries
        start = max(length - QUERY_LENGTH, 0)
        query_tokens = case_name.split()[start:]
        query = " ".join(query_tokens)
        # ~ performs a proximity search for the preceding phrase
        # See: http://wiki.apache.org/solr/SolrRelevancyCookbook#Term_Proximity
        params["q"] = '"%s"~%d' % (query, len(query_tokens))
        params["caller"] = "reverse_match"
        new_results = conn.raw_query(**params).execute()
        if len(new_results) == 1:
            return [result]
    return []


def case_name_query(conn, params, citation, citing_doc):
    query, length = make_name_param(citation.defendant, citation.plaintiff)
    params["q"] = "caseName:(%s)" % query
    params["caller"] = "match_citations"
    results = []
    # Use Solr minimum match search, starting with requiring all words to match,
    # and decreasing by one word each time until a match is found
    for num_words in xrange(length, 0, -1):
        params["mm"] = num_words
        new_results = conn.raw_query(**params).execute()
        if len(new_results) >= 1:
            # For 1 result, make sure case name of match actually appears in
            # citing doc. For multiple results, use same technique to
            # potentially narrow down
            return reverse_match(conn, new_results, citing_doc)
            # Else, try again
        results = new_results
    return results


def get_years_from_reporter(citation):
    """Given a citation object, try to look it its dates in the reporter DB"""
    start_year = 1750
    end_year = date.today().year
    if citation.lookup_index is not None:
        # Some cases can't be disambiguated.
        # fmt: off
        reporter_dates = (REPORTERS[citation.canonical_reporter]
                          [citation.lookup_index]
                          ['editions']
                          [citation.reporter])
        # fmt: on
        if hasattr(reporter_dates["start"], "year"):
            start_year = reporter_dates["start"].year
        if hasattr(reporter_dates["end"], "year"):
            end_year = reporter_dates["end"].year
    return start_year, end_year


def match_citation(citation, citing_doc=None):
    """For a citation object, try to match it to an item in the database using
    a variety of heuristics.

    Returns:
      - a Solr Result object with the results, or an empty list if no hits
    """
    # TODO: Create shared solr connection for all queries
    conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode="r")
    main_params = {
        "q": "*",
        "fq": [
            "status:Precedential",  # Non-precedential documents aren't cited
        ],
        "caller": "citation.match_citations.match_citation",
    }
    if citing_doc is not None:
        # Eliminate self-cites.
        main_params["fq"].append("-id:%s" % citing_doc.pk)
    # Set up filter parameters
    if citation.year:
        start_year = end_year = citation.year
    else:
        start_year, end_year = get_years_from_reporter(citation)
        if citing_doc is not None and citing_doc.cluster.date_filed:
            end_year = min(end_year, citing_doc.cluster.date_filed.year)
    main_params["fq"].append(
        "dateFiled:%s" % build_date_range(start_year, end_year)
    )

    if citation.court:
        main_params["fq"].append("court_exact:%s" % citation.court)

    # Take 1: Use a phrase query to search the citation field.
    main_params["fq"].append('citation:("%s")' % citation.base_citation())
    results = conn.raw_query(**main_params).execute()
    if len(results) == 1:
        return results
    if len(results) > 1:
        if citing_doc is not None and citation.defendant:
            # Refine using defendant, if there is one
            results = case_name_query(conn, main_params, citation, citing_doc)
        return results

    # Give up.
    return []
