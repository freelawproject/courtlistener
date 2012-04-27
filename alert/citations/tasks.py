# This software and any associated files are copyright 2010 Brian Carver and
# Michael Lissner.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
sys.path.append('/var/www/court-listener/alert')

from alert import settings
from django.core.management import setup_environ
setup_environ(settings)

from alert.citations import find_citations
from alert.citations import match_citations
from alert.search.models import Document
from celery.decorators import task

import re

def get_document_citations(document):
    '''Identify and return citations from the html or plain text of the document.'''
    if document.documentHTML:
        citations = find_citations.get_citations(document.documentHTML)
    elif document.documentPlainText:
        citations = find_citations.get_citations(document.documentPlainText,
                                                 html=False)
    else:
        citations = []
    return citations

def create_cited_html(document, citations):
    if document.documentHTML:
        new_html = document.documentHTML
        for citation in citations:
            new_html = re.sub(citation.as_regex(), citation.as_html(), new_html)
    elif document.documentPlainText:
        inner_html = document.documentPlainText
        for citation in citations:
            repl = u'</pre>%s<pre class="inline">' % citation.as_html()
            inner_html = re.sub(citation.as_regex(), repl, inner_html)
        new_html = u'<pre class="inline">%s</pre>' % inner_html
    return new_html.encode('utf-8')

@task
def update_document(document):
    print "%s at http://courtlistener.com/admin/search/citation/%s/" % \
        (document.citation.case_name, document.citation.pk)

    DEBUG = 2
    citations = get_document_citations(document)
    # List for tracking number of citation vs. name matches
    matched_citations = []
    for citation in citations:
        # Resource.org docs contain their own citation in the html text, which 
        # we don't want to include
        if citation.base_citation() == document.citation.westCite:
            continue
        matches, is_citation_match = match_citations.match_citation(citation,
                                                                    document)
        # TODO: Figure out what to do if there's more than one
        if len(matches) == 1:
            matched_citations.append(is_citation_match)
            match_id = matches[0]['id']
            try:
                matched_doc = Document.objects.get(pk=match_id)
                # Add citation match to the document's list of cases it cites
                document.cases_cited.add(matched_doc.citation)
                # URL field will be used for generating inline citation html
                citation.match_url = matched_doc.get_absolute_url()
            except Document.DoesNotExist:
                if DEBUG >= 2:
                    print "No database matches found for document id %s" % match_id
                continue
            except Document.MultipleObjectsReturned:
                if DEBUG >= 2:
                    print "Multiple database matches found for document id %s" % match_id
                continue
        else:
            if DEBUG >= 2:
                print "No match found for citation %s" % citation.base_citation()
    # Only create new HTML if we found citations
    if citations:
        document.html_with_citations = create_cited_html(document, citations)
        if DEBUG >= 3:
            print document.html_with_citations

    # Turn off solr updating; we're not changing anything in the search index
    document.save(index=False)
    citation_matches = sum(matched_citations)
    name_matches = len(matched_citations) - citation_matches

    print "  %d citations" % len(citations)
    print "  %d exact matches" % citation_matches
    print "  %d name matches" % name_matches

@task
def update_document_by_id(document_id):
    doc = Document.objects.get(pk=document_id)
    update_document(doc)
