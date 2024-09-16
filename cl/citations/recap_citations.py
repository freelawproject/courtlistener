from typing import Dict, List

from django.db import transaction
from eyecite import get_citations
from eyecite.models import CitationBase
from eyecite.tokenizers import HyperscanTokenizer

from cl.citations.annotate_citations import get_and_clean_opinion_text
from cl.citations.match_citations import (
    NO_MATCH_RESOURCE,
    do_resolve_citations,
)
from cl.citations.types import MatchedResourceType, SupportedCitationType
from cl.search.models import OpinionsCitedByRECAPDocument, RECAPDocument
from cl.search.tasks import index_related_cites_fields

HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


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
    citations: List[CitationBase] = get_citations(
        document.cleaned_text, tokenizer=HYPERSCAN_TOKENIZER
    )

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

    # Update changes in ES.
    index_related_cites_fields.delay(
        OpinionsCitedByRECAPDocument.__name__,
        document.pk,
    )
