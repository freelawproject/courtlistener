#!/usr/bin/env python

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple, no_type_check

import waffle
from django.conf import settings
from elasticsearch_dsl.response import Response
from eyecite import resolve_citations
from eyecite.models import (
    CitationBase,
    FullCaseCitation,
    FullJournalCitation,
    FullLawCitation,
    Resource,
    ShortCaseCitation,
    SupraCitation,
)
from eyecite.test_factories import case_citation
from eyecite.utils import strip_punct
from requests import Session
from scorched.response import SolrResponse

from cl.citations.match_citations_queries import es_search_db_for_full_citation
from cl.citations.types import (
    MatchedResourceType,
    ResolvedFullCites,
    SupportedCitationType,
)
from cl.citations.utils import get_years_from_reporter
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.scorched_utils import ExtraSolrInterface, ExtraSolrSearch
from cl.lib.types import SearchParam
from cl.search.models import Opinion, RECAPDocument

DEBUG = True

QUERY_LENGTH = 10

NO_MATCH_RESOURCE = Resource(case_citation(source_text="UNMATCHED_CITATION"))


def build_date_range(start_year: int, end_year: int) -> str:
    """Build a date range to be handed off to a solr query."""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    date_range = f"[{start.isoformat()}Z TO {end.isoformat()}Z]"
    return date_range


def make_name_param(
    defendant: str,
    plaintiff: str | None = None,
) -> Tuple[str, int]:
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
    citing_opinion: Opinion,
) -> List[ExtraSolrSearch]:
    """Uses the case name of the found document to verify that it is a match on
    the original.
    """
    params: SearchParam = {"fq": [f"id:{citing_opinion.pk}"]}
    for result in results:
        case_name, length = make_name_param(result["caseName"])
        # Avoid overly long queries
        start = max(length - QUERY_LENGTH, 0)
        query_tokens = case_name.split()[start:]
        query = " ".join(query_tokens)
        # ~ performs a proximity search for the preceding phrase
        # See: http://wiki.apache.org/solr/SolrRelevancyCookbook#Term_Proximity
        params["q"] = f'"{query}"~{len(query_tokens)}'
        params["caller"] = "reverse_match"
        new_results = conn.query().add_extra(**params).execute()
        if len(new_results) == 1:
            return [result]
    return []


def case_name_query(
    conn: ExtraSolrInterface,
    params: SearchParam,
    citation: SupportedCitationType,
    citing_opinion: Opinion,
) -> List[ExtraSolrSearch]:
    query, length = make_name_param(
        citation.metadata.defendant, citation.metadata.plaintiff
    )
    params["q"] = f"caseName:({query})"
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
            return reverse_match(conn, new_results, citing_opinion)
            # Else, try again
        results = new_results
    return [results]


def search_db_for_fullcitation(
    full_citation: FullCaseCitation,
) -> SolrResponse:
    """For a citation object, try to match it to an item in the database using
    a variety of heuristics.
    Returns:
      - a Solr Result object with the results, or an empty list if no hits
    """
    if not hasattr(full_citation, "citing_opinion"):
        full_citation.citing_opinion = None

    # TODO: Create shared solr connection for all queries
    with Session() as session:
        si = ExtraSolrInterface(
            settings.SOLR_OPINION_URL, http_connection=session, mode="r"
        )
        main_params: SearchParam = {
            "q": "*",
            "fq": [
                "status:Precedential",  # Non-precedential documents aren't cited
            ],
            "caller": "citation.match_citations.match_citation",
        }
        if full_citation.citing_opinion is not None:
            # Eliminate self-cites.
            main_params["fq"].append(f"-id:{full_citation.citing_opinion.pk}")
        # Set up filter parameters
        if full_citation.year:
            start_year = end_year = full_citation.year
        else:
            start_year, end_year = get_years_from_reporter(full_citation)
            if (
                full_citation.citing_opinion is not None
                and full_citation.citing_opinion.cluster.date_filed
            ):
                end_year = min(
                    end_year,
                    full_citation.citing_opinion.cluster.date_filed.year,
                )
        main_params["fq"].append(
            f"dateFiled:{build_date_range(start_year, end_year)}"
        )

        if full_citation.metadata.court:
            main_params["fq"].append(
                f"court_exact:{full_citation.metadata.court}"
            )

        # Take 1: Use a phrase query to search the citation field.
        main_params["fq"].append(
            f'citation:("{full_citation.corrected_citation()}")'
        )
        results = si.query().add_extra(**main_params).execute()
        if len(results) == 1:
            return results
        if len(results) > 1:
            if (
                full_citation.citing_opinion is not None
                and full_citation.metadata.defendant
            ):  # Refine using defendant, if there is one
                results = case_name_query(
                    si,
                    main_params,
                    full_citation,
                    full_citation.citing_opinion,
                )
                return results

    # Give up.
    return []


def filter_by_matching_antecedent(
    opinion_candidates: Iterable[Opinion],
    antecedent_guess: Optional[str],
) -> Optional[Opinion]:
    if not antecedent_guess:
        return None

    antecedent_guess = strip_punct(antecedent_guess)
    candidates: List[Opinion] = []

    for o in opinion_candidates:
        if antecedent_guess in best_case_name(o.cluster):
            candidates.append(o)

    # Remove duplicates and only accept if one candidate remains
    candidates = list(set(candidates))
    return candidates[0] if len(candidates) == 1 else None


def resolve_fullcase_citation(
    full_citation: FullCaseCitation,
) -> MatchedResourceType:
    # Case 1: FullCaseCitation
    if type(full_citation) is FullCaseCitation:
        if waffle.switch_is_active("es_resolve_citations"):
            # Revolve citations using ES; enable once all the opinions are
            # indexed.
            db_search_results: Response = es_search_db_for_full_citation(
                full_citation
            )
        else:
            db_search_results: SolrResponse = search_db_for_fullcitation(
                full_citation
            )
        # If there is one search result, try to return it
        if len(db_search_results) == 1:
            result_id = db_search_results[0]["id"]
            try:
                return Opinion.objects.get(pk=result_id)
            except (Opinion.DoesNotExist, Opinion.MultipleObjectsReturned):
                pass

    # Case 2: FullLawCitation (TODO: implement support)
    elif type(full_citation) is FullLawCitation:
        pass

    # Case 3: FullJournalCitation (TODO: implement support)
    elif type(full_citation) is FullJournalCitation:
        pass

    # If no Opinion can be matched, just return a placeholder object
    return NO_MATCH_RESOURCE


def resolve_shortcase_citation(
    short_citation: ShortCaseCitation,
    resolved_full_cites: ResolvedFullCites,
) -> Optional[Opinion]:
    candidates: List[Opinion] = []
    matched_opinions = [
        o for c, o in resolved_full_cites if type(o) is Opinion
    ]
    for opinion in matched_opinions:
        for c in opinion.cluster.citations.all():
            if (
                short_citation.corrected_reporter() == c.reporter
                and short_citation.groups["volume"] == str(c.volume)
            ):
                candidates.append(opinion)

    # Remove duplicates
    candidates = list(set(candidates))

    # Only accept if one candidate remains
    if len(candidates) == 1:
        return candidates[0]

    # Otherwise, try to refine further using the antecedent guess
    else:
        return filter_by_matching_antecedent(
            candidates, short_citation.metadata.antecedent_guess
        )


def resolve_supra_citation(
    supra_citation: SupraCitation,
    resolved_full_cites: ResolvedFullCites,
) -> Optional[Opinion]:
    matched_opinions = [
        o for c, o in resolved_full_cites if type(o) is Opinion
    ]
    return filter_by_matching_antecedent(
        matched_opinions, supra_citation.metadata.antecedent_guess
    )


@no_type_check
def do_resolve_citations(
    citations: List[CitationBase], citing_object: Opinion | RECAPDocument
) -> Dict[MatchedResourceType, List[SupportedCitationType]]:
    # Set the citing opinion on FullCaseCitation objects for later matching
    for c in citations:
        if type(c) is FullCaseCitation:
            if isinstance(citing_object, Opinion):
                c.citing_opinion = citing_object
            elif isinstance(citing_object, RECAPDocument):
                # if the object doing the citing is a RECAPDocument,
                # refer to it as a citing document.
                c.citing_document = citing_object
            else:
                raise "Unknown citing type."

    # Call and return eyecite's resolve_citations() function
    return resolve_citations(
        citations=citations,
        resolve_full_citation=resolve_fullcase_citation,
        resolve_shortcase_citation=resolve_shortcase_citation,
        resolve_supra_citation=resolve_supra_citation,
    )
