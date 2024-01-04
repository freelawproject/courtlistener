from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Tuple, no_type_check

from django.apps import (  # Must use apps.get_model() to avoid circular import issue
    apps,
)
from django.db.models import Sum
from eyecite.models import FullCaseCitation


def map_reporter_db_cite_type(citation_type: str) -> int:
    """Map a citation type from the reporters DB to CL Citation type

    :param citation_type: A value from REPORTERS['some-key']['cite_type']
    :return: A value from the search.models.Citation object
    """
    Citation = apps.get_model("search.Citation")
    citation_map = {
        "specialty": Citation.SPECIALTY,
        "federal": Citation.FEDERAL,
        "state": Citation.STATE,
        "state_regional": Citation.STATE_REGIONAL,
        "neutral": Citation.NEUTRAL,
        "specialty_lexis": Citation.LEXIS,
        "specialty_west": Citation.WEST,
        "scotus_early": Citation.SCOTUS_EARLY,
    }
    return citation_map[citation_type]


async def get_citation_depth_between_clusters(
    citing_cluster_pk: int, cited_cluster_pk: int
) -> int:
    """OpinionsCited objects exist as relationships between Opinion objects,
    but we often want access to citation depth information between
    OpinionCluster objects. This helper method assists in doing the necessary
    DB lookup.

    :param citing_cluster_pk: The primary key of the citing OpinionCluster
    :param cited_cluster_pk: The primary key of the cited OpinionCluster
    :return: The sum of all the depth fields of the OpinionsCited objects
        associated with the Opinion objects associated with the given
        OpinionCited objects
    """
    OpinionsCited = apps.get_model("search.OpinionsCited")
    result = await OpinionsCited.objects.filter(
        citing_opinion__cluster__pk=citing_cluster_pk,
        cited_opinion__cluster__pk=cited_cluster_pk,
    ).aaggregate(depth=Sum("depth"))
    return result["depth"]


def get_years_from_reporter(
    citation: FullCaseCitation,
) -> Tuple[int, int]:
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
