#!/usr/bin/env python

from django_elasticsearch_dsl.search import Search
from elasticsearch_dsl import Q
from elasticsearch_dsl.query import Query
from elasticsearch_dsl.response import Hit, Response
from eyecite.models import FullCaseCitation

from cl.citations.types import SupportedCitationType
from cl.citations.utils import (
    QUERY_LENGTH,
    get_years_from_reporter,
    make_name_param,
)
from cl.lib.elasticsearch_utils import build_fulltext_query
from cl.search.constants import CITATION_REVERSE_MATCH_LOOK_UP_FIELDS
from cl.search.documents import OpinionDocument
from cl.search.models import Opinion


def fetch_citations(search_query: Search) -> list[Hit]:
    """Fetches all citation matches from Elasticsearch based on the provided
    search query.

    :param search_query: The Elasticsearch DSL Search object.
    :return: A list of ES Hits objects.
    """

    citation_hits = []
    search_query = search_query.sort("id")
    # Only retrieve fields required for the lookup.
    search_query = search_query.source(includes=["id", "caseName"])
    search_query = search_query.extra(size=2)
    response = search_query.execute()
    citation_hits.extend(response.hits)
    return citation_hits


def es_reverse_match(
    results: list[Hit],
    citing_opinion: Opinion,
) -> list[Hit]:
    """Elasticsearch method that uses the case name of the found document to
    verify that it is a match on the original.

    :param results: The Response object containing search results.
    :param citing_opinion: The citing opinion to confirm the reverse match.
    :return: A list of OpinionDocument matched.
    """
    opinion_document = OpinionDocument.search()
    for result in results:
        case_name, length = make_name_param(result["caseName"])
        # Avoid overly long queries
        start = max(length - QUERY_LENGTH, 0)
        query_tokens = case_name.split()[start:]
        query = " ".join(query_tokens)
        # Construct a proximity query_string
        # ~ performs a proximity search for the preceding phrase
        # See: https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-query-string-query.html#_proximity_searches
        value = f'"{query}"~{len(query_tokens)}'
        # Create a search object with the query
        search = opinion_document.query(
            build_fulltext_query(CITATION_REVERSE_MATCH_LOOK_UP_FIELDS, value)
        )
        search = search.filter("term", id=citing_opinion.pk)
        new_response = fetch_citations(search)
        if len(new_response) == 1:
            return [result]
    return []


def es_case_name_query(
    search_query: Query,
    citation: SupportedCitationType,
    citing_opinion: Opinion,
) -> Response | list[Hit]:
    """Execute an Elasticsearch query to find case names based on a given
    citation and citing opinion.

    :param search_query: The base query to perform the search.
    :param citation: The citation object containing metadata about the case.
    :param citing_opinion: The opinion object where the case name should appear

    :return: A elasticsearch Response object with the search results or a list
    of OpinionDocument objects if matches are found.
    """
    query, length = make_name_param(
        citation.metadata.defendant, citation.metadata.plaintiff
    )
    # Use an Elasticsearch minimum_should_match query, starting with requiring
    # all words to match and decreasing by one word each time until a match is
    # found
    opinion_document = OpinionDocument.search()
    new_response = []
    for num_words in range(length, 0, -1):
        case_name_query = Q(
            "match",
            caseName={"query": query, "minimum_should_match": f"{num_words}"},
        )
        # Combine the base params query with the case_name_query, using a must
        # clause
        combined_query = search_query & case_name_query
        search = opinion_document.query(combined_query)
        new_response = fetch_citations(search)
        if len(new_response) >= 1:
            # For 1 result, make sure case name of match actually appears in
            # citing doc. For multiple results, use same technique to
            # potentially narrow down
            return es_reverse_match(new_response, citing_opinion)
    return new_response


def es_search_db_for_full_citation(
    full_citation: FullCaseCitation,
) -> list[Hit]:
    """For a citation object, try to match it to an item in the database using
    a variety of heuristics.
    :param full_citation: A FullCaseCitation instance.
    return: A ElasticSearch Result object with the results, or an empty list if
     no hits
    """

    if not hasattr(full_citation, "citing_opinion"):
        full_citation.citing_opinion = None
    search_query = OpinionDocument.search()
    filters = [
        Q(
            "term", **{"status.raw": "Published"}
        ),  # Non-precedential documents aren't cited
        Q("match", cluster_child="opinion"),
    ]
    must_not = []
    if full_citation.citing_opinion is not None:
        # Eliminate self-cites.
        must_not.append(Q("match", id=full_citation.citing_opinion.pk))
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

    filters.append(
        Q(
            "range",
            dateFiled={
                "gte": f"{start_year}-01-01T00:00:00Z",
                "lte": f"{end_year}-12-31T23:59:59Z",
            },
        )
    )
    if full_citation.metadata.court:
        filters.append(
            (Q("term", **{"court_id.raw": full_citation.metadata.court}))
        )

    # Take 1: Use a phrase query to search the citation field.
    filters.append(
        Q(
            "match_phrase",
            **{"citation.exact": full_citation.corrected_citation()},
        )
    )
    query = Q("bool", must_not=must_not, filter=filters)
    citations_query = search_query.query(query)
    results = fetch_citations(citations_query)
    if len(results) == 1:
        return results
    if len(results) > 1:
        if (
            full_citation.citing_opinion is not None
            and full_citation.metadata.defendant
        ):
            results = es_case_name_query(
                query,
                full_citation,
                full_citation.citing_opinion,
            )
            return results

    # Give up.
    return []
