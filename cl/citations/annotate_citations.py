import html
import re
from typing import Dict, List

from eyecite import annotate_citations, clean_text
from eyecite.models import FullCaseCitation

from cl.citations.match_citations import NO_MATCH_RESOURCE
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


def calculate_pin_cite_absolute_span(
    cite_end: int, pin_cite_start: int, pin_cite_text: str
) -> tuple[int, int]:
    """Calculate the absolute start and end positions of a pin cite in the
    plain text.

    :param cite_end: The end position of the citation in the plain text.
    :param pin_cite_start: The relative start position of the pin cite within
    the substring.
    :param pin_cite_text: The text of the pin cite.
    :return: A tuple containing the absolute start and end positions of the pin
    cite. Example: (start, end)
    """
    absolute_pin_cite_start = cite_end + pin_cite_start
    absolute_pin_cite_end = absolute_pin_cite_start + len(pin_cite_text)
    return absolute_pin_cite_start, absolute_pin_cite_end


def generate_pin_cite_annotation(
    opinion: Opinion, pin_cite_number: str, case_name: str
) -> list[str]:
    """Generate the HTML annotation for a pin cite.

    :param opinion: The opinion object matched to the pin cite.
    :param pin_cite_number: The pin cite number extracted from the text.
    :param case_name: The name of the case, truncated and sanitized for use in
    HTML.
    :return: A list of strings representing the HTML annotation.

    Example: ['<span class="citation pin-cite">...</span>']
    """
    safe_case_name = html.escape(case_name)
    return [
        f'<span class="citation pin-cite" data-id="{opinion.pk}">'
        f'<a href="{opinion.cluster.get_absolute_url()}#{pin_cite_number}"'
        f' aria-description="Citation for case: {safe_case_name}"'
        ">",
        "</a></span>",
    ]


def get_pin_cite_annotation(
    citation: FullCaseCitation, plain_text: str, opinion: Opinion
) -> list[tuple[int, int] | str]:
    """Calculate the pin cite span and generate the annotation for a given
    citation

    This function calculates the span of a pin cite within the plain text of
    an opinion and generates an HTML annotation for the pin cite. The
    annotation includes a link to the specific pin cite location in the opinion.

    :param citation: The citation object containing the pin cite and its
    metadata.
    :param plain_text: The plain text of the opinion where the citation was
    found.
    :param opinion: The opinion object matched to the pin cite.
    :return: A list containing the pin cite span (start and end indices) and
    the HTML annotation.

    Example: [(start, end), '<span class="citation pin-cite">...</span>']
    """
    PIN_CITE_NUMBER_PATTERN = r"\d+"
    MAX_PIN_CITE_SEARCH_LENGTH = 100

    # Calculate the pin cite span manually since it's not directly available
    cite_start, cite_end = citation.span()
    pin_cite_text = citation.metadata.pin_cite

    # Extract a substring from the opinion text starting at the end of the
    # citation
    text_after_citation = plain_text[
        cite_end : cite_end + MAX_PIN_CITE_SEARCH_LENGTH
    ]
    pin_cite_start = text_after_citation.find(pin_cite_text)

    # Calculate the absolute start and end positions of the pin cite in the
    # plain text
    absolute_pin_cite_start, absolute_pin_cite_end = (
        calculate_pin_cite_absolute_span(
            cite_end, pin_cite_start, pin_cite_text
        )
    )

    # Extract the first sequence of digits from the pin cite (e.g.,
    # "144" from "144-145, n. 6")
    pin_cite_number_match = re.search(
        PIN_CITE_NUMBER_PATTERN,
        plain_text[absolute_pin_cite_start:absolute_pin_cite_end],
    )

    # Generate the annotation only if the pin cite contains a valid number
    case_name = trunc(best_case_name(opinion.cluster), 60, "...")
    safe_case_name = html.escape(case_name)
    pin_cite_annotation = generate_pin_cite_annotation(
        opinion, pin_cite_number_match.group(), safe_case_name
    )

    return [
        (absolute_pin_cite_start, absolute_pin_cite_end)
    ] + pin_cite_annotation


def generate_annotations(
    citation_resolutions: Dict[
        MatchedResourceType, List[SupportedCitationType]
    ],
    plain_text: str,
) -> List[List]:
    """Generate the string annotations to insert into the opinion text

    :param citation_resolutions: A map of lists of citations in the opinion
    :param plain_text: The cleaned text containing the citations.
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
            case_name = trunc(best_case_name(opinion.cluster), 60, "...")
            safe_case_name = html.escape(case_name)
            # Get the pin cite if we used one to match it with an opinion.
            # This is for a special pin cite like "8 Wheat. 574" which points
            # to "8 Wheat. 543"
            pin_cite = (
                f"#{opinion.page_pin_cite}"
                if hasattr(opinion, "page_pin_cite")
                else ""
            )
            annotation = [
                f'<span class="citation" data-id="{opinion.pk}">'
                f'<a href="{opinion.cluster.get_absolute_url()}{pin_cite}"'
                f' aria-description="Citation for case: {safe_case_name}"'
                ">",
                "</a></span>",
            ]
        for c in citations:
            annotations.append([c.span()] + annotation)

            if isinstance(opinion, Opinion) and isinstance(
                c, FullCaseCitation
            ):
                # We only want to annotate citations with a corresponding
                # match, we do this here because not all citations may have a
                # pin cite in the FullCaseCitation metadata
                if c.metadata.pin_cite:
                    pin_cite_annotation = get_pin_cite_annotation(
                        c, plain_text, opinion
                    )
                    annotations.append(pin_cite_annotation)

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
            annotations=generate_annotations(
                citation_resolutions, opinion.cleaned_text
            ),
            source_text=opinion.source_text,
            unbalanced_tags="skip",  # Don't risk overwriting existing tags
        )
    else:  # Else, present `source_text` wrapped in <pre> HTML tags...
        new_html = annotate_citations(
            plain_text=opinion.cleaned_text,
            annotations=[
                [a[0], f"</pre>{a[1]}", f'{a[2]}<pre class="inline">']
                for a in generate_annotations(
                    citation_resolutions, opinion.cleaned_text
                )
            ],
            source_text=f'<pre class="inline">{html.escape(opinion.source_text)}</pre>',
        )

    # Return the newly-annotated text
    return new_html
