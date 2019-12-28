import re
from httplib import ResponseNotReady
from collections import Counter

from cl.celery import app
from cl.citations import find_citations, match_citations
from cl.search.models import Opinion, OpinionsCited

# This is the distance two reporter abbreviations can be from each other if they
# are considered parallel reporters. For example, "22 U.S. 44, 46 (13 Atl. 33)"
# would have a distance of 4.
PARALLEL_DISTANCE = 4


@app.task
def identify_parallel_citations(citations):
    """Work through a list of citations and identify ones that are physically
    near each other in the document.

    Return a list of tuples. Each tuple represents a series of parallel
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
def get_document_citations(opinion):
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


def create_cited_html(opinion, citations):
    if any([opinion.html_columbia, opinion.html_lawbox, opinion.html]):
        new_html = opinion.html_columbia or opinion.html_lawbox or opinion.html
        for citation in citations:
            new_html = re.sub(
                citation.as_regex(), citation.as_html(), new_html
            )
    elif opinion.plain_text:
        inner_html = opinion.plain_text
        for citation in citations:
            repl = u'</pre>%s<pre class="inline">' % citation.as_html()
            inner_html = re.sub(citation.as_regex(), repl, inner_html)
        new_html = u'<pre class="inline">%s</pre>' % inner_html
    return new_html.encode("utf-8")


@app.task(bind=True, max_retries=5, ignore_result=True)
def find_citations_for_opinion_by_pks(self, opinion_pks, index=True):
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

        # Match all those different Citation objects to Opinion objects, using
        # a variety of hueristics.
        try:
            citation_matches = match_citations.get_citation_matches(
                opinion, citations
            )
        except ResponseNotReady as e:
            # Threading problem in httplib, which is used in the Solr query.
            raise self.retry(exc=e, countdown=2)

        # Consolidate duplicate matches, keeping a counter of how often each
        # match appears (so we know how many times an opinion cites another).
        # keys = opinion
        # values = number of times that opinion is cited
        grouped_matches = Counter(citation_matches)

        for matched_opinion in grouped_matches:
            # Increase citation count for matched cluster if it hasn't
            # already been cited by this opinion.
            if matched_opinion not in opinion.opinions_cited.all():
                matched_opinion.cluster.citation_count += 1
                matched_opinion.cluster.save(index=index)

        # Only update things if we found citations
        if citations:
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

        # Update Solr if requested. In some cases we do it at the end for
        # performance reasons.
        opinion.save(index=index)
