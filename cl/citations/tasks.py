import logging
from http.client import ResponseNotReady

from django.db import transaction
from django.db.models import F
from django.db.models.query import QuerySet
from django.db.utils import OperationalError
from eyecite import get_citations
from eyecite.models import CitationBase
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
from cl.citations.parenthetical_utils import (
    create_parenthetical_groups,
    disconnect_parenthetical_group_signals,
    reconnect_parenthetical_group_signals,
)
from cl.citations.recap_citations import store_recap_citations
from cl.citations.score_parentheticals import parenthetical_score
from cl.citations.types import MatchedResourceType, SupportedCitationType
from cl.citations.unmatched_citations_utils import handle_unmatched_citations
from cl.citations.utils import (
    get_cited_clusters_ids_to_update,
    make_get_citations_kwargs,
)
from cl.search.models import (
    Opinion,
    OpinionCluster,
    OpinionsCited,
    Parenthetical,
    RECAPDocument,
)
from cl.search.tasks import index_related_cites_fields

logger = logging.getLogger(__name__)

# This is the distance two reporter abbreviations can be from each other if
# they are considered parallel reporters. For example,
# "22 U.S. 44, 46 (13 Atl. 33)" would have a distance of 6.
PARALLEL_DISTANCE = 6
HYPERSCAN_TOKENIZER = HyperscanTokenizer(cache_dir=".hyperscan")


@app.task
def identify_parallel_citations(
    citations: list[SupportedCitationType],
) -> set[tuple[SupportedCitationType, ...]]:
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
    self, doc_ids: list[int]
):
    """Find citations and authored parentheticals for search.RECAPDocument objects.

    :param doc_ids: An iterable of search.RECAPDocument PKs

    :return: None
    """
    documents: QuerySet[RECAPDocument, RECAPDocument] = (
        RECAPDocument.objects.filter(pk__in=doc_ids).filter(
            ocr_status__in=[
                RECAPDocument.OCR_UNNECESSARY,
                RECAPDocument.OCR_COMPLETE,
            ]
        )
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
    opinion_pks: list[int],
    disable_parenthetical_groups: bool = False,
    disable_citation_count_update: bool = False,
) -> None:
    """Find citations and authored parentheticals for search.Opinion objects.

    :param opinion_pks: An iterable of search.Opinion PKs
    :param disable_parenthetical_groups: True if not ParentheticalGroup should
        be created; and their  post_save and post_delete signals should be
        disconnected; useful in batch jobs from the `find_citations` command
    :param disable_citation_count_update: if True,
        OpinionCluster.citation_count and related ElasticSearch fields will not
        be updated. Useful to prevent database overloading during bulk work

    :return: None
    """
    opinions: QuerySet[Opinion, Opinion] = Opinion.objects.filter(
        pk__in=opinion_pks
    )

    if disable_parenthetical_groups:
        disconnect_parenthetical_group_signals()

    update_citation_count = not disable_citation_count_update
    failed_ids: list[int] = []

    logger.info("Processing opinions: %s", opinion_pks)
    try:
        for index, opinion in enumerate(opinions):
            try:
                logger.info("Starting opinion: %s", opinion.id)
                store_opinion_citations_and_update_parentheticals(
                    opinion,
                    update_citation_count,
                    disable_parenthetical_groups,
                )
            except ResponseNotReady as e:
                # Threading problem in httplib.
                logger.warning("ResponseNotReady error for: %s", opinion.id)
                raise self.retry(exc=e, countdown=2)
            except OperationalError as e:
                # Delay deadlocked tasks
                logger.warning(
                    "OperationalError processing opinion %s: %s",
                    opinion.id,
                    e,
                    exc_info=True,
                    extra={"opinion_id": opinion.id},
                )
                failed_ids.append(opinion.id)
            except Exception as e:
                # Send this opinion failure to sentry and continue onward
                logger.error(
                    "Opinion failed: '%s' with %s",
                    opinion.id,
                    str(e),
                    exc_info=True,
                )

                # do not retry the whole loop on an unknown exception
                remaining_ids = [o.id for o in opinions[index + 1 :]]
                if remaining_ids:
                    logger.warning(
                        "Retrying remaining opinions: %s", remaining_ids
                    )
                    raise self.retry(
                        exc=e,
                        countdown=2,
                        args=(
                            remaining_ids,
                            disable_parenthetical_groups,
                            disable_citation_count_update,
                        ),
                    )
    finally:
        if disable_parenthetical_groups:
            reconnect_parenthetical_group_signals()

    # Retry task with the opinions that failed due to OperationalError
    if failed_ids:
        logger.warning(
            "Retrying %d failed opinions due to OperationalError:",
            len(failed_ids),
        )
        raise self.retry(
            exc=OperationalError("Batch retry for failed opinion ids"),
            countdown=5,
            args=(
                failed_ids,
                disable_parenthetical_groups,
                disable_citation_count_update,
            ),
        )


def store_opinion_citations_and_update_parentheticals(
    opinion: Opinion,
    update_citation_count: bool = True,
    disable_parenthetical_groups: bool = False,
) -> None:
    """
    Updates counts of citations to other opinions within a given court opinion,
    parenthetical info for the cited opinions, and stores unmatched citations

    :param opinion: A search.Opinion object
    :param update_citation_count: if False, do NOT update the DB or Elastic:
        - OpinionCluster.citation_count
        - `index_related_cites_fields` that updates OpinionDocument and
            OpinionClusterDocument
        this is useful to prevent database overloading during bulk work
    :param disable_parenthetical_groups: Skip creating ParentheticalGroups
    :return: None
    """
    segments = make_get_citations_kwargs(opinion)
    if not segments:
        logger.error(
            "Opinion has no content id: '%s'",
            opinion.id,
            extra=dict(
                opinion=opinion,
            ),
        )
        return

    cited_html_segments = []
    citation_resolutions: dict[
        MatchedResourceType, list[SupportedCitationType]
    ] = {}
    has_single_segment = True if len(segments) == 1 else False
    for kwarg_segment in segments:
        # Extract citations
        logger.debug("Extracting citations for opinion %s", opinion.pk)
        citations: list[CitationBase] = get_citations(
            tokenizer=HYPERSCAN_TOKENIZER,
            **kwarg_segment,
        )

        logger.debug("Resolving citations %s", opinion.pk)
        # Resolve all those different citation objects to Opinion objects,
        # using a variety of heuristics.
        citation_segment_resolutions: dict[
            MatchedResourceType, list[SupportedCitationType]
        ] = do_resolve_citations(citations, opinion)

        for (
            resource_type,
            citations_list,
        ) in citation_segment_resolutions.items():
            if resource_type not in citation_resolutions:
                citation_resolutions[resource_type] = []
            citation_resolutions[resource_type].extend(citations_list)

        logger.debug("Creating HTML with Citations %s", opinion.pk)

        # Generate the citing opinion's new HTML with inline citation links
        cited_html = create_cited_html(
            citation_segment_resolutions, kwarg_segment, has_single_segment
        )
        cited_html_segments.append(cited_html)

    created_html = "".join(cited_html_segments)
    if segments[0].get("plain_text", False) and not has_single_segment:
        # wrap plain text in a pre tag
        created_html = f'<pre class="inline">{created_html}</pre>'
    opinion.html_with_citations = created_html

    if not citation_resolutions:
        # there was nothing to annotate, just save the `html_with_citations`
        logger.debug("No annotations: Saving %s", opinion.pk)
        opinion.save()
        return

    # Put apart the unmatched citations and ambiguous citations
    unmatched_citations = citation_resolutions.pop(NO_MATCH_RESOURCE, [])
    ambiguous_matches = citation_resolutions.pop(MULTIPLE_MATCHES_RESOURCE, [])

    clusters_to_update_par_groups_for = set()
    parentheticals: list[Parenthetical] = []

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

    # need to update the citation_count of cited clusters
    cluster_ids_to_update: list[int] = []

    # Finally, commit these changes to the database in a single
    # transaction block.
    logger.debug("Begin transaction: %s", opinion.pk)
    with transaction.atomic():
        if update_citation_count:
            logger.debug(
                "Update citation count for %s",
                opinion.pk,
            )
            cluster_ids_to_update = get_cited_clusters_ids_to_update(
                citation_resolutions.keys(), opinion.pk
            )
            OpinionCluster.objects.filter(id__in=cluster_ids_to_update).update(
                citation_count=F("citation_count") + 1
            )

        handle_unmatched_citations(
            opinion,
            unmatched_citations + ambiguous_matches,
            citation_resolutions,
        )
        logger.debug("Recreate OpCited and Parens: %s", opinion.pk)

        # Nuke existing citations and parentheticals
        OpinionsCited.objects.filter(citing_opinion_id=opinion.pk).delete()
        Parenthetical.objects.filter(describing_opinion_id=opinion.pk).delete()

        # Create the new ones
        OpinionsCited.objects.bulk_create(
            [
                OpinionsCited(
                    citing_opinion_id=opinion.pk,
                    cited_opinion_id=_opinion.pk,
                    depth=len(_citations),
                )
                for _opinion, _citations in citation_resolutions.items()
                if opinion.cluster_id != _opinion.cluster_id
            ]
        )
        Parenthetical.objects.bulk_create(parentheticals)

        if disable_parenthetical_groups is False:
            # Update parenthetical groups for clusters that we have added
            # parentheticals for from this opinion
            logger.debug("Create parenthetical groups: %s", opinion.pk)
            for cluster_id in clusters_to_update_par_groups_for:
                create_parenthetical_groups(
                    OpinionCluster.objects.get(pk=cluster_id)
                )

        # Save all the changes to the citing opinion
        opinion.save()

    # Updates the ElasticSearch index
    # - OpinionClusterDocument.citeCount
    # - OpinionDocument.citeCount
    # - OpinionDocument.cites
    if update_citation_count:
        logger.debug("Index related cites: %s", opinion.pk)

        index_related_cites_fields.delay(
            OpinionsCited.__name__,
            opinion.pk,
            cluster_ids_to_update,
        )

    logger.debug("Finished %s", opinion.pk)
