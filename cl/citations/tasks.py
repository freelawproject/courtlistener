import re

from cl.citations import find_citations, match_citations
from cl.search.models import Opinion, OpinionsCited
from celery import task

# This is the distance two reporter abbreviations can be from each other if they
# are considered parallel reporters. For example, "22 U.S. 44, 46 (13 Atl. 33)"
# would have a distance of 4.
PARALLEL_DISTANCE = 4

@task
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


@task
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
        citations = find_citations.get_citations(opinion.plain_text,
                                                 html=False)
    else:
        citations = []
    return citations


def create_cited_html(opinion, citations):
    if any([opinion.html_columbia, opinion.html_lawbox, opinion.html]):
        new_html = opinion.html_columbia or opinion.html_lawbox or opinion.html
        for citation in citations:
            new_html = re.sub(citation.as_regex(), citation.as_html(),
                              new_html)
    elif opinion.plain_text:
        inner_html = opinion.plain_text
        for citation in citations:
            repl = u'</pre>%s<pre class="inline">' % citation.as_html()
            inner_html = re.sub(citation.as_regex(), repl, inner_html)
        new_html = u'<pre class="inline">%s</pre>' % inner_html
    return new_html.encode('utf-8')


@task
def update_document(opinion, index=True):
    """Get the citations for an item and save it and add it to the index if
    requested."""
    citations = get_document_citations(opinion)

    # List used so we can do one simple update to the citing opinion.
    opinions_cited = set()
    for citation in citations:
        matches = match_citations.match_citation(
            citation,
            citing_doc=opinion
        )

        # TODO: Figure out what to do if there's more than one
        if len(matches) == 1:
            match_id = matches[0]['id']
            try:
                matched_opinion = Opinion.objects.get(pk=match_id)

                # Increase citation count for matched cluster if it hasn't
                # already been cited by this opinion.
                if matched_opinion not in opinion.opinions_cited.all():
                    matched_opinion.cluster.citation_count += 1
                    matched_opinion.cluster.save(index=index)

                # Add citation match to the citing opinion's list of cases it
                # cites. opinions_cited is a set so duplicates aren't an issue
                opinions_cited.add(matched_opinion.pk)

                # URL field will be used for generating inline citation html
                citation.match_url = matched_opinion.cluster.get_absolute_url()
                citation.match_id = matched_opinion.pk
            except Opinion.DoesNotExist:
                # No Opinions returned. Press on.
                continue
            except Opinion.MultipleObjectsReturned:
                # Multiple Opinions returned. Press on.
                continue
        else:
            # No match found for citation
            #create_stub([citation])
            pass

    # Only update things if we found citations
    if citations:
        opinion.html_with_citations = create_cited_html(opinion, citations)

        # Nuke existing citations
        OpinionsCited.objects.filter(citing_opinion_id=opinion.pk).delete()

        # Create the new ones.
        OpinionsCited.objects.bulk_create([
            OpinionsCited(citing_opinion_id=opinion.pk,
                          cited_opinion_id=pk) for
            pk in opinions_cited
        ])

    # Update Solr if requested. In some cases we do it at the end for
    # performance reasons.
    opinion.save(index=index)


@task
def update_document_by_id(opinion_id):
    """This is not an OK way to do id-based tasks. Needs to be refactored."""
    op = Opinion.objects.get(pk=opinion_id)
    update_document(op)
