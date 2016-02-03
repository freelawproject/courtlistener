import re
from django.core import urlresolvers
from django.db import IntegrityError
from cl.citations import find_citations, match_citations
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.search.models import Opinion, OpinionsCited
from celery import task


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
    DEBUG = 0

    if DEBUG >= 1:
        print "%s at %s" % (
            best_case_name(opinion.cluster),
            urlresolvers.reverse(
                'admin:search_opinioncluster_change',
                args=(opinion.cluster.pk,),
            )
        )

    citations = get_document_citations(opinion)
    # List for tracking number of citation vs. name matches
    matched_citations = []
    # List used so we can do one simple update to the citing opinion.
    opinions_cited = []
    for citation in citations:
        # Resource.org docs contain their own citation in the html text, which
        # we don't want to include
        if citation.base_citation() in opinion.cluster.citation_string:
            continue
        matches, is_citation_match = match_citations.match_citation(
            citation,
            citing_doc=opinion
        )

        # TODO: Figure out what to do if there's more than one
        if len(matches) == 1:
            matched_citations.append(is_citation_match)
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
                opinions_cited.append(matched_opinion.pk)

                # URL field will be used for generating inline citation html
                citation.match_url = matched_opinion.cluster.get_absolute_url()
                citation.match_id = matched_opinion.pk
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

    # Only update things if we found citations
    if citations:
        opinion.html_with_citations = create_cited_html(opinion, citations)
        try:
            OpinionsCited.objects.bulk_create([
                OpinionsCited(citing_opinion_id=pk,
                              cited_opinion_id=opinion.pk) for
                pk in opinions_cited
            ])
        except IntegrityError as e:
            # If bulk_create would create an item that already exists, it fails.
            # In that case, do them one by one, skipping failing cases.
            for pk in opinions_cited:
                try:
                    cited = OpinionsCited(
                        citing_opinion_id=pk,
                        cited_opinion_id=opinion.pk,
                    )
                    cited.save()
                except IntegrityError:
                    # We'll just skip the ones that already exist, but still do
                    # the others.
                    pass
        if DEBUG >= 3:
            print opinion.html_with_citations

    # Update Solr if requested. In some cases we do it at the end for
    # performance reasons.
    opinion.save(index=index)
    if DEBUG >= 1:
        citation_matches = sum(matched_citations)
        name_matches = len(matched_citations) - citation_matches
        print "  %d citations" % len(citations)
        print "  %d exact matches" % citation_matches
        print "  %d name matches" % name_matches


@task
def update_document_by_id(opinion_id):
    """This is not an OK way to do id-based tasks. Needs to be refactored."""
    op = Opinion.objects.get(pk=opinion_id)
    update_document(op)
