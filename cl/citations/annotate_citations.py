import html
import re
from typing import Dict, List

from eyecite import annotate_citations, clean_text

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
            # Get the pincite if we used one to match it with an opinion.
            # This is for a special pincite like "8 Wheat. 574" which points
            # to "8 Wheat. 543"
            pincite = (
                f"#{opinion.pincite_used}"
                if hasattr(opinion, "pincite_used")
                else ""
            )
            annotation = [
                f'<span class="citation" data-id="{opinion.pk}">'
                f'<a href="{opinion.cluster.get_absolute_url()}{pincite}"'
                f' aria-description="Citation for case: {safe_case_name}"'
                ">",
                "</a></span>",
            ]
        for c in citations:
            annotations.append([c.span()] + annotation)

            if isinstance(opinion, Opinion):
                # We only want to annotate citations with a corresponding
                # match, we do this here because not all citations may have a
                # pin cite in the FullCaseCitation metadata
                try:
                    if c.metadata.pin_cite:
                        # We don't have span for pincite, so we need to
                        # calculate it manually based on the citation span
                        cite_start, cite_end = c.span()
                        target_pin_cite = c.metadata.pin_cite
                        # We get a partial string from the original opinion
                        # starting from the end of citation to the end of
                        # citation plus 100
                        partial_string = plain_text[cite_end : cite_end + 100]
                        pin_cite_start = partial_string.find(target_pin_cite)
                        # Then we calculate the absolute span for the pincite
                        absolute_pin_cite_start = cite_end + pin_cite_start
                        absolute_pin_cite_end = absolute_pin_cite_start + len(
                            target_pin_cite
                        )

                        # We get the first sequence of digits in case the
                        # pincite is a range or it has non sequence numbers.
                        # e.g. in "144-145, n. 6" we extract the 144
                        extract_pincite = re.search(
                            r"\d+",
                            plain_text[
                                absolute_pin_cite_start:absolute_pin_cite_end
                            ],
                        )

                        if extract_pincite:
                            # We only annotate the pincite if we are sure
                            # that it is a number
                            case_name = trunc(
                                best_case_name(opinion.cluster), 60, "..."
                            )
                            safe_case_name = html.escape(case_name)
                            pincite_annotation = [
                                f'<span class="citation pin-cite" data-id="{opinion.pk}">'
                                f'<a href="{opinion.cluster.get_absolute_url()}#{extract_pincite.group()}"'
                                f' aria-description="Citation for case: {safe_case_name}"'
                                ">",
                                "</a></span>",
                            ]
                            annotations.append(
                                [
                                    (
                                        absolute_pin_cite_start,
                                        absolute_pin_cite_end,
                                    )
                                ]
                                + pincite_annotation
                            )
                except Exception as e:
                    print("Error: ", e)
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
