import re
from django.core import urlresolvers
from cl.opinion_page.views import make_citation_string
from cl.citations import find_citations, match_citations
from cl.search.models import Opinion
from celery import task


def get_document_citations(document):
    """Identify and return citations from the html or plain text of the
    document.
    """
    if document.html_lawbox:
        citations = find_citations.get_citations(document.html_lawbox)
    elif document.html:
        citations = find_citations.get_citations(document.html)
    elif document.plain_text:
        citations = find_citations.get_citations(document.plain_text,
                                                 html=False)
    else:
        citations = []
    return citations


def create_cited_html(document, citations):
    if document.html_lawbox or document.html:
        new_html = document.html_lawbox or document.html
        for citation in citations:
            new_html = re.sub(citation.as_regex(), citation.as_html(),
                              new_html)
    elif document.plain_text:
        inner_html = document.plain_text
        for citation in citations:
            repl = u'</pre>%s<pre class="inline">' % citation.as_html()
            inner_html = re.sub(citation.as_regex(), repl, inner_html)
        new_html = u'<pre class="inline">%s</pre>' % inner_html
    return new_html.encode('utf-8')


@task
def update_document(document, index=True):
    """Get the citations for an item and save it and add it to the index if
    requested."""
    DEBUG = 0
    if DEBUG >= 1:
        print "%s at %s" % (
            document.case_name,
            urlresolvers.reverse(
                'admin:search_citation_change',
                args=(document.citation.pk,),
            )
        )

    citations = get_document_citations(document)
    # List for tracking number of citation vs. name matches
    matched_citations = []
    for citation in citations:
        # Resource.org docs contain their own citation in the html text, which
        # we don't want to include
        if citation.base_citation() in make_citation_string(document):
            continue
        matches, is_citation_match = match_citations.match_citation(citation, document)

        # TODO: Figure out what to do if there's more than one
        if len(matches) == 1:
            matched_citations.append(is_citation_match)
            match_id = matches[0]['id']
            try:
                matched_doc = Opinion.objects.get(pk=match_id)
                # Increase citation count for matched cluster if it hasn't
                # already been cited by this document.
                if matched_doc not in document.opinions_cited.all():
                    matched_doc.cluster.citation_count += 1
                    matched_doc.cluster.save(index=index)

                # Add citation match to the citing document's list of cases it
                # cites. opinions_cited is a set so duplicates aren't an issue
                document.opinions_cited.add(matched_doc)
                # URL field will be used for generating inline citation html
                citation.match_url = matched_doc.get_absolute_url()
                citation.match_id = matched_doc.pk
            except Opinion.DoesNotExist:
                if DEBUG >= 2:
                    print "No Opinions returned for id %s" % match_id
                continue
            except Opinion.MultipleObjectsReturned:
                if DEBUG >= 2:
                    print "Multiple Opinions returned for id %s" % match_id
                continue
        else:
            #create_stub([citation])
            if DEBUG >= 2:
                # TODO: Don't print 1 line per citation.  Save them in a list
                # and print in a single line at the end.
                print "No match found for citation %s" % citation.base_citation()
    # Only create new HTML if we found citations
    if citations:
        document.html_with_citations = create_cited_html(document, citations)
        if DEBUG >= 3:
            print document.html_with_citations

    # Update Solr if requested. In some cases we do it at the end for
    # performance reasons.
    document.save(index=index)
    if DEBUG >= 1:
        citation_matches = sum(matched_citations)
        name_matches = len(matched_citations) - citation_matches
        print "  %d citations" % len(citations)
        print "  %d exact matches" % citation_matches
        print "  %d name matches" % name_matches


@task
def update_document_by_id(document_id):
    """This is not an OK way to do id-based tasks. Needs to be refactored."""
    doc = Opinion.objects.get(pk=document_id)
    update_document(doc)
