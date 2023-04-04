"""
Created on Wed Jun 15 16:32:17 2016

@author: elliott
"""

import re


def convert_columbia_html(text):
    conversions = [
        ("italic", "em"),
        ("block_quote", "blockquote"),
        ("bold", "strong"),
        ("underline", "u"),
        ("strikethrough", "strike"),
        ("superscript", "sup"),
        ("subscript", "sub"),
        ("heading", "h3"),
        ("table", "pre"),
    ]

    for pattern, replacement in conversions:
        text = re.sub(f"<{pattern}>", f"<{replacement}>", text)
        text = re.sub(f"</{pattern}>", f"</{replacement}>", text)

    # grayed-out page numbers
    text = re.sub("<page_number>", ' <span class="star-pagination">*', text)
    text = re.sub("</page_number>", "</span> ", text)

    # footnotes
    foot_references = re.findall(
        "<footnote_reference>.*?</footnote_reference>", text
    )

    for ref in foot_references:
        try:
            fnum = re.search(r"[\*\d]+", ref).group()
        except AttributeError:
            fnum = re.search(r"\[fn(.+)\]", ref).group(1)
        rep = f'<sup id="ref-fn{fnum}"><a href="#fn{fnum}">{fnum}</a></sup>'
        text = text.replace(ref, rep)

    foot_numbers = re.findall("<footnote_number>.*?</footnote_number>", text)

    for ref in foot_numbers:
        try:
            fnum = re.search(r"[\*\d]+", ref).group()
        except:
            fnum = re.search(r"\[fn(.+)\]", ref).group(1)
        rep = r'<sup id="fn%s"><a href="#ref-fn%s">%s</a></sup>' % (
            fnum,
            fnum,
            fnum,
        )
        text = text.replace(ref, rep)

    # Make nice paragraphs. This replaces double newlines with paragraphs, then
    # nests paragraphs inside blockquotes, rather than vice versa. The former
    # looks good. The latter is bad.
    text = f"<p>{text}</p>"
    text = re.sub(r"</blockquote>\s*<blockquote>", "\n\n", text)
    text = re.sub("\n\n", "</p>\n<p>", text)
    text = re.sub(r"<p>\s*<blockquote>", "<blockquote><p>", text, re.M)
    text = re.sub("</blockquote></p>", "</p></blockquote>", text, re.M)

    return text
