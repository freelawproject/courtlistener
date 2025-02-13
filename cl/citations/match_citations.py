#!/usr/bin/env python
from typing import Dict, Iterable, List, Optional, no_type_check

from elasticsearch_dsl.response import Hit
from eyecite import resolve_citations
from eyecite.models import (
    CitationBase,
    FullCaseCitation,
    FullJournalCitation,
    FullLawCitation,
    Resource,
    ShortCaseCitation,
    SupraCitation,
)
from eyecite.test_factories import case_citation
from eyecite.utils import strip_punct

from cl.citations.match_citations_queries import (
    es_search_db_for_full_citation,
    es_search_db_for_partial_citation,
)
from cl.citations.types import (
    MatchedResourceType,
    ResolvedFullCites,
    SupportedCitationType,
)
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.search.models import Opinion, RECAPDocument

DEBUG = True


NO_MATCH_RESOURCE = Resource(case_citation(source_text="UNMATCHED_CITATION"))


def filter_by_matching_antecedent(
    opinion_candidates: Iterable[Opinion],
    antecedent_guess: Optional[str],
) -> Optional[Opinion]:
    if not antecedent_guess:
        return None

    antecedent_guess = strip_punct(antecedent_guess)
    candidates: List[Opinion] = []

    for o in opinion_candidates:
        if antecedent_guess in best_case_name(o.cluster):
            candidates.append(o)

    # Remove duplicates and only accept if one candidate remains
    candidates = list(set(candidates))
    return candidates[0] if len(candidates) == 1 else None


def resolve_fullcase_citation(
    full_citation: FullCaseCitation,
) -> MatchedResourceType:
    # Case 1: FullCaseCitation
    if type(full_citation) is FullCaseCitation:
        db_search_results: list[Hit]
        # Look for matches using full citation
        db_search_results, _ = es_search_db_for_full_citation(full_citation)
        if len(db_search_results) == 0:
            # We didn't get an exact match on the volume/reporter/page.
            # Perhaps it's a pin cite. Find closest citations filtering by
            # volume and reporter and excluding self cites. e.g. 8 Wheat. 574
            # points to 8 Wheat. 543
            db_search_results, _ = es_search_db_for_partial_citation(
                full_citation
            )

        # If there is one search result, try to return it
        if len(db_search_results) == 1:
            result_id = db_search_results[0]["id"]
            try:
                opinion = Opinion.objects.get(pk=result_id)
                if hasattr(db_search_results[0], "page_pin_cite"):
                    opinion.page_pin_cite = db_search_results[0].page_pin_cite
                return opinion
            except (Opinion.DoesNotExist, Opinion.MultipleObjectsReturned):
                pass

    # Case 2: FullLawCitation (TODO: implement support)
    elif type(full_citation) is FullLawCitation:
        pass

    # Case 3: FullJournalCitation (TODO: implement support)
    elif type(full_citation) is FullJournalCitation:
        pass

    # If no Opinion can be matched, just return a placeholder object
    return NO_MATCH_RESOURCE


def resolve_shortcase_citation(
    short_citation: ShortCaseCitation,
    resolved_full_cites: ResolvedFullCites,
) -> Optional[Opinion]:
    candidates: List[Opinion] = []
    matched_opinions = [
        o for c, o in resolved_full_cites if type(o) is Opinion
    ]
    for opinion in matched_opinions:
        for c in opinion.cluster.citations.all():
            if (
                short_citation.corrected_reporter() == c.reporter
                and short_citation.groups["volume"] == str(c.volume)
            ):
                candidates.append(opinion)

    # Remove duplicates
    candidates = list(set(candidates))

    # Only accept if one candidate remains
    if len(candidates) == 1:
        return candidates[0]

    # Otherwise, try to refine further using the antecedent guess
    else:
        return filter_by_matching_antecedent(
            candidates, short_citation.metadata.antecedent_guess
        )


def resolve_supra_citation(
    supra_citation: SupraCitation,
    resolved_full_cites: ResolvedFullCites,
) -> Optional[Opinion]:
    matched_opinions = [
        o for c, o in resolved_full_cites if type(o) is Opinion
    ]
    return filter_by_matching_antecedent(
        matched_opinions, supra_citation.metadata.antecedent_guess
    )


@no_type_check
def do_resolve_citations(
    citations: List[CitationBase], citing_object: Opinion | RECAPDocument
) -> Dict[MatchedResourceType, List[SupportedCitationType]]:
    # Set the citing opinion on FullCaseCitation objects for later matching
    for c in citations:
        if type(c) is FullCaseCitation:
            if isinstance(citing_object, Opinion):
                c.citing_opinion = citing_object
            elif isinstance(citing_object, RECAPDocument):
                # if the object doing the citing is a RECAPDocument,
                # refer to it as a citing document.
                c.citing_document = citing_object
            else:
                raise "Unknown citing type."

    # Call and return eyecite's resolve_citations() function
    return resolve_citations(
        citations=citations,
        resolve_full_citation=resolve_fullcase_citation,
        resolve_shortcase_citation=resolve_shortcase_citation,
        resolve_supra_citation=resolve_supra_citation,
    )
