from typing import Dict, List, Tuple

from django.db import transaction
from eyecite import get_citations
from eyecite.models import CitationBase

from cl.citations.annotate_citations import get_and_clean_opinion_text
from cl.citations.match_citations import (
    NO_MATCH_RESOURCE,
    do_resolve_citations,
)
from cl.lib.types import MatchedResourceType, SupportedCitationType
from cl.search.models import OpinionsCitedByRECAPDocument, RECAPDocument


def store_recap_citations(document: RECAPDocument) -> None:
    """
    Identify citations from federal filings to opinions.

    :param document: A search.RECAPDocument object.

    :return: None
    """

    get_and_clean_opinion_text(
        document
    )  # even though this function assumes the input is an opinion, it will work for RECAP documents.

    # Extract the citations from the document's text
    citations: List[CitationBase] = get_citations(document.cleaned_text)

    # If no citations are found, then there is nothing else to do for now.
    if not citations:
        return

    # Resolve all those different citation objects to Opinion objects,
    # using a variety of heuristics.
    citation_resolutions: Dict[
        MatchedResourceType, List[SupportedCitationType]
    ] = do_resolve_citations(citations, document)

    # Delete the unmatched citations
    citation_resolutions.pop(NO_MATCH_RESOURCE, None)

    with transaction.atomic():
        # delete existing citation entries
        OpinionsCitedByRECAPDocument.objects.filter(
            citing_document=document.pk
        ).delete()

        objects_to_create = [
            OpinionsCitedByRECAPDocument(
                citing_document_id=document.pk,
                cited_opinion_id=opinion_object.pk,
                depth=len(cits),
            )
            for opinion_object, cits in citation_resolutions.items()
        ]

        OpinionsCitedByRECAPDocument.objects.bulk_create(objects_to_create)


def get_recap_citations(
    recap_doc_id: int, top_k: int | None = None
) -> Tuple[int, List[OpinionsCitedByRECAPDocument]]:
    """
    The purpose of this function is to retrieve the OpinionClusters for Opinions cited
    within a given RECAPDocument. Because of how Django ORM works,
    it returns the citation record object with the associated Opinion and Cluster
    also loaded in memory.
    If top_k is provided -> returns the objects for the k most-cited opinions.
    """
    query = (
        OpinionsCitedByRECAPDocument.objects.filter(
            citing_document_id=recap_doc_id
        )
        .select_related("cited_opinion__cluster__docket__court")
        .prefetch_related(
            "cited_opinion__cluster__citations",
        )
        .only(
            "depth",
            "cited_opinion__cluster__slug",
            "cited_opinion__cluster__case_name",
            "cited_opinion__cluster__case_name_full",
            "cited_opinion__cluster__case_name_short",
            "cited_opinion__cluster__docket_id",
            "cited_opinion__cluster__date_filed",
            "cited_opinion__cluster__docket__docket_number",
            "cited_opinion__cluster__docket__court_id",
            "cited_opinion__cluster__docket__court__citation_string",
        )
        .order_by("-depth")
    )
    total_count = query.count()

    if top_k:
        return total_count, query[:top_k]

    return total_count, list(query)
