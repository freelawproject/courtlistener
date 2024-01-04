from http.client import ResponseNotReady
from typing import Dict, List, Set, Tuple

from django.db import transaction
from django.db.models import F
from django.db.models.query import QuerySet
from eyecite import get_citations
from eyecite.models import CitationBase

from cl.celery_init import app
from cl.citations.annotate_citations import (
    create_cited_html,
    get_and_clean_opinion_text,
)
from cl.citations.filter_parentheticals import (
    clean_parenthetical_text,
    is_parenthetical_descriptive,
)
from cl.citations.match_citations import (
    NO_MATCH_RESOURCE,
    do_resolve_citations,
)
from cl.citations.parenthetical_utils import create_parenthetical_groups
from cl.citations.recap_citations import store_recap_citations
from cl.citations.score_parentheticals import parenthetical_score
from cl.citations.types import MatchedResourceType, SupportedCitationType
from cl.search.models import (
    Opinion,
    OpinionCluster,
    OpinionsCited,
    Parenthetical,
    RECAPDocument,
)
from cl.search.tasks import add_items_to_solr, index_related_cites_fields

# This is the distance two reporter abbreviations can be from each other if
# they are considered parallel reporters. For example,
# "22 U.S. 44, 46 (13 Atl. 33)" would have a distance of 6.
PARALLEL_DISTANCE = 6


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
    documents: QuerySet[RECAPDocument] = RECAPDocument.objects.filter(
        pk__in=doc_ids
    ).filter(
        ocr_status__in=[
            RECAPDocument.OCR_UNNECESSARY,
            RECAPDocument.OCR_COMPLETE,
        ]
    )

    for d in documents:
        try:
            store_recap_citations(d)
        except ResponseNotReady as e:
            # Threading problem in httplib, which is used in the Solr query.
            raise self.retry(exc=e, countdown=2)


@app.task(bind=True, max_retries=5, ignore_result=True)
def find_citations_and_parentheticals_for_opinion_by_pks(
    self,
    opinion_pks: List[int],
    index: bool = True,
) -> None:
    """Find citations and authored parentheticals for search.Opinion objects.

    :param opinion_pks: An iterable of search.Opinion PKs
    :param index: Whether to add the items to Solr
    :return: None
    """
    opinions: QuerySet[Opinion] = Opinion.objects.filter(pk__in=opinion_pks)
    for opinion in opinions:
        try:
            store_opinion_citations_and_update_parentheticals(opinion, index)
        except ResponseNotReady as e:
            # Threading problem in httplib, which is used in the Solr query.
            raise self.retry(exc=e, countdown=2)

    # If a Solr update was requested, do a single one at the end with all the
    # pks of the passed opinions
    if index:
        add_items_to_solr.delay(opinion_pks, "search.Opinion")


def store_opinion_citations_and_update_parentheticals(
    opinion: Opinion, index: bool
) -> None:
    """
    Updates counts of citations to other opinions within a given court opinion, as well as parenthetical info for the cited opinions.

    :param opinion: A search.Opinion object.
    :param index: Whether to add the item to Solr
    :return: None
    """

    # Memoize parsed versions of the opinion's text
    get_and_clean_opinion_text(opinion)

    # Extract the citations from the opinion's text
    citations: List[CitationBase] = get_citations(opinion.cleaned_text)

    # If no citations are found, then there is nothing else to do for now.
    if not citations:
        return

    # Resolve all those different citation objects to Opinion objects,
    # using a variety of heuristics.
    citation_resolutions: Dict[
        MatchedResourceType, List[SupportedCitationType]
    ] = do_resolve_citations(citations, opinion)

    # Generate the citing opinion's new HTML with inline citation links
    opinion.html_with_citations = create_cited_html(
        opinion, citation_resolutions
    )

    # Delete the unmatched citations
    citation_resolutions.pop(NO_MATCH_RESOURCE, None)

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

    # Finally, commit these changes to the database in a single
    # transcation block. Trigger a single Solr update as well, if
    # required.
    with transaction.atomic():
        opinion_clusters_to_update = OpinionCluster.objects.filter(
            sub_opinions__pk__in=opinion_ids_to_update
        )
        opinion_clusters_to_update.update(
            citation_count=F("citation_count") + 1
        )

        if index:
            add_items_to_solr.delay(
                opinion_clusters_to_update.values_list("pk", flat=True),
                "search.OpinionCluster",
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

        # Save all the changes to the citing opinion (send to solr later)
        opinion.save(index=False)

    # Update changes in ES.
    cluster_ids_to_update = list(
        opinion_clusters_to_update.values_list("id", flat=True)
    )
    index_related_cites_fields.delay(
        OpinionsCited.__name__, opinion.pk, cluster_ids_to_update
    )
