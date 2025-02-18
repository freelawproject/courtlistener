import html
import re
from typing import Dict, List, Optional

from django.urls import reverse
from eyecite import annotate_citations, clean_text
from eyecite.models import IdCitation, ShortCaseCitation, SupraCitation

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


def generate_annotation(
    opinion: Opinion, extra_class: Optional[str] = None, pin_cite: str = ""
) -> List[str]:
    """Generate an HTML annotation for matched legal citations.

    :param opinion: An Opinion object that matched the citation.
    :param extra_class: An optional additional CSS class for styling.
    :param pin_cite: A pinpoint citation reference (e.g., "144-145, n. 6").
                      If provided, extracts the first numeric value for linking.
    :return: A list containing HTML elements representing the citation.
    """
    PIN_CITE_NUMBER_PATTERN = r"\d+"
    classes = ["citation"]
    if extra_class:
        classes.append(extra_class)

    case_name = trunc(best_case_name(opinion.cluster), 60, "...")
    safe_case_name = html.escape(case_name)

    valid_pin_cite_number = None
    if pin_cite:
        # Extract the first sequence of digits from the pin cite (e.g.,
        # "144" from "144-145, n. 6" or "609" from "at 609" or "123" from "at
        # 123, 124.")
        pin_cite_number_match = re.search(PIN_CITE_NUMBER_PATTERN, pin_cite)
        if pin_cite_number_match is not None:
            valid_pin_cite_number = pin_cite_number_match.group()

    # Construct the citation link
    base_url = opinion.cluster.get_absolute_url()
    link = (
        f"{base_url}#{valid_pin_cite_number}"
        if valid_pin_cite_number
        else base_url
    )

    annotation = [
        f'<span class="{" ".join(classes)}" data-id="{opinion.pk}">'
        f'<a href="{link}" aria-description="Citation for case: {safe_case_name}">',
        "</a></span>",
    ]
    return annotation


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
    from cl.opinion_page.views import make_citation_url_dict

    annotations: List[List] = []
    for opinion, citations in citation_resolutions.items():
        if opinion is NO_MATCH_RESOURCE:
            # Unsuccessfully matched...
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
                kwargs = make_citation_url_dict(**c.groups)
                citation_url = reverse("citation_redirector", kwargs=kwargs)
                annotation = [
                    '<span class="citation multiple-matches">'
                    f'<a href="{html.escape(citation_url)}">',
                    "</a></span>",
                ]
                annotations.append([c.span()] + annotation)
        else:
            # Successfully matched citation
            for c in citations:
                # TODO add ReferenceCitation
                if isinstance(
                    c, (SupraCitation, IdCitation, ShortCaseCitation)
                ):
                    # Generate extra class name based on object type
                    class_name = re.sub(
                        r"(?<!^)([A-Z])", r"-\1", c.__class__.__name__
                    ).lower()
                    if c.metadata.pin_cite:
                        annotation = generate_annotation(
                            opinion, class_name, c.metadata.pin_cite
                        )
                    else:
                        # We can have these citations types without a pin cite
                        annotation = generate_annotation(opinion, class_name)

                # Handle FullCaseCitation cases
                elif c.metadata.pin_cite:
                    # Case 1: FullCaseCitation with pin cite
                    # e.g. "334 U. S. 131, 144, n. 6"
                    annotation = generate_annotation(
                        opinion,
                        extra_class="pin-cite",
                        pin_cite=c.metadata.pin_cite,
                    )
                    annotations.append([c.full_span()] + annotation)

                else:
                    # Case 2: FullCaseCitation without pin cite
                    # e.g. "334 U. S. 131"
                    annotation = generate_annotation(opinion)

                annotations.append([c.span()] + annotation)
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
