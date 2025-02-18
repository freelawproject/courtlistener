import html
import re
from typing import Dict, List

from django.urls import reverse
from eyecite import annotate_citations, clean_text

from cl.citations.match_citations import (
    MULTIPLE_MATCHES_RESOURCE,
    NO_MATCH_RESOURCE,
)
from cl.citations.types import MatchedResourceType, SupportedCitationType
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.string_utils import trunc
from cl.search.models import Opinion, RECAPDocument


def get_and_clean_opinion_text(document: Opinion | RECAPDocument) -> None:
    """Memoize useful versions of an opinion's text as additional properties
    on the Opinion object. This should be done before performing citation
    extraction and annotation on an opinion.

    :param document: The Opinion or RECAPDocument whose text should be parsed
    """

    # We prefer CAP data (xml_harvard) first.
    for attr in [
        "xml_harvard",
        "html_anon_2020",
        "html_columbia",
        "html_lawbox",
        "html",
    ]:
        text = getattr(document, attr, None)
        if text:
            document.source_text = text
            # Remove XML encodings from xml_harvard
            text = re.sub(r"^<\?xml.*?\?>", "", text, count=1)
            document.cleaned_text = clean_text(
                text, ["html", "all_whitespace"]
            )
            document.source_is_html = True
            break
    else:
        # Didn't hit the break; use plain text
        text = getattr(document, "plain_text")
        document.source_text = text
        document.cleaned_text = clean_text(text, ["all_whitespace"])
        document.source_is_html = False


def generate_annotations(
    citation_resolutions: Dict[
        MatchedResourceType, List[SupportedCitationType]
    ],
) -> List[List]:
    """Generate the string annotations to insert into the opinion text

    :param citation_resolutions: A map of lists of citations in the opinion
    :return The new HTML containing citations
    """
    from cl.opinion_page.views import make_citation_url_dict

    annotations: List[List] = []
    for opinion, citations in citation_resolutions.items():
        if opinion is NO_MATCH_RESOURCE:  # If unsuccessfully matched...
            annotation = [
                '<span class="citation no-link">',
                "</span>",
            ]
            # Annotate all unmatched citations
            annotations.extend([[c.span()] + annotation for c in citations])
        elif opinion is MULTIPLE_MATCHES_RESOURCE:
            # Multiple matches, can't disambiguate
            for c in citations:
                # Annotate all citations can't be disambiguated to citation
                # lookup page
                citation_dict = {
                    "reporter": c.groups.get("reporter"),
                    "volume": c.groups.get("volume", None),
                    "page": c.groups.get("page", None),
                }
                kwargs = make_citation_url_dict(**citation_dict)
                citation_url = reverse("citation_redirector", kwargs=kwargs)
                annotation = [
                    '<span class="citation multiple-matches">'
                    f'<a href="{html.escape(citation_url)}">',
                    "</a></span>",
                ]
                annotations.append([c.span()] + annotation)
        else:
            # Successfully matched citation
            case_name = trunc(best_case_name(opinion.cluster), 60, "...")
            safe_case_name = html.escape(case_name)
            opinion_url = html.escape(opinion.cluster.get_absolute_url())
            annotation = [
                f'<span class="citation" data-id="{opinion.pk}">'
                f'<a href="{opinion_url}"'
                f' aria-description="Citation for case: {safe_case_name}"'
                ">",
                "</a></span>",
            ]
            # Annotate all matched citations for the resource
            annotations.extend([[c.span()] + annotation for c in citations])
    return annotations


def create_cited_html(
    opinion: Opinion,
    citation_resolutions: Dict[
        MatchedResourceType, List[SupportedCitationType]
    ],
) -> str:
    """Using the opinion itself and a list of citations found within it, make
    the citations into links to the correct citations.

    :param opinion: The opinion to enhance
    :param citation_resolutions: A map of lists of citations in the opinion
    :return The new HTML containing citations
    """
    if opinion.source_is_html:  # If opinion was originally HTML...
        new_html = annotate_citations(
            plain_text=opinion.cleaned_text,
            annotations=generate_annotations(citation_resolutions),
            source_text=opinion.source_text,
            unbalanced_tags="skip",  # Don't risk overwriting existing tags
        )
    else:  # Else, present `source_text` wrapped in <pre> HTML tags...
        new_html = annotate_citations(
            plain_text=opinion.cleaned_text,
            annotations=[
                [a[0], f"</pre>{a[1]}", f'{a[2]}<pre class="inline">']
                for a in generate_annotations(citation_resolutions)
            ],
            source_text=f'<pre class="inline">{html.escape(opinion.source_text)}</pre>',
        )

    # Return the newly-annotated text
    return new_html
