#!/usr/bin/env python
from typing import Dict, Iterable, List, Optional, no_type_check

from asgiref.sync import async_to_sync, sync_to_async
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

from cl.citations.match_citations_queries import es_search_db_for_full_citation
from cl.citations.types import (
    MatchedResourceType,
    ResolvedFullCites,
    SupportedCitationType,
)
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.search.models import Opinion, RECAPDocument
from cl.search.selectors import get_clusters_from_citation_str

DEBUG = True


NO_MATCH_RESOURCE = Resource(case_citation(source_text="UNMATCHED_CITATION"))
MULTIPLE_MATCHES_RESOURCE = Resource(
    case_citation(
        source_text="MULTIPLE_MATCHES", page="999999", volume="999999"
    )
)


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
        db_search_results, _ = es_search_db_for_full_citation(full_citation)
        # If there is more than one result, return a placeholder with the
        # citation with multiple results

        if len(db_search_results) == 0:
            # If no citation is found use get_clusters_from_citation as a backup
            volume = full_citation.groups.get("volume")
            reporter = full_citation.corrected_reporter()
            page = full_citation.corrected_page()
            if (
                volume is not None
                and volume.isdigit()
                and reporter is not None
                and page is not None
            ):
                clusters, _count = async_to_sync(
                    get_clusters_from_citation_str
                )(volume=volume, reporter=reporter, page=page)

                # exclude self links
                if getattr(full_citation, "citing_opinion", False):
                    clusters = [
                        cluster
                        for cluster in clusters
                        if cluster.id
                        != full_citation.citing_opinion.cluster.pk
                    ]
                    _count = len(clusters)

                if _count == 1:
                    # return the first item by ordering key
                    return clusters[0].ordered_opinions.first()
                elif _count >= 2:
                    # if two or more remain return multiple matches
                    return MULTIPLE_MATCHES_RESOURCE

        if len(db_search_results) > 1:
            return MULTIPLE_MATCHES_RESOURCE

        # If there is one search result, try to return it
        if len(db_search_results) == 1:
            result_id = db_search_results[0]["id"]
            try:
                return Opinion.objects.get(pk=result_id)
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
