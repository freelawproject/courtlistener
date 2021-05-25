from typing import Dict, List, Union

from eyecite import annotate, clean_text
from eyecite.models import Resource

from cl.citations.match_citations import NO_MATCH_RESOURCE
from cl.lib.types import SupportedCitationType
from cl.search.models import Opinion


def get_and_clean_opinion_text(opinion: Opinion) -> None:
    """Memoize useful versions of an opinion's text as additional properties
    on the Opinion object. This should be done before performing citation
    extraction and annotation on an opinion.

    :param opinion: The Opinion whose text should be parsed
    """
    for attr in ["html_anon_2020", "html_columbia", "html_lawbox", "html"]:
        text = getattr(opinion, attr)
        if text:
            opinion.source_text = text
            opinion.cleaned_text = clean_text(text, ["html", "all_whitespace"])
            opinion.source_is_html = True
            break
    else:
        # Didn't hit the break; use plain text
        text = getattr(opinion, "plain_text")
        opinion.source_text = text
        opinion.cleaned_text = clean_text(text, ["all_whitespace"])
        opinion.source_is_html = False


def generate_annotations(
    citation_resolutions: Dict[
        Union[Opinion, Resource], List[SupportedCitationType]
    ],
) -> List[List]:
    """Generate the string annotations to insert into the opinion text

    :param citations: A list of citations in the opinion
    :return The new HTML containing citations
    """
    annotations: List[List] = []
    for opinion, citations in citation_resolutions.items():
        if opinion is NO_MATCH_RESOURCE:  # If unsuccessfully matched...
            annotation = [
                '<span class="citation no-link">',
                "</span>",
            ]
        else:  # If successfully matched...
            annotation = [
                f'<span class="citation" data-id="{opinion.pk}"><a href="{opinion.cluster.get_absolute_url()}">',
                "</a></span>",
            ]
        for c in citations:
            annotations.append([c.span()] + annotation)
    return annotations


def create_cited_html(
    opinion: Opinion,
    citation_resolutions: Dict[
        Union[Opinion, Resource], List[SupportedCitationType]
    ],
) -> str:
    """Using the opinion itself and a list of citations found within it, make
    the citations into links to the correct citations.

    :param opinion: The opinion to enhance
    :param citations: A list of citations in the opinion
    :return The new HTML containing citations
    """
    if opinion.source_is_html:  # If opinion was originally HTML...
        new_html = annotate(
            plain_text=opinion.cleaned_text,
            annotations=generate_annotations(citation_resolutions),
            source_text=opinion.source_text,
            unbalanced_tags="skip",  # Don't risk overwriting existing tags
        )
    else:  # Else, make sure to wrap the new text in <pre> HTML tags...
        new_html = annotate(
            plain_text=opinion.cleaned_text,
            annotations=[
                [a[0], "</pre>" + a[1], a[2] + '<pre class="inline">']
                for a in generate_annotations(citation_resolutions)
            ],
            source_text=opinion.source_text,
        )
        new_html = '<pre class="inline">%s</pre>' % new_html

    # Return the newly-annotated text
    return new_html
