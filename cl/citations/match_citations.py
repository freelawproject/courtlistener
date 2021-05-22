#!/usr/bin/env python
# encoding utf-8

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple, Union, cast

from django.conf import settings
from eyecite.models import (
    CitationBase,
    FullCaseCitation,
    IdCitation,
    NonopinionCitation,
    ShortCaseCitation,
    SupraCitation,
)
from eyecite.utils import strip_punct

from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.scorched_utils import ExtraSolrInterface, ExtraSolrSearch
from cl.lib.types import SearchParam
from cl.search.models import Opinion

DEBUG = True

QUERY_LENGTH = 10


def build_date_range(start_year: int, end_year: int) -> str:
    """Build a date range to be handed off to a solr query."""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    date_range = "[%sZ TO %sZ]" % (start.isoformat(), end.isoformat())
    return date_range


def make_name_param(defendant: str, plaintiff: str = None) -> Tuple[str, int]:
    """Remove punctuation and return cleaned string plus its length in tokens."""
    token_list = defendant.split()
    if plaintiff:
        token_list.extend(plaintiff.split())
        # Strip out punctuation, which Solr doesn't like
    query_words = [strip_punct(t) for t in token_list]
    return " ".join(query_words), len(query_words)


def reverse_match(
    conn: ExtraSolrInterface,
    results: List[ExtraSolrSearch],
    citing_doc: Opinion,
) -> List[ExtraSolrSearch]:
    """Uses the case name of the found document to verify that it is a match on
    the original.
    """
    params: SearchParam = {"fq": ["id:%s" % citing_doc.pk]}
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
        new_results = conn.query().add_extra(**params).execute()
        if len(new_results) == 1:
            return [result]
    return []


def case_name_query(
    conn: ExtraSolrInterface,
    params: SearchParam,
    citation: CitationBase,
    citing_doc: Opinion,
) -> List[ExtraSolrSearch]:
    query, length = make_name_param(citation.defendant, citation.plaintiff)
    params["q"] = "caseName:(%s)" % query
    params["caller"] = "match_citations"
    results = []
    # Use Solr minimum match search, starting with requiring all words to
    # match and decreasing by one word each time until a match is found
    for num_words in range(length, 0, -1):
        params["mm"] = num_words
        new_results = conn.query().add_extra(**params).execute()
        if len(new_results) >= 1:
            # For 1 result, make sure case name of match actually appears in
            # citing doc. For multiple results, use same technique to
            # potentially narrow down
            return reverse_match(conn, new_results, citing_doc)
            # Else, try again
        results = new_results
    return results


def get_years_from_reporter(citation: CitationBase) -> Tuple[int, int]:
    """Given a citation object, try to look it its dates in the reporter DB"""
    start_year = 1750
    end_year = date.today().year

    edition_guess = citation.edition_guess
    if edition_guess:
        if hasattr(edition_guess.start, "year"):
            start_year = edition_guess.start.year
        if hasattr(edition_guess.end, "year"):
            start_year = edition_guess.end.year
    return start_year, end_year


def match_citation(
    citation: CitationBase, citing_doc: Opinion = None
) -> List[ExtraSolrSearch]:
    """For a citation object, try to match it to an item in the database using
    a variety of heuristics.

    Returns:
      - a Solr Result object with the results, or an empty list if no hits
    """
    # TODO: Create shared solr connection for all queries
    si = ExtraSolrInterface(settings.SOLR_OPINION_URL, mode="r")
    main_params: SearchParam = {
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
    results = si.query().add_extra(**main_params).execute()
    si.conn.http_connection.close()
    if len(results) == 1:
        return results
    if len(results) > 1:
        if citing_doc is not None and citation.defendant:
            # Refine using defendant, if there is one
            results = case_name_query(si, main_params, citation, citing_doc)
        return results

    # Give up.
    return []


def filter_by_matching_antecedent(
    citation_matches: List[Opinion],
    antecedent_guess: Optional[str],
) -> Optional[Opinion]:
    if not antecedent_guess:
        return None

    antecedent_guess = strip_punct(antecedent_guess)
    candidates: List[Opinion] = []

    for cm in citation_matches:
        if antecedent_guess in best_case_name(cm.cluster):
            candidates.append(cm)

    # Remove duplicates and only accept if one candidate remains
    candidates = list(set(candidates))
    return candidates[0] if len(candidates) == 1 else None


def get_citation_matches(
    citing_opinion: Opinion,
    citations: List[CitationBase],
) -> List[Opinion]:
    """For a list of Citation objects (e.g., FullCitations, SupraCitations,
    IdCitations, etc.), try to match them to Opinion objects in the database
    using a variety of heuristics.

    Returns:
      - a list of Opinion objects, as matched to citations
    """
    citation_matches: List[Opinion] = []  # List of matches to return
    was_matched: bool = (
        False  # Whether the previous citation match was successful
    )

    for citation in citations:
        matched_opinion = None

        # If the citation is to a non-opinion document, we currently cannot
        # match these.
        if isinstance(citation, NonopinionCitation):
            pass

        # If the citation is an id citation, just resolve it to the opinion
        # that was matched immediately prior (so long as the previous match
        # was successful).
        elif isinstance(citation, IdCitation):
            if was_matched:
                matched_opinion = citation_matches[-1]

        # If the citation is a supra citation, try to resolve it to one of
        # the citations that has already been matched
        elif isinstance(citation, SupraCitation):
            # The only clue we have to help us with resolution is the guess
            # of what the supra citation's antecedent is, so we try to
            # match that string to one of the known case names of the
            # already matched opinions. However, because case names might
            # look alike, matches using this heuristic may not be unique.
            # If no match, or more than one match, is found, then the supra
            # reference is effectively dropped.
            matched_opinion = filter_by_matching_antecedent(
                citation_matches, citation.antecedent_guess
            )

        # Likewise, if the citation is a short form citation, try to resolve it
        # to one of the citations that has already been matched
        elif isinstance(citation, ShortCaseCitation):
            # We first try to match by using the reporter and volume number.
            # However, because matches made using this heuristic may not be
            # unique, we then refine by using the antecedent guess and only
            # accept the match if there is a single unique candidate. This
            # refinement may still fail (because the guess could be
            # meaningless), in which case the citation is not resolvable and
            # is dropped.
            candidates = []
            for cm in citation_matches:
                for c in cm.cluster.citations.all():
                    if (
                        citation.reporter == c.reporter
                        and citation.volume == str(c.volume)
                    ):
                        candidates.append(cm)

            candidates = list(set(candidates))  # Remove duplicate matches
            if len(candidates) == 1:
                # Accept the match!
                matched_opinion = candidates[0]
            else:
                matched_opinion = filter_by_matching_antecedent(
                    candidates, citation.antecedent_guess
                )

        # Otherwise, the citation is just a regular citation, so try to match
        # it directly to an opinion
        elif isinstance(citation, FullCaseCitation):
            matches = match_citation(citation, citing_doc=citing_opinion)

            if len(matches) == 1:
                match_id = matches[0]["id"]
                try:
                    matched_opinion = Opinion.objects.get(pk=match_id)
                except Opinion.DoesNotExist:
                    # No Opinions returned. Press on.
                    pass
                except Opinion.MultipleObjectsReturned:
                    # Multiple Opinions returned. Press on.
                    pass
            else:
                # No match found for citation
                pass

        # If an opinion was successfully matched, add it to the list and
        # set the match fields on the original citation object so that they
        # can later be used for generating inline html
        if matched_opinion:
            was_matched = True
            citation_matches.append(matched_opinion)
            citation.match_url = matched_opinion.cluster.get_absolute_url()
            citation.match_id = matched_opinion.pk
        else:
            was_matched = False

    return citation_matches
