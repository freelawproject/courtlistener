from django.db import transaction
from eyecite import get_citations
from eyecite.models import CitationBase
from eyecite.tokenizers import HyperscanTokenizer

from cl.citations.match_citations import (
    MULTIPLE_MATCHES_RESOURCE,
    NO_MATCH_RESOURCE,
    do_resolve_citations,
)
from cl.citations.types import MatchedResourceType, SupportedCitationType
from cl.citations.utils import make_get_citations_kwargs
from cl.search.documents import ESRECAPDocument
from cl.search.models import OpinionsCitedByRECAPDocument, RECAPDocument
from cl.search.tasks import index_related_cites_fields, percolate_document

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


def store_recap_citations(document: RECAPDocument) -> None:
    """
    Identify citations from federal filings to opinions.

    :param document: A search.RECAPDocument object.

    :return: None
    """
    # Extract the citations from the document's text
    citations: list[CitationBase] = get_citations(
        tokenizer=HYPERSCAN_TOKENIZER, **make_get_citations_kwargs(document)
    )

    # If no citations are found, abort the resolution process, but perform
    # the RECAPDocument percolation before aborting, since the percolation
    # was previously delayed.
    if not citations:
        percolate_document(ESRECAPDocument, document.pk, document)
        return

    # Resolve all those different citation objects to Opinion objects,
    # using a variety of heuristics.
    citation_resolutions: dict[
        MatchedResourceType, list[SupportedCitationType]
    ] = do_resolve_citations(citations, document)

    # Delete the unmatched citations
    citation_resolutions.pop(NO_MATCH_RESOURCE, None)

    # Delete multiple matches citations
    citation_resolutions.pop(MULTIPLE_MATCHES_RESOURCE, None)

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

    # Update changes in ES.
    index_related_cites_fields.delay(
        OpinionsCitedByRECAPDocument.__name__,
        document.pk,
    )
