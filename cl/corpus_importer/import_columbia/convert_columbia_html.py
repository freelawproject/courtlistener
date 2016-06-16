# -*- coding: utf-8 -*-
"""
Created on Wed Jun 15 16:32:17 2016

@author: elliott
"""

import re


def convert_columbia_html(text):

    conversions = [('italic', 'em'),
                   ('block_quote', 'blockquote'),
                   ('bold', 'strong'),
                   ('underline', 'u'),
                   ('strikethrough', 'strike'),
                   ('superscript', 'sup'),
                   ('subscript', 'sub'),
                   ('heading', 'h3'),
                   ('table', 'pre')]

    for (pattern, replacement) in conversions:
        text = re.sub('<'+pattern+'>', '<'+replacement+'>', text)
        text = re.sub('</'+pattern+'>', '</'+replacement+'>', text)

    # grayed-out page numbers
    text = re.sub('<page_number>', ' <span class="star-pagination">*', text)
    text = re.sub('</page_number>', '</span> ', text)

    # footnotes
    foot_references = re.findall('<footnote_reference>.*?</footnote_reference>', text)

    for ref in foot_references:
        fnum = re.search('[\*\d]+', ref).group()
        rep = '<sup id="ref-fn%s"><a href="#fn%s">%s</a></sup>' % (fnum, fnum, fnum)
        text = text.replace(ref, rep)

    foot_numbers = re.findall('<footnote_number>.*?</footnote_number>',text)

    for ref in foot_numbers:
         fnum = re.search('[\*\d]+', ref).group()
         rep = r'<sup id="fn%s"><a href="#ref-fn%s">%s</a></sup>' % (fnum, fnum, fnum)
         text = text.replace(ref, rep)

    # Make nice paragraphs. This replaces double newlines with paragraphs, then
    # nests paragraphs inside blockquotes, rather than vice versa. The former
    # looks good. The latter is bad.
    text = '<p>' + text + '</p>'
    text = re.sub('</blockquote>\s*<blockquote>', '\n\n', text)
    text = re.sub('\n\n', '</p>\n<p>', text)
    text = re.sub('<p>\s*<blockquote>', '<blockquote><p>', text, re.M)
    text = re.sub('</blockquote></p>', '</p></blockquote>', text, re.M)

    return text
