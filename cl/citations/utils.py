from datetime import date

from django.apps import (  # Must use apps.get_model() to avoid circular import issue
    apps,
)
from django.db.models import Sum
from django.template.defaultfilters import slugify
from django.utils.safestring import SafeString
from eyecite.models import CitationBase, FullCaseCitation, ShortCaseCitation
from eyecite.utils import strip_punct
from reporters_db import EDITIONS, VARIATIONS_ONLY

QUERY_LENGTH = 10
SLUGIFIED_EDITIONS: dict[str, str] = {
    str(slugify(item)): item for item in EDITIONS.keys()
}


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
) -> tuple[int, int]:
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


def make_name_param(
    defendant: str,
    plaintiff: str | None = None,
) -> tuple[str, int]:
    """Remove punctuation and return cleaned string plus its length in tokens."""
    token_list = defendant.split()
    if plaintiff:
        token_list.extend(plaintiff.split())

    # Strip out punctuation, which Solr doesn't like
    query_words = [strip_punct(t) for t in token_list]
    return " ".join(query_words), len(query_words)


def get_canonicals_from_reporter(reporter_slug: str) -> list[SafeString]:
    """
    Disambiguates a reporter slug using a list of variations.

    The list of variations is a dictionary that maps each variation
    to a list of reporters that it could be possibly referring to.

    Args:
        reporter_slug (str): The reporter's name in slug format

    Returns:
        list[str]: A list of potential canonical names for the reporter
    """
    slugified_variations = {}
    for variant, canonicals in VARIATIONS_ONLY.items():
        slugged_canonicals = []
        for canonical in canonicals:
            slugged_canonicals.append(slugify(canonical))
        slugified_variations[str(slugify(variant))] = slugged_canonicals

    return slugified_variations.get(reporter_slug, [])


def filter_out_non_case_law_citations(
    citations: list[CitationBase],
) -> list[FullCaseCitation | ShortCaseCitation]:
    """
    Filters out all non-case-law citations from a list of citations.

    Args:
        citations (list[CitationBase]): List of citation

    Returns:
        list[FullCaseCitation | ShortCaseCitation]: List of case law citations.
    """
    return [
        c
        for c in citations
        if isinstance(c, (FullCaseCitation, ShortCaseCitation))
    ]
