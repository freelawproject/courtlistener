#!/usr/bin/env python

from django_elasticsearch_dsl.search import Search
from elasticsearch_dsl import Q
from elasticsearch_dsl.query import Query
from elasticsearch_dsl.response import Hit, Response
from eyecite import get_citations
from eyecite.models import FullCaseCitation
from eyecite.tokenizers import HyperscanTokenizer
from natsort import natsort

from cl.citations.types import SupportedCitationType
from cl.citations.utils import (
    QUERY_LENGTH,
    get_years_from_reporter,
    make_name_param,
)
from cl.lib.types import CleanData
from cl.search.documents import OpinionDocument
from cl.search.models import Opinion

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


def fetch_citations(search_query: Search, fields=None) -> list[Hit]:
    """Fetches citation matches from Elasticsearch based on the provided
    search query.

    :param search_query: The Elasticsearch DSL Search object.
    :param fields: fields to return
    :return: A list of ES Hits objects.
    """

    if fields is None:
        fields = ["id", "caseName", "absolute_url", "dateFiled"]
    citation_hits = []
    search_query = search_query.sort("id")
    # Only retrieve fields required for the lookup.
    search_query = search_query.source(includes=fields)
    # Citation resolution aims for a single match. Setting up a size of 2 is
    # enough to determine if there is more than one match.
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

        reverse_query = Q(
            "bool",
            must=Q(
                "query_string",
                fields=["text"],
                query=value,
                quote_field_suffix=".exact",
                default_operator="AND",
                type="phrase",
            ),
            filter=[
                Q("term", id=citing_opinion.pk),
                Q("match", cluster_child="opinion"),
            ],
        )
        search = opinion_document.query(reverse_query)
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
    full_citation: FullCaseCitation, query_citation: bool = False
) -> tuple[list[Hit], bool]:
    """For a citation object, try to match it to an item in the database using
    a variety of heuristics.
    :param full_citation: A FullCaseCitation instance.
    :param query_citation: Whether this is related to es_get_query_citation
    resolution
    return: A two tuple, the ElasticSearch Result object with the results, or an empty list if
     no hits and a boolean indicating whether the citation was found.
    """

    if not hasattr(full_citation, "citing_opinion"):
        full_citation.citing_opinion = None
    search_query = OpinionDocument.search()
    filters = [
        Q(
            "term", **{"status.raw": "Published"}
        ),  # Non-precedential documents aren't cited
    ]

    if query_citation:
        # If this is related to query citation resolution, look for
        # opinion_cluster to determine if a citation matched a single cluster.
        filters.append(Q("match", cluster_child="opinion_cluster"))
    else:
        filters.append(Q("match", cluster_child="opinion"))

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
    citation_found = True if len(results) > 0 else False
    if len(results) == 1:
        return results, citation_found
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
            return results, citation_found
    else:
        # We didn't get an exact match on the volume/reporter/page. Perhaps
        # it's a pincite. Find closest citations filtering by volume and
        # reporter and excluding self cites.
        partial_citation_str = " ".join(
            [full_citation.groups["volume"], full_citation.groups["reporter"]]
        )
        filters = [
            Q(
                "match_phrase",
                **{"citation.exact": partial_citation_str},
            )
        ]
        query = Q("bool", must_not=must_not, filter=filters)
        citations_query = search_query.query(query)
        results = fetch_citations(
            citations_query, fields=["id", "cluster_id", "citation", "text"]
        )
        closest_opinion_clusters = []

        # Create a temporal item and add it to the values list (cluster_id,
        # page)
        citation_item = (0, full_citation.groups["page"])
        closest_opinion_clusters.append(citation_item)

        for result in results:
            # Get the citations from OpinionDocument that matched the partial
            # citation
            valid_citations = [
                get_citations(citation)[0]
                for citation in result["citation"]
                if partial_citation_str in citation and get_citations(citation)
            ]

            for valid_citation in valid_citations:
                closest_opinion_clusters.append(
                    (result["cluster_id"], valid_citation.groups["page"])
                )

        if len(closest_opinion_clusters) > 1:
            # Order by page number
            sort_possible_matches = natsort.natsorted(
                closest_opinion_clusters, key=lambda item: item[1]
            )
            # Find te index of the temporal item
            citation_item_position = sort_possible_matches.index(citation_item)

            if citation_item_position > 0:
                # if the position is greater than 0, then the previous item in
                # the list is the closest citation, we get the cluster id of the
                # previous item
                possible_cluster_id_matched = sort_possible_matches[
                    citation_item_position - 1
                ][0]

                # We filter the results list to get the possible match
                # OpinionDocument
                filtered_results = [
                    hit
                    for hit in results
                    if hit.cluster_id == possible_cluster_id_matched
                ]

                if (
                    len(filtered_results) == 1
                    and f"*{full_citation.groups["page"]}"
                    in filtered_results[0]["text"]
                ):
                    # Check if the page number is in the opinion text, currently
                    # we only look for this format: *page_number
                    # We add a temporary extra attribute to know that we got
                    # the match using a pin cite
                    filtered_results[0].pincite_used = full_citation.groups[
                        "page"
                    ]
                    return [filtered_results[0]], True
                for result in filtered_results:
                    # We could have clusters with multiple opinions, we need
                    # to check if the page number is in any of the opinions
                    if f"*{full_citation.groups['page']}" in result["text"]:
                        # We found the page number in the opinion content
                        filtered_results[0].pincite_used = (
                            full_citation.groups["page"]
                        )
                        return [result], True

    # Give up.
    return [], citation_found


def es_get_query_citation(
    cd: CleanData,
) -> tuple[Hit | None, list[FullCaseCitation]]:
    """Extract citations from the query. If it's a single citation, search for
     it into ES, and if found, return it.

    :param cd: A CleanData instance.
    :param return: A two tuple the ES Hit object or None and the list of
    missing citations from the query.
    """
    missing_citations: list[FullCaseCitation] = []
    if not cd.get("q"):
        return None, missing_citations
    citations = get_citations(cd["q"], tokenizer=HYPERSCAN_TOKENIZER)
    citations = [c for c in citations if isinstance(c, FullCaseCitation)]

    matches = None
    for citation in citations:
        matches, citation_found = es_search_db_for_full_citation(
            citation, query_citation=True
        )
        if not citation_found:
            missing_citations.append(citation)

    if len(citations) == 1 and matches and len(matches) == 1:
        # If more than one match, don't show the tip
        return matches[0], missing_citations
    return matches, missing_citations
