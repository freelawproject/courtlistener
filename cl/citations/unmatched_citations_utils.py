import logging

from eyecite.models import CitationBase, FullCaseCitation

from cl.citations.models import UnmatchedCitation
from cl.citations.types import MatchedResourceType, SupportedCitationType
from cl.search.models import Opinion

logger = logging.getLogger(__name__)


def unmatched_citation_is_valid(
    citation: CitationBase, self_citations: list[str]
) -> bool:
    """Check if an eyecite citation is valid to create an UnmatchedCitation

    :param citation: the citation to check for validity
    :param self_citations: list of citations to the cluster
    :return: True if valid
    """
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
    if citation.corrected_citation() in self_citations:
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
