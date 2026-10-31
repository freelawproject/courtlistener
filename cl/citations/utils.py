from datetime import date
from typing import TYPE_CHECKING

from django.apps import (  # Must use apps.get_model() to avoid circular import issue
    apps,
)
from django.db.models import Q, Sum
from django.template.defaultfilters import slugify
from django.utils.functional import keep_lazy_text
from eyecite.models import CitationBase, FullCaseCitation, ShortCaseCitation
from eyecite.utils import strip_punct
from reporters_db import EDITIONS, REPORTERS, VARIATIONS_ONLY

if TYPE_CHECKING:
    from cl.search.models import Opinion, RECAPDocument

QUERY_LENGTH = 10
NAIVE_SLUGIFIED_EDITIONS = {str(slugify(item)): item for item in EDITIONS}


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

    # final fallback check for known variations
    if reporter in VARIATIONS_ONLY and len(VARIATIONS_ONLY[reporter]) == 1:
        return slugify(VARIATIONS_ONLY[reporter][0])

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


def get_canonicals_from_reporter(reporter_or_slug: str) -> list[str]:
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


def chunk_text(text: str, chunk_size: int):
    """Chunk text with overlapping chunks to avoid misses

    :param text: Text to chunk
    :param chunk_size: The chunk size
    :return: Chunks of text
    """
    if len(text) <= chunk_size:
        yield text
        return
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            yield text[start:]
            break
        yield text[start:end]
        start += chunk_size


# The Opinion text sources tried, in order, when building
# ``html_with_citations``. The first non-empty field wins, so a source is only
# used when every field above it is empty. Note that ``html_lawbox`` outranks
# only scraped content (``html``) and ``plain_text``: the Harvard, Columbia,
# scanning-project and anonymous-archive corpora all take precedence over it.
CITATION_SOURCE_FIELDS: tuple[str, ...] = (
    "xml_harvard",
    "xml_scan",
    "html_anon_2020",
    "html_columbia",
    "html_lawbox",
    "html",
    "plain_text",
)

#: The sources that outrank ``html_lawbox``. If any of these is non-empty on an
#: Opinion, its ``html_with_citations`` was *not* derived from ``html_lawbox``.
FIELDS_PREFERRED_OVER_LAWBOX: tuple[str, ...] = CITATION_SOURCE_FIELDS[
    : CITATION_SOURCE_FIELDS.index("html_lawbox")
]


def lawbox_is_citation_source_filter() -> Q:
    """Build a filter for Opinions whose ``html_with_citations`` derives from
    ``html_lawbox``.

    This is the database-level mirror of :func:`lawbox_is_citation_source` and
    reuses the same ordering as :func:`make_get_citations_kwargs`, so the two
    cannot drift apart. Evaluating it in SQL also keeps the text columns out of
    Python, which matters when a caller is scanning a corpus-wide set of
    Opinions.

    Use it to decide whether re-running citation annotation for a repaired
    ``html_lawbox`` is worthwhile: an opinion that prefers another corpus would
    just regenerate the same ``html_with_citations`` from that other source.

    :return: A ``Q`` object matching Opinions with a non-empty ``html_lawbox``
        and no higher-priority text source.
    """
    preferred_empty = Q()
    for field in FIELDS_PREFERRED_OVER_LAWBOX:
        # These TextFields are blank rather than null in this schema, but stay
        # permissive: make_get_citations_kwargs treats None and "" alike.
        preferred_empty &= Q(**{f"{field}__isnull": True}) | Q(**{field: ""})
    return preferred_empty & ~Q(html_lawbox="")


def lawbox_is_citation_source(opinion: "Opinion") -> bool:
    """Whether ``opinion``'s ``html_with_citations`` is derived from
    ``html_lawbox``.

    In-memory mirror of :func:`lawbox_is_citation_source_filter`, for callers
    that already hold an Opinion and for tests.

    :param opinion: The Opinion to inspect.
    :return: True if ``html_lawbox`` is the source annotation uses (or would
        use) for this opinion.
    """
    if not getattr(opinion, "html_lawbox", None):
        return False
    return not any(
        getattr(opinion, field, None) for field in FIELDS_PREFERRED_OVER_LAWBOX
    )


def make_get_citations_kwargs(
    document: "RECAPDocument | Opinion", chunk_size: int = 200_000
) -> list[dict]:
    """Prepare markup kwargs for `get_citations` - chunked

    This is done outside `get_citations` because it uses specific Opinion
    attributes used are set in Courtlistener, not in eyecite.

    :param document: The Opinion or RECAPDocument whose text should be parsed
    :param chunk_size: The chunk size
    :return: a list dict kwargs for `get_citations`
    """
    segments = []
    for attr in CITATION_SOURCE_FIELDS:
        text = getattr(document, attr, None)
        if not text:
            continue
        for chunk in chunk_text(text, chunk_size=chunk_size):
            if attr == "plain_text":
                kwargs = {
                    "plain_text": chunk,
                    "clean_steps": ["all_whitespace"],
                }
            else:
                kwargs = {
                    "markup_text": chunk,
                    "clean_steps": ["xml", "html", "all_whitespace"],
                }
            segments.append(kwargs)
        break
    return segments


def get_cited_clusters_ids_to_update(
    resolutions, citing_opinion_id: int
) -> list[int]:
    """Get ids for clusters that need their `citation_count` updated

    Increase the citation count for the cluster of each matched opinion
    if that cluster has not already been cited by this opinion.

    :param resolutions: an iterable of opinion objects
    :param citing_opinion_id: the citing opinion

    :return: the list of OpinionCluster ids for update
    """
    # prevent circular imports
    OpinionsCited = apps.get_model("search.OpinionsCited")

    currently_cited_opinions = OpinionsCited.objects.filter(
        citing_opinion_id=citing_opinion_id
    ).values_list("cited_opinion_id", flat=True)

    cluster_ids_to_update = {
        o.cluster_id
        for o in resolutions
        if o.pk not in currently_cited_opinions
    }
    return list(cluster_ids_to_update)
