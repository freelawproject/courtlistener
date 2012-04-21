#!/usr/bin/env python
# encoding: utf-8

import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'alert.settings'

import sys
sys.path.append("/var/www/court-listener")

from alert.search.models import Document
from alert.lib.db_tools import queryset_generator

from reporter_tokenizer import FederalReporterTokenizer
import find_citations
import match_citations
import re

DEBUG = 2

def get_document_citations(document, tokenizer):
    '''Identify and return citations from the html or plain text of the document.'''
    if document.documentHTML:
        citations = find_citations.get_citations(document.documentHTML,
                                                 tokenizer)
    elif document.documentPlainText:
        citations = find_citations.get_citations(document.documentPlainText,
                                                 tokenizer,
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

def update_document(document, tokenizer):
    citations = get_document_citations(document, tokenizer)
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
                document.cited_cases.append(matched_doc.citation)
                # URL field will be used for generating inline citation html
                # MLR: match_doc is undefined, I think
                citation.match_url = match_doc.get_absolute_url()
            except:
                # MLR: Hrm, had you used a specific exception type, you'd probably 
                #      have noticed the error above :). Probably should do that 
                #      too.
                # No matches or multiple matches.
                continue
        else:
            # MLR: need something here, so we at least know how much we fail, right?
            print "MLR: more than one match found for citation foo, therefore....blah"
    # Only create new HTML if we found citations
    if citations:
        document.html_with_citations = create_cited_html(document, citations)
        if DEBUG >= 3:
            print document.html_with_citations

    # MLR: Am I not seeing where we tweak the m2m? I woulda expected it here? 
    document.save()
    citation_matches = sum(matched_citations)
    name_matches = len(matched_citations) - citation_matches
    return (len(citations), citation_matches, name_matches)

def update_documents(documents):
    tokenizer = FederalReporterTokenizer()
    citations = 0
    citation_matches = 0
    name_matches = 0
    for document in documents:
        cite_found, new_cite_matches, new_name_matches = update_document(document, tokenizer)
        citations += cite_found
        citation_matches += new_cite_matches
        name_matches += new_name_matches
        if DEBUG >= 2:
            print document.citation.case_name
            print "  %d citations" % cite_found
            print "  %d exact matches" % new_cite_matches
            print "  %d name matches" % new_name_matches
    if DEBUG >= 1:
        print "Summary for %d documents" % len(documents)
        print "  %d citations" % citations
        print "  %d exact matches" % citation_matches
        print "  %d name matches" % name_matches

def update_documents_by_id(id_list):
    docs = Document.objects.filter(pk__in=id_list)
    update_documents(docs)

def main():
    docs = queryset_generator(Document.objects.all())
    update_documents(docs)

if __name__ == '__main__':
    main()
