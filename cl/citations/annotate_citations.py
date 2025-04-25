import html
import re
from typing import Dict, List

from django.urls import reverse
from eyecite import annotate_citations
from eyecite.models import IdCitation, SupraCitation

from cl.citations.match_citations import (
    MULTIPLE_MATCHES_RESOURCE,
    NO_MATCH_RESOURCE,
)
from cl.citations.types import MatchedResourceType, SupportedCitationType
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.string_utils import trunc


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
                if not c.groups or not c.groups.get("reporter"):
                    continue

                kwargs = make_citation_url_dict(
                    c.groups["reporter"],
                    c.groups.get("volume"),
                    c.groups.get("page"),
                )
                citation_url = reverse("citation_redirector", kwargs=kwargs)
                annotation = [
                    '<span class="citation multiple-matches">'
                    f'<a href="{html.escape(citation_url)}">',
                    "</a></span>",
                ]
                annotations.append([c.span()] + annotation)
        else:
            # Successfully matched citations
            for citation in citations:
                opinion_url = html.escape(opinion.cluster.get_absolute_url())
                case_name = trunc(best_case_name(opinion.cluster), 60, "...")
                safe_case_name = html.escape(case_name)
                # if pin cite exists - add page to url if number
                # if multiple pages - link to first e.g. 122-123, add #122
                if citation.metadata.pin_cite:
                    match = re.search(r"\d+", citation.metadata.pin_cite)
                    if match:
                        opinion_url = f"{opinion_url}#{match.group()}"
                annotation = [
                    f'<span class="citation" data-id="{opinion.pk}">'
                    f'<a href="{opinion_url}"'
                    f' aria-description="Citation for case: {safe_case_name}"'
                    ">",
                    "</a></span>",
                ]
                if isinstance(citation, (IdCitation, SupraCitation)):
                    # for ID and Supra citations use full span to
                    # to avoid unbalanced html
                    annotation_span = citation.full_span()
                else:
                    annotation_span = citation.span_with_pincite()

                annotations.append([annotation_span] + annotation)
    return annotations


def create_cited_html(
    citation_resolutions: Dict[
        MatchedResourceType, List[SupportedCitationType]
    ],
) -> str:
    """Using the opinion itself and a list of citations found within it, make
    the citations into links to the correct citations.

    :param citation_resolutions: A map of lists of citations in the opinion
    :return The new HTML containing citations
    """
    document = list(citation_resolutions.values())[0][0].document

    if document.markup_text:  # If opinion was originally HTML...
        new_html = annotate_citations(
            plain_text=document.plain_text,
            annotations=generate_annotations(citation_resolutions),
            source_text=document.markup_text,
            unbalanced_tags="skip",  # Don't risk overwriting existing tags
            offset_updater=document.plain_to_markup,
        )
    else:  # Else, present `source_text` wrapped in <pre> HTML tags...
        new_html = annotate_citations(
            plain_text=document.plain_text,
            annotations=[
                [a[0], f"</pre>{a[1]}", f'{a[2]}<pre class="inline">']
                for a in generate_annotations(citation_resolutions)
            ],
            source_text=f'<pre class="inline">{html.escape(document.source_text)}</pre>',
        )

    # Return the newly-annotated text
    return new_html
