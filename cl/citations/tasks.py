import re
from http.client import ResponseNotReady
from collections import Counter
from typing import List, Union, Tuple, Set

from django.db import transaction
from django.db.models import F

from cl.celery_init import app
from cl.citations import find_citations, match_citations
from cl.search.models import Opinion, OpinionsCited, OpinionCluster
from cl.search.tasks import add_items_to_solr
from cl.citations.models import Citation, NonopinionCitation
from cl.citations.utils import (
    is_balanced_html,
    remove_duplicate_citations_by_regex,
)

# This is the distance two reporter abbreviations can be from each other if
# they are considered parallel reporters. For example,
# "22 U.S. 44, 46 (13 Atl. 33)" would have a distance of 4.
PARALLEL_DISTANCE = 4


@app.task
def identify_parallel_citations(
    citations: List[Citation],
) -> Set[Tuple[Citation]]:
    """Work through a list of citations and identify ones that are physically
    near each other in the document.

    Return a set of tuples. Each tuple represents a series of parallel
    citations. These will usually be length two, but not necessarily.
    """
    if len(citations) == 0:
        return citations
    citation_indexes = [c.reporter_index for c in citations]
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


@app.task
def get_document_citations(
    opinion: Opinion,
) -> List[Union[NonopinionCitation, Citation]]:
    """Identify and return citations from the html or plain text of the
    opinion.
    """
    if opinion.html_columbia:
        citations = find_citations.get_citations(opinion.html_columbia)
    elif opinion.html_lawbox:
        citations = find_citations.get_citations(opinion.html_lawbox)
    elif opinion.html:
        citations = find_citations.get_citations(opinion.html)
    elif opinion.plain_text:
        citations = find_citations.get_citations(
            opinion.plain_text, html=False
        )
    else:
        citations = []
    return citations


def create_cited_html(opinion: Opinion, citations: List[Citation]) -> str:
    """Add citation links to opinion text

    Using the opinion itself and a list of citations found within it, make the
    citations into links to the correct citations.
    :param opinion: The opinion to enhance
    :param citations: A list of citations in the opinion
    :return The new HTML containing citations
    """
    citations = [
        citation for citation in citations if isinstance(citation, Citation)
    ]
    citations = remove_duplicate_citations_by_regex(citations)
    if any([opinion.html_columbia, opinion.html_lawbox, opinion.html]):
        new_html = opinion.html_columbia or opinion.html_lawbox or opinion.html
        for citation in citations:
            citation_regex = citation.as_regex()
            match = re.search(citation_regex, new_html)

            # Only perform the string replacement if we're sure that the
            # matched HTML is not unbalanced. (If it is, when we inject
            # our own HTML, the DOM can get messed up.)
            if match and is_balanced_html(match.group()):
                new_html = re.sub(citation_regex, citation.as_html(), new_html)
    elif opinion.plain_text:
        inner_html = opinion.plain_text
        for citation in citations:
            repl = '</pre>%s<pre class="inline">' % citation.as_html()
            inner_html = re.sub(citation.as_regex(), repl, inner_html)
        new_html = '<pre class="inline">%s</pre>' % inner_html
    return new_html


@app.task(bind=True, max_retries=5, ignore_result=True)
def find_citations_for_opinion_by_pks(
    self,
    opinion_pks: List[int],
    index: bool = True,
) -> None:
    """Find citations for search.Opinion objects.

    :param opinion_pks: An iterable of search.Opinion PKs
    :param index: Whether to add the item to Solr
    :return: None
    """
    opinions = Opinion.objects.filter(pk__in=opinion_pks)
    for opinion in opinions:
        # Returns a list of Citation objects, i.e., something like
        # [FullCitation, FullCitation, ShortformCitation, FullCitation,
        #   SupraCitation, SupraCitation, ShortformCitation, FullCitation]
        citations = get_document_citations(opinion)

        # If no citations are found, continue
        if not citations:
            continue

        # Match all those different Citation objects to Opinion objects, using
        # a variety of heuristics.
        try:
            citation_matches = match_citations.get_citation_matches(
                opinion, citations
            )
        except ResponseNotReady as e:
            # Threading problem in httplib, which is used in the Solr query.
            raise self.retry(exc=e, countdown=2)

        # Consolidate duplicate matches, keeping a counter of how often each
        # match appears (so we know how many times an opinion cites another).
        # keys = cited opinion
        # values = number of times that opinion is cited
        grouped_matches = Counter(citation_matches)

        # Increase the citation count for the cluster of each matched opinion
        # if that cluster has not already been cited by this opinion. First,
        # calculate a list of the IDs of every opinion whose cluster will need
        # updating.
        all_cited_opinions = opinion.opinions_cited.all().values_list(
            "pk", flat=True
        )
        opinion_ids_to_update = set()
        for matched_opinion in grouped_matches:
            if matched_opinion.pk not in all_cited_opinions:
                opinion_ids_to_update.add(matched_opinion.pk)

        with transaction.atomic():
            # Then, increment the citation_count fields for those matched
            # clusters all at once. Trigger a single Solr update as well, if
            # required.
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

            # Generate the citing opinion's new HTML
            # (with inline citation links)
            opinion.html_with_citations = create_cited_html(opinion, citations)

            # Nuke existing citations
            OpinionsCited.objects.filter(citing_opinion_id=opinion.pk).delete()

            # Create the new ones.
            OpinionsCited.objects.bulk_create(
                [
                    OpinionsCited(
                        citing_opinion_id=opinion.pk,
                        cited_opinion_id=matched_opinion.pk,
                        depth=grouped_matches[matched_opinion],
                    )
                    for matched_opinion in grouped_matches
                ]
            )

            # Save all the changes to the citing opinion (send to solr later)
            opinion.save(index=False)

    # If a Solr update was requested, do a single one at the end with all the
    # pks of the passed opinions
    if index:
        add_items_to_solr.delay(opinion_pks, "search.Opinion")
