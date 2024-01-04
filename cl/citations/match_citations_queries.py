#!/usr/bin/env python

from elasticsearch_dsl import Q
from elasticsearch_dsl.response import Response
from eyecite.models import FullCaseCitation

from cl.citations.utils import get_years_from_reporter
from cl.search.documents import OpinionClusterDocument


def es_search_db_for_full_citation(
    full_citation: FullCaseCitation,
) -> Response:
    """For a citation object, try to match it to an item in the database using
    a variety of heuristics.
    :param full_citation: A FullCaseCitation instance.
    return: A ElasticSearch Result object with the results, or an empty list if
     no hits
    """

    if not hasattr(full_citation, "citing_opinion"):
        full_citation.citing_opinion = None
    search_query = OpinionClusterDocument.search()
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
                "lte": f"{end_year}-01-01T00:00:00Z",
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
    results = citations_query.execute()
    if len(results) == 1:
        return results
    if len(results) > 1:
        if (
            full_citation.citing_opinion is not None
            and full_citation.metadata.defendant
        ):  # TODO Refine using defendant, if there is one
            pass

    # Give up.
    return []
