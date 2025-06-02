import logging
from http.client import ResponseNotReady

from django.conf import settings
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
    disconnect_pg_signals: bool = False,
) -> None:
    """Find citations and authored parentheticals for search.Opinion objects.

    :param opinion_pks: An iterable of search.Opinion PKs
    :param disconnect_pg_signals: True if ParentheticalGroup post_save and
        post_delete signals should be disconnected; useful in batch jobs
        from the `find_citations` command

    :return: None
    """
    opinions: QuerySet[Opinion, Opinion] = Opinion.objects.filter(
        pk__in=opinion_pks
    )
    # delivery_info does not exist in test environment
    children_queue = (self.request.delivery_info or {}).get(
        "routing_key", settings.CELERY_ETL_TASK_QUEUE
    )

    if disconnect_pg_signals:
        disconnect_parenthetical_group_signals()
    try:
        for index, opinion in enumerate(opinions):
            try:
                store_opinion_citations_and_update_parentheticals(
                    opinion,
                    children_queue,
                )
            except ResponseNotReady as e:
                # Threading problem in httplib.
                raise self.retry(exc=e, countdown=2)
            except OperationalError:
                # delay deadlocked tasks, and continue regular process
                find_citations_and_parentheticals_for_opinion_by_pks.apply_async(
                    ([opinion.id], disconnect_pg_signals), countdown=60
                )
            except Exception as e:
                # do not retry the whole loop on an unknown exception
                end_index = min(len(opinions) - 1, index + 1)
                ids = [o.id for o in opinions[end_index:]]
                if ids:
                    raise self.retry(
                        exc=e,
                        countdown=60,
                        kwargs={
                            "opinion_pks": ids,
                            "disconnect_pg_signals": disconnect_pg_signals,
                        },
                    )
    finally:
        if disconnect_pg_signals:
            reconnect_parenthetical_group_signals()


def store_opinion_citations_and_update_parentheticals(
    opinion: Opinion,
    queue_for_children: str = settings.CELERY_ETL_TASK_QUEUE,
) -> None:
    """
    Updates counts of citations to other opinions within a given court opinion,
    parenthetical info for the cited opinions, and stores unmatched citations

    :param opinion: A search.Opinion object
    :param queue: celery queue to send the child tasks to
    :return: None
    """
    # Extract the citations from the opinion's text
    # If the source has marked up text, pass it so it can be used to find
    # ReferenceCitations. This is handled by `make_get_citations_kwargs`
    get_citations_kwargs = make_get_citations_kwargs(opinion)
    citations: list[CitationBase] = get_citations(
        tokenizer=HYPERSCAN_TOKENIZER,
        **get_citations_kwargs,
    )

    # Resolve all those different citation objects to Opinion objects,
    # using a variety of heuristics.
    citation_resolutions: dict[
        MatchedResourceType, list[SupportedCitationType]
    ] = do_resolve_citations(citations, opinion)

    # Generate the citing opinion's new HTML with inline citation links
    opinion.html_with_citations = create_cited_html(
        citation_resolutions, get_citations_kwargs
    )
    if not citation_resolutions:
        # there was nothing to annotate, just save the `html_with_citations`
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

    # Increase the citation count for the cluster of each matched opinion
    # if that cluster has not already been cited by this opinion. First,
    # calculate a list of the IDs of every opinion whose cluster will need
    # updating.
    currently_cited_opinions = OpinionsCited.objects.filter(
        citing_opinion_id=opinion.pk
    ).values_list("cited_opinion_id", flat=True)
    cluster_ids_to_update = {
        o.cluster.pk
        for o in citation_resolutions.keys()
        if o.pk not in currently_cited_opinions
    }

    # Finally, commit these changes to the database in a single
    # transaction block.
    with transaction.atomic():
        opinion_clusters_to_update = OpinionCluster.objects.filter(
            id__in=cluster_ids_to_update
        )
        opinion_clusters_to_update.update(
            citation_count=F("citation_count") + 1
        )
        handle_unmatched_citations(
            opinion,
            unmatched_citations + ambiguous_matches,
            citation_resolutions,
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
    index_related_cites_fields.apply_async(
        args=(
            OpinionsCited.__name__,
            opinion.pk,
            list(cluster_ids_to_update),
        ),
        queue=queue_for_children,
    )
