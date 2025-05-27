import logging
from datetime import date

from django.apps import (  # Must use apps.get_model() to avoid circular import issue
    apps,
)
from django.db.models import Sum
from django.template.defaultfilters import slugify
from django.utils.functional import keep_lazy_text
from django.utils.safestring import SafeString
from eyecite.models import CitationBase, FullCaseCitation, ShortCaseCitation
from eyecite.utils import strip_punct
from reporters_db import EDITIONS, REPORTERS, VARIATIONS_ONLY

from cl.citations.models import UnmatchedCitation
from cl.citations.types import MatchedResourceType, SupportedCitationType
from cl.search.models import Opinion

QUERY_LENGTH = 10
NAIVE_SLUGIFIED_EDITIONS = {str(slugify(item)): item for item in EDITIONS}

logger = logging.getLogger(__name__)


@keep_lazy_text
def slugify_reporter(reporter: str) -> str:
    """Slugify reporters preventing slug collision

    Some different reporter abbreviations may have their naive slug collide
    Examples where  one is the state reporter, the other a neutral reporter
    - 'Vt.' and 'VT': naive slug 'vt'
    - 'La.' and 'LA': naive slug 'la'

    Others: 'CIT' 'C.I.T.'; 'Day.' 'Day'; 'MSPB' 'M.S.P.B.'; 'Me.' 'ME';
    'ND' 'N.D.'; 'NM' 'N.M.'; 'Pa.' 'PA'; 'SD' 'S.D.'

    :param reporter: the reporter abbreviation, or a slug, or an user input
    :return: the collision-aware slug
    """
    slug = str(slugify(reporter))
    if slug == reporter:
        # return the already slugified reporter; this may happen on redirected
        # cl.opinion_page.views.citation_redirector
        return slug

    if NAIVE_SLUGIFIED_EDITIONS.get(slug, "") == reporter:
        # the slug and reporter match the naive mapper
        return slug

    # if the input string is actually a reporter, return a collision-aware slug
    if reporter in REPORTERS:
        return str(
            slugify(f"{reporter} {REPORTERS[reporter][0]['cite_type']}")
        )

    return slug


SLUGIFIED_EDITIONS = {slugify_reporter(item): item for item in EDITIONS}


def map_reporter_db_cite_type(citation_type: str) -> int:
    """Map a citation type from the reporters DB to CL Citation type

    :param citation_type: A value from REPORTERS['some-key']['cite_type']
    :return: A value from the search.models.Citation object
    """
    Citation = apps.get_model("search.Citation")
    citation_map = {
        "specialty": Citation.SPECIALTY,
        "journal": Citation.JOURNAL,
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
            end_year = edition_guess.end.year
    return start_year, end_year


def make_name_param(
    defendant: str,
    plaintiff: str | None = None,
) -> tuple[str, int]:
    """Remove punctuation and return cleaned string plus its length in tokens."""
    token_list = defendant.split()
    if plaintiff:
        token_list.extend(plaintiff.split())

    # Strip out punctuation
    query_words = [strip_punct(t) for t in token_list]
    return " ".join(query_words), len(query_words)


def get_canonicals_from_reporter(reporter_or_slug: str) -> list[SafeString]:
    """
    Disambiguates a reporter slug using a list of variations.

    The list of variations is a dictionary that maps each variation
    to a list of reporters that it could be possibly referring to.

    Args:
        reporter_or_slug: The reporter's name, which may be in slug format

    Returns:
        list[str]: A list of potential canonical names for the reporter
    """
    reporter_slug = slugify_reporter(reporter_or_slug)
    slugified_variations = {}
    for variant, canonicals in VARIATIONS_ONLY.items():
        slugged_canonicals = []
        for canonical in canonicals:
            slugged_canonicals.append(slugify_reporter(canonical))
        slugified_variations[str(slugify(variant))] = slugged_canonicals

    return slugified_variations.get(reporter_slug, [])


def filter_out_non_case_law_citations(
    citations: list[CitationBase],
) -> list[FullCaseCitation | ShortCaseCitation]:
    """
    Filters out all non-case law citations from a list of citations.

    Args:
        citations (list[CitationBase]): List of citation

    Returns:
        list[FullCaseCitation | ShortCaseCitation]: List of case law citations.
    """
    return [
        c
        for c in citations
        if isinstance(c, (FullCaseCitation | ShortCaseCitation))
    ]


def filter_out_non_case_law_and_non_valid_citations(
    citations: list[CitationBase],
) -> list[FullCaseCitation | ShortCaseCitation]:
    """
    Filters out all non-case law citations and citations with no volume or page
    from a list of citations.

    Args:
        citations (list[CitationBase]): List of citation

    Returns:
        list[FullCaseCitation | ShortCaseCitation]: List of case law citations.
    """
    return [
        c
        for c in citations
        if isinstance(c, (FullCaseCitation | ShortCaseCitation))
        and c.groups.get("volume", None)
        and c.groups.get("page", None)
    ]


def make_get_citations_kwargs(document) -> dict:
    """Prepare markup kwargs for `get_citations`

    This is done outside `get_citations` because it uses specific Opinion
    attributes used are set in Courtlistener, not in eyecite.

    :param document: The Opinion or RECAPDocument whose text should be parsed

    :return: a dictionary with kwargs for `get_citations`
    """
    kwargs = {}
    # We prefer CAP data (xml_harvard) first.
    for attr in [
        "xml_harvard",
        "html_anon_2020",
        "html_columbia",
        "html_lawbox",
        "html",
    ]:
        text = getattr(document, attr, None)
        if text:
            kwargs = {
                "markup_text": text,
                "clean_steps": ["xml", "html", "all_whitespace"],
            }
            break
    else:
        kwargs = {
            "plain_text": getattr(document, "plain_text"),
            "clean_steps": ["all_whitespace"],
        }

    return kwargs


def unmatched_citation_is_valid(
    citation: CitationBase, self_citations: list[str]
) -> bool:
    """"""
    if not isinstance(citation, FullCaseCitation):
        return False

    # handle bugs in eyecite that make it return FullCitations with null
    # values in required fields
    groups = citation.groups
    if (
        not groups.get("reporter")
        or not groups.get("volume")
        or not groups.get("page")
    ):
        logger.error(
            "Unexpected null value in FullCaseCitation %s",
            citation,
        )
        return False

    if not groups.get("volume").isdigit():
        logger.error(
            "Unexpected non-integer volume value in FullCaseCitation %s",
            citation,
        )
        return False

    # This would raise a DataError, we have seen cases from bad OCR or
    # citation lookalikes. See #5191
    if int(groups["volume"]) >= 32_767:
        return False

    # avoid storing self citations as unmatched; the self citation will
    # usually be found at the beginning of the opinion's text
    # Note that both Citation.__str__ and UnmatchedCitation.__str__ use
    # the standardized volume, reporter and page values, so they are
    # comparable
    citation_str = str(citation)
    if citation_str in self_citations:
        return False

    return True


def update_unmatched_citations_status(
    resolved_citations: set[str],
    existing_unmatched_citations: list[UnmatchedCitation],
) -> None:
    """Check if previously unmatched citations have been resolved and
    updates UnmatchedCitation.status accordingly

    We assume no new UnmatchedCitations will be created after the first run

    :param citation_resolutions: strings of resolved citations
    :param existing_unmatched_citations: list of existing UnmatchedCitation
        objects
    :return None:
    """
    # try to update the status of FOUND and FAILED_* UnmatchedCitations
    found_citations = [
        u
        for u in existing_unmatched_citations
        if u.status
        not in [UnmatchedCitation.UNMATCHED, UnmatchedCitation.RESOLVED]
    ]

    for found in found_citations:
        if found.citation_string in resolved_citations:
            found.status = UnmatchedCitation.RESOLVED
        else:
            if found.status in [
                UnmatchedCitation.FAILED,
                UnmatchedCitation.FAILED_AMBIGUOUS,
            ]:
                continue
            found.status = UnmatchedCitation.FAILED
        found.save()


def store_unmatched_citations(
    unmatched_citations: list[CitationBase],
    ambiguous_matches: list[CitationBase],
    opinion: Opinion,
) -> None:
    """Bulk create UnmatchedCitation instances cited by an opinion

    Only FullCaseCitations provide useful information for resolution
    updates. Other types are discarded

    :param unmatched_citations: citations with 0 matches
    :param ambiguous_matches: citations with more than 1 match
    :param opinion: the citing opinion
    :return None:
    """
    unmatched_citations_to_store = []
    seen_citations = set()

    for index, unmatched_citation in enumerate(
        unmatched_citations + ambiguous_matches, 1
    ):
        has_multiple_matches = index > len(unmatched_citations)

        citation_object = UnmatchedCitation.create_from_eyecite(
            unmatched_citation, opinion, has_multiple_matches
        )

        # use to prevent Integrity error from duplicates
        citation_str = str(citation_object)
        if citation_str in seen_citations:
            continue
        seen_citations.add(citation_str)

        unmatched_citations_to_store.append(citation_object)

    if unmatched_citations_to_store:
        UnmatchedCitation.objects.bulk_create(unmatched_citations_to_store)


def handle_unmatched_citations(
    citing_opinion: Opinion,
    unmatched_citations: list[CitationBase],
    ambiguous_matches: list[CitationBase],
    citation_resolutions: dict[
        MatchedResourceType, list[SupportedCitationType]
    ],
) -> None:
    """Store valid UnmatchedCitations or update their status

    :param citing_opinion: the cited opinion
    :param unmatched_citations: citations with 0 matches
    :param ambiguous_matches: citations with more than 1 match

    :return None
    """
    if not (unmatched_citations or ambiguous_matches):
        return

    self_citations = [str(c) for c in citing_opinion.cluster.citations.all()]
    valid_unmatched = [
        c
        for c in unmatched_citations
        if unmatched_citation_is_valid(c, self_citations)
    ]
    valid_ambiguous = [
        c
        for c in ambiguous_matches
        if unmatched_citation_is_valid(c, self_citations)
    ]

    if not (valid_unmatched or valid_ambiguous):
        return

    existing_unmatched_citations = list(
        UnmatchedCitation.objects.filter(citing_opinion=citing_opinion).all()
    )

    if not existing_unmatched_citations:
        store_unmatched_citations(
            valid_unmatched, valid_ambiguous, citing_opinion
        )
        return

    resolved_citations = {
        c.matched_text() for v in citation_resolutions.values() for c in v
    }

    update_unmatched_citations_status(
        resolved_citations, existing_unmatched_citations
    )

    # We can get new UnmatchedCitations when eyecite or reporters-db are
    # improved, so we need to compare existing UnmatchedCitation rows with
    # the new ones
    existing_unmatched_strings = {
        i.citation_string for i in existing_unmatched_citations
    }
    new_unmatched = [
        c
        for c in valid_unmatched
        if c.matched_text() not in existing_unmatched_strings
    ]
    new_ambiguous = [
        c
        for c in valid_ambiguous
        if c.matched_text() not in existing_unmatched_strings
    ]
    if new_unmatched or new_ambiguous:
        store_unmatched_citations(new_unmatched, new_ambiguous, citing_opinion)
