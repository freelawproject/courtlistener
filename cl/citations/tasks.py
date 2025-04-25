import html
import logging
from http.client import ResponseNotReady
from typing import Dict, List, Set, Tuple

from django.db import transaction
from django.db.models import F
from django.db.models.query import QuerySet
from eyecite import get_citations
from eyecite.models import CitationBase, FullCaseCitation
from eyecite.tokenizers import HyperscanTokenizer

from cl.celery_init import app
from cl.citations.annotate_citations import create_cited_html
from cl.citations.filter_parentheticals import (
    clean_parenthetical_text,
    is_parenthetical_descriptive,
)
from cl.citations.match_citations import (
    MULTIPLE_MATCHES_RESOURCE,
    NO_MATCH_RESOURCE,
    do_resolve_citations,
)
from cl.citations.models import UnmatchedCitation
from cl.citations.parenthetical_utils import create_parenthetical_groups
from cl.citations.recap_citations import store_recap_citations
from cl.citations.score_parentheticals import parenthetical_score
from cl.citations.types import MatchedResourceType, SupportedCitationType
from cl.citations.utils import make_get_citations_kwargs
from cl.search.models import (
    Opinion,
    OpinionCluster,
    OpinionsCited,
    Parenthetical,
    RECAPDocument,
)
from cl.search.tasks import index_related_cites_fields

logger = logging.getLogger()

# This is the distance two reporter abbreviations can be from each other if
# they are considered parallel reporters. For example,
# "22 U.S. 44, 46 (13 Atl. 33)" would have a distance of 6.
PARALLEL_DISTANCE = 6
HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


@app.task
def identify_parallel_citations(
    citations: List[SupportedCitationType],
) -> Set[Tuple[SupportedCitationType, ...]]:
    """Work through a list of citations and identify ones that are physically
    near each other in the document.

    Return a set of tuples. Each tuple represents a series of parallel
    citations. These will usually be length two, but not necessarily.
    """
    if len(citations) == 0:
        return set()
    citation_indexes = [c.index for c in citations]
    parallel_citation = [citations[0]]
    parallel_citations = set()
    for i, reporter_index in enumerate(citation_indexes[:-1]):
        if reporter_index + PARALLEL_DISTANCE > citation_indexes[i + 1]:
            # The present item is within a reasonable distance from the next
            # item. It's a parallel citation.
            parallel_citation.append(citations[i + 1])
        else:
            # Not close enough. Append what we've got and start a new list.
            if len(parallel_citation) > 1:
                if tuple(parallel_citation[::-1]) not in parallel_citations:
                    # If the reversed tuple isn't in the set already, add it.
                    # This makes sure a document with many references to the
                    # same case only gets counted once.
                    parallel_citations.add(tuple(parallel_citation))
            parallel_citation = [citations[i + 1]]

    # In case the last item had a citation.
    if len(parallel_citation) > 1:
        if tuple(parallel_citation[::-1]) not in parallel_citations:
            # Ensure the reversed tuple isn't in the set already (see above).
            parallel_citations.add(tuple(parallel_citation))
    return parallel_citations


@app.task(bind=True, max_retries=5, ignore_result=True)
def find_citations_and_parantheticals_for_recap_documents(
    self, doc_ids: List[int]
):
    """Find citations and authored parentheticals for search.RECAPDocument objects.

    :param doc_ids: An iterable of search.RECAPDocument PKs

    :return: None
    """
    documents: QuerySet[
        RECAPDocument, RECAPDocument
    ] = RECAPDocument.objects.filter(pk__in=doc_ids).filter(
        ocr_status__in=[
            RECAPDocument.OCR_UNNECESSARY,
            RECAPDocument.OCR_COMPLETE,
        ]
    )

    for d in documents:
        try:
            store_recap_citations(d)
        except ResponseNotReady as e:
            # Threading problem in httplib.
            raise self.retry(exc=e, countdown=2)


@app.task(bind=True, max_retries=5, ignore_result=True)
def find_citations_and_parentheticals_for_opinion_by_pks(
    self,
    opinion_pks: List[int],
) -> None:
    """Find citations and authored parentheticals for search.Opinion objects.

    :param opinion_pks: An iterable of search.Opinion PKs
    :return: None
    """
    opinions: QuerySet[Opinion, Opinion] = Opinion.objects.filter(
        pk__in=opinion_pks
    )
    for opinion in opinions:
        try:
            store_opinion_citations_and_update_parentheticals(opinion)
        except ResponseNotReady as e:
            # Threading problem in httplib.
            raise self.retry(exc=e, countdown=2)


def store_opinion_citations_and_update_parentheticals(
    opinion: Opinion,
) -> None:
    """
    Updates counts of citations to other opinions within a given court opinion,
    parenthetical info for the cited opinions, and stores unmatched citations

    :param opinion: A search.Opinion object.
    :return: None
    """
    # Extract the citations from the opinion's text
    # If the source has marked up text, pass it so it can be used to find
    # ReferenceCitations. This is handled by `make_get_citations_kwargs`
    cite_dict = make_get_citations_kwargs(opinion)
    citations: List[CitationBase] = get_citations(
        tokenizer=HYPERSCAN_TOKENIZER,
        **cite_dict,
    )

    if not citations:
        # No citations found make html with citations
        if cite_dict.get("markup_text"):
            new_html = cite_dict.get("markup_text")
        else:
            plain_text = cite_dict.get("plain_text", "")
            new_html = f'<pre class="inline">{ html.escape(plain_text)}</pre>'
        opinion.html_with_citations = new_html
        opinion.save()
        return

    # Resolve all those different citation objects to Opinion objects,
    # using a variety of heuristics.
    citation_resolutions: Dict[
        MatchedResourceType, List[SupportedCitationType]
    ] = do_resolve_citations(citations, opinion)

    # Generate the citing opinion's new HTML with inline citation links
    opinion.html_with_citations = create_cited_html(citation_resolutions)

    # Put apart the unmatched citations
    unmatched_citations = citation_resolutions.pop(NO_MATCH_RESOURCE, [])

    # Delete citations with multiple matches
    ambiguous_matches = citation_resolutions.pop(MULTIPLE_MATCHES_RESOURCE, [])

    # Increase the citation count for the cluster of each matched opinion
    # if that cluster has not already been cited by this opinion. First,
    # calculate a list of the IDs of every opinion whose cluster will need
    # updating.

    currently_cited_opinions = opinion.opinions_cited.all().values_list(
        "pk", flat=True
    )

    opinion_ids_to_update = {
        o.pk
        for o in citation_resolutions.keys()
        if o.pk not in currently_cited_opinions
    }

    clusters_to_update_par_groups_for = set()
    parentheticals: List[Parenthetical] = []

    for _opinion, _citations in citation_resolutions.items():
        # Currently, eyecite has a bug where parallel citations are
        # detected individually. We avoid creating duplicate parentheticals
        # because of that by keeping track of what we've seen so far.
        parenthetical_texts = set()

        for c in _citations:
            if (
                (par_text := c.metadata.parenthetical)
                and par_text not in parenthetical_texts
                and is_parenthetical_descriptive(par_text)
            ):
                clusters_to_update_par_groups_for.add(_opinion.cluster_id)
                parenthetical_texts.add(par_text)
                clean = clean_parenthetical_text(par_text)
                parentheticals.append(
                    Parenthetical(
                        describing_opinion_id=opinion.pk,
                        described_opinion_id=_opinion.pk,
                        text=clean,
                        score=parenthetical_score(clean, opinion.cluster),
                    )
                )

    # If the opinion has been processed previously, we update it's
    # associated UnmatchedCitations.status. If not, we store them all
    update_unmatched_status = UnmatchedCitation.objects.filter(
        citing_opinion=opinion
    ).exists()

    # Finally, commit these changes to the database in a single
    # transcation block.
    with transaction.atomic():
        opinion_clusters_to_update = OpinionCluster.objects.filter(
            sub_opinions__pk__in=opinion_ids_to_update
        )
        opinion_clusters_to_update.update(
            citation_count=F("citation_count") + 1
        )

        if update_unmatched_status:
            update_unmatched_citations_status(citation_resolutions, opinion)
        elif unmatched_citations or ambiguous_matches:
            store_unmatched_citations(
                unmatched_citations, ambiguous_matches, opinion
            )

        # Nuke existing citations and parentheticals
        OpinionsCited.objects.filter(citing_opinion_id=opinion.pk).delete()
        Parenthetical.objects.filter(describing_opinion_id=opinion.pk).delete()

        # Create the new ones.
        OpinionsCited.objects.bulk_create(
            [
                OpinionsCited(
                    citing_opinion_id=opinion.pk,
                    cited_opinion_id=_opinion.pk,
                    depth=len(_citations),
                )
                for _opinion, _citations in citation_resolutions.items()
            ]
        )
        Parenthetical.objects.bulk_create(parentheticals)

        # Update parenthetical groups for clusters that we have added
        # parentheticals for from this opinion
        for cluster_id in clusters_to_update_par_groups_for:
            create_parenthetical_groups(
                OpinionCluster.objects.get(pk=cluster_id)
            )

        # Save all the changes to the citing opinion
        opinion.save()

    # Update changes in ES.
    cluster_ids_to_update = list(
        opinion_clusters_to_update.values_list("id", flat=True)
    )
    index_related_cites_fields.delay(
        OpinionsCited.__name__, opinion.pk, cluster_ids_to_update
    )


def update_unmatched_citations_status(
    citation_resolutions: Dict[
        MatchedResourceType, List[SupportedCitationType]
    ],
    citing_opinion: Opinion,
) -> None:
    """Check if previously unmatched citations have been resolved and
    updates UnmatchedCitation.status accordingly

    We assume no new UnmatchedCitations will be created after the first run

    :param citation_resolutions: dict whose values are resolved citations
    :param citing_opinion: the opinion
    :return None:
    """
    resolved_citations = {
        c.matched_text() for v in citation_resolutions.values() for c in v
    }

    # try to update the status of FOUND and FAILED_* UnmatchedCitations
    found_citations = UnmatchedCitation.objects.filter(
        citing_opinion=citing_opinion
    ).exclude(
        status__in=[UnmatchedCitation.UNMATCHED, UnmatchedCitation.RESOLVED]
    )
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
    unmatched_citations: List[CitationBase],
    ambiguous_matches: List[CitationBase],
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
    citations_to_this_cluster = [
        str(c) for c in opinion.cluster.citations.all()
    ]

    for index, unmatched_citation in enumerate(
        unmatched_citations + ambiguous_matches, 1
    ):
        has_multiple_matches = index > len(unmatched_citations)

        if not isinstance(unmatched_citation, FullCaseCitation):
            continue

        # handle bugs in eyecite that make it return FullCitations with null
        # values in required fields
        groups = unmatched_citation.groups
        if (
            not groups.get("reporter")
            or not groups.get("volume")
            or not groups.get("page")
        ):
            logger.error(
                "Unexpected null value in FullCaseCitation %s",
                unmatched_citation,
            )
            continue
        if not groups.get("volume").isdigit():
            logger.error(
                "Unexpected non-integer volume value in FullCaseCitation %s",
                unmatched_citation,
            )
            continue

        # This would raise a DataError, we have seen cases from bad OCR or
        # citation lookalikes. See #5191
        if int(groups["volume"]) >= 32_767:
            continue

        citation_object = UnmatchedCitation.create_from_eyecite(
            unmatched_citation, opinion, has_multiple_matches
        )

        # use to prevent Integrity error from duplicates
        citation_str = str(citation_object)
        if citation_str in seen_citations:
            continue
        seen_citations.add(citation_str)

        # avoid storing self citations as unmatched; the self citation will
        # usually be found at the beginning of the opinion's text
        # Note that both Citation.__str__ and UnmatchedCitation.__str__ use
        # the standardized volume, reporter and page values, so they are
        # comparable
        if citation_str in citations_to_this_cluster:
            continue

        unmatched_citations_to_store.append(citation_object)

    if unmatched_citations_to_store:
        UnmatchedCitation.objects.bulk_create(unmatched_citations_to_store)
