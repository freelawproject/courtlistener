# Code for importing Centralia structured opinion extractions into the DB
import logging
from enum import StrEnum
from typing import Any, cast

from django.db import transaction
from eyecite import get_citations
from juriscraper.lib.string_utils import titlecase

from cl.citations.tasks import HYPERSCAN_TOKENIZER
from cl.citations.utils import make_get_citations_kwargs
from cl.search.models import Opinion

logger = logging.getLogger(__name__)

# Courts whose opinion clusters may be ingested via Centralia's structured
# extraction. Kept narrow while the integration is being rolled out.
CENTRALIA_ENABLED_COURTS = {"scotus"}

# The only verdict centralia gives that means "fully accounted for, nothing
# to look at". Its other three -- ``scanned`` (no text layer), ``review``
# (something unplaced or warned about) and ``failed`` (no usable output) --
# all leave the text pipeline's own extraction in place.
INGESTIBLE_STATUS = "valid"

# Below this share of the text the pipeline already extracted, the
# structured read likely lost whole pages. Centralia legitimately drops
# running headers and page furniture, so the bar is deliberately low.
MIN_TEXT_COVERAGE = 0.5

# Opinion text fields that outrank `html`, the field a merge writes, for
# display and citation finding. See make_get_citations_kwargs.
FIELDS_OUTRANKING_HTML = (
    "xml_harvard",
    "xml_scan",
    "html_anon_2020",
    "html_columbia",
    "html_lawbox",
)


class StructuredExtractionStatus(StrEnum):
    """Outcome of running Centralia's structured extraction on a cluster."""

    # Doctor or Centralia returned an error
    ERROR = "error"
    # The read failed the quality checks, so the opinion was left untouched
    SKIPPED = "skipped"
    # Dry runs only: the read passed the quality checks but was not saved
    WOULD_INGEST = "would_ingest"
    INGESTED = "ingested"


# Centralia's opinion kind -> CL opinion type.
# CL has no per-curiam type, so per curiam opinions are stored as
# lead opinions with the per_curiam flag set. Kinds missing here, such as
# "order", fall back to lead in map_centralia_opinion_type.
CENTRALIA_OPINION_TYPES: dict[str, str] = {
    "majority": Opinion.LEAD,
    "per-curiam": Opinion.LEAD,
    "concurrence": Opinion.CONCURRENCE,
    "concurrence-in-result": Opinion.CONCURRENCE,
    "concurring-in-part-and-dissenting-in-part": Opinion.CONCUR_IN_PART,
    "dissent": Opinion.DISSENT,
    "addendum": Opinion.ADDENDUM,
    "rehearing": Opinion.REHEARING,
}


def normalize_centralia_opinion_type(centralia_type: str | None) -> str:
    """Normalize a Centralia opinion type for lookups and comparisons.

    :param centralia_type: The `opinions[].type` value returned by Centralia.
    :return: The type, stripped and lowercased; "" when missing.
    """
    return (centralia_type or "").strip().lower()


def map_centralia_opinion_type(centralia_type: str | None) -> str:
    """Map a Centralia opinion type to a CL opinion type.

    Combined is deliberately never returned. It means an import could not
    tell one writing from another, and Centralia's whole purpose is to say
    how many writings a document holds and where each begins, so a lone
    writing is the lead opinion, not a combined one. Unrecognized types,
    including "order", are also lead: a paper Centralia cannot name is
    likelier to be the decision itself than a concurrence or dissent, both
    of which it names.

    :param centralia_type: The `opinions[].type` value returned by Centralia.
    :return: The CL opinion type.
    """
    return CENTRALIA_OPINION_TYPES.get(
        normalize_centralia_opinion_type(centralia_type), Opinion.LEAD
    )


def _wrap(html: str) -> str:
    """Scope a payload fragment under the class CL's stylesheet targets.

    :param html: Centralia markup for one writing.
    :return: The wrapped fragment, or "" when there is nothing to wrap.
    """
    html = (html or "").strip()
    if not html:
        return ""
    return f'<div class="centralia">{html}</div>'


def _syllabus_html(payload: dict) -> str:
    """Join the syllabus paragraphs of a structured read into HTML.

    :param payload: Doctor's structured payload.
    :return: One <p> per paragraph of `sections.syllabus.html`, which holds
    inline markup only; "" when the read found no syllabus.
    """
    syllabus = (payload.get("sections") or {}).get("syllabus") or {}
    return "".join(
        f"<p>{paragraph.strip()}</p>"
        for paragraph in syllabus.get("html") or []
        if (paragraph or "").strip()
    )


def _payload_text_length(payload: dict) -> int:
    """Total plain text the structured read recovered.

    :param payload: Doctor's structured payload.
    :return: Combined length of the headmatter and every writing's text.
    """
    total = len((payload.get("headmatter") or {}).get("text") or "")
    for writing in payload.get("opinions") or []:
        total += len(writing.get("text") or "")
    return total


def should_ingest(opinion: Opinion, payload: dict) -> tuple[bool, str]:
    """Decide whether a structured read is good enough to store.

    Ingesting a bad read is worse than keeping the flat text, because the
    HTML it writes outranks ``plain_text`` for display, so this asks only
    whether the read itself is complete and trustworthy. What KIND of paper
    it is does not matter: centralia's ``doc_type`` is still approximate,
    and a filing can turn out to carry the court's writing.

    :param opinion: The opinion the payload was read from.
    :param payload: Doctor's structured payload.
    :return: A 2-tuple of whether to ingest and the reason, for logging.
    """
    status = payload.get("status") or ""
    if status != INGESTIBLE_STATUS:
        return False, f"status={status}, not a clean read"

    diagnostics = payload.get("diagnostics") or {}
    # Per-page facts that mean the same thing even when the overall status
    # came back valid: an image page, a page with no text layer, or a page
    # whose CID-encoded fonts extract as Mojibake.
    for field, why in (
        ("scan_pages", "scanned pages"),
        ("text_missing_pages", "pages with no text layer"),
        ("cid_pages", "CID-encoded pages"),
    ):
        if pages := diagnostics.get(field):
            return False, f"{why} {list(pages)[:5]}, needs OCR"  # type: ignore

    writings = payload.get("opinions") or []
    if not writings:
        return False, "no writings found"
    if not any((w.get("html") or "").strip() for w in writings):
        return False, "writings carry no html"
    # An ingest wants centralia's clean markup, not its review page. The
    # chip badge marks a payload from before the ingest-facing render.
    if 'class="chip"' in (writings[0].get("html") or ""):
        return False, "review-flavored payload, doctor needs centralia>=0.0.5"

    # Guard against a silently partial read by comparing against whatever
    # the existing extraction already managed.
    existing = len(opinion.plain_text or "")
    recovered = _payload_text_length(payload)
    if existing and recovered < existing * MIN_TEXT_COVERAGE:
        return False, (
            f"recovered {recovered} chars vs {existing} already extracted "
            f"(under {MIN_TEXT_COVERAGE:.0%})"
        )

    return True, f"status={status}"


def check_structured_extraction(
    opinion: Opinion, data: dict[str, Any], skip_validation: bool = False
) -> tuple[bool, str]:
    """Decide whether a structured extraction can be merged into an opinion.

    Runs should_ingest and requires every writing Centralia found to carry
    HTML. A read with several writings is only accepted when the opinion is
    its cluster's only one, since merging splits it into sibling opinions;
    this also stops a cluster that was already split from being split again.
    Nothing is changed or logged, so dry runs can use it too.

    :param opinion: The opinion the extraction was read from.
    :param data: A successful response payload from Doctor's structured
    opinion endpoint.
    :param skip_validation: Whether to skip should_ingest's quality checks.
    Only the writings with HTML that merging needs are still required, so a
    partial or garbled read passes. Opinions with text in a field that
    outranks `html` are still refused, since the merged HTML would be
    neither shown nor cited. Meant for previews and one-off fixes.
    :return: A 2-tuple of whether the extraction can be merged and the
    reason, for logging.
    """
    if skip_validation:
        # Without validation, the command no longer filters these opinions
        # out by source or anon 2020 content, so check them here.
        if outranking := [
            field
            for field in FIELDS_OUTRANKING_HTML
            if getattr(opinion, field)
        ]:
            return False, (
                f"text in {', '.join(outranking)} outranks html, so the "
                "extraction would be neither shown nor cited"
            )
        reason = f"status={data.get('status') or ''}, validation skipped"
    else:
        ingestible, reason = should_ingest(opinion, data)
        if not ingestible:
            return False, reason
    writings = data.get("opinions") or []
    if not writings:
        return False, "no writings found"
    # A sibling without HTML would be a blank opinion on the case page
    if not all((w.get("html") or "").strip() for w in writings):
        return False, "a writing carries no html"
    if len(writings) > 1 and (
        others := opinion.cluster.sub_opinions.filter(
            main_version__isnull=True
        )
        .exclude(pk=opinion.pk)
        .count()
    ):
        return False, (
            f"found {len(writings)} writings, but the cluster already has "
            f"{others + 1} opinions; only a cluster's only opinion can be "
            "split"
        )
    return True, reason


def count_citations(document: Opinion) -> int:
    """Count the citations eyecite finds in an opinion, without saving any.

    Reads the same field, with the same cleanup, as the citation finder, so
    the count matches what find_citations_and_parentheticals_for_opinion_by_pks
    would extract before resolving. Citations are not resolved, so the count
    includes citations to cases that are not in CL.

    :param document: The opinion to read. It may be unsaved.
    :return: The number of citations found.
    """
    return sum(
        len(get_citations(tokenizer=HYPERSCAN_TOKENIZER, **kwargs))
        for kwargs in make_get_citations_kwargs(document)
    )


def compare_structured_extraction(
    opinion: Opinion, data: dict[str, Any]
) -> dict[str, int]:
    """Compare an opinion's current content with a structured extraction.

    Meant for quality control: run it before merging, since merging replaces
    the opinion's current content. Citation counting runs eyecite on both
    versions, so this is too slow to run on every ingest.

    :param opinion: The opinion as currently stored.
    :param data: A successful response payload from Doctor's structured
    opinion endpoint.
    :return: The character counts of the current `plain_text` and of the
    extracted text, and the number of citations eyecite finds in the
    opinion's current content and in the extracted HTML.
    """
    extracted = Opinion(
        html="".join(
            _wrap(writing.get("html") or "")
            for writing in data.get("opinions") or []
        )
    )
    return {
        "old_chars": len(opinion.plain_text or ""),
        "new_chars": _payload_text_length(data),
        "old_citations": count_citations(opinion),
        "new_citations": count_citations(extracted),
    }


def _ordering_keys(writings: list[dict[str, Any]]) -> list[int]:
    """Pick an ordering key for each writing of a structured read.

    :param writings: The `opinions` of Doctor's structured payload.
    :return: Centralia's `order` for each writing when they are distinct
    positive integers. Otherwise, 1 to N by position, since the keys must be
    unique within a cluster.
    """
    orders = [writing.get("order") for writing in writings]
    if len(set(orders)) == len(orders) and all(
        type(order) is int and order > 0 for order in orders
    ):
        return cast(list[int], orders)
    return list(range(1, len(writings) + 1))


def _apply_writing(
    opinion: Opinion, writing: dict[str, Any], ordering_key: int
) -> None:
    """Copy one writing of a structured read onto an opinion, unsaved.

    Sets the opinion's HTML, ordering key, type, per curiam flag and, unless
    it is per curiam, its author string when the read names an author.

    :param opinion: The opinion to update. It may be new.
    :param writing: One of the `opinions` of Doctor's structured payload.
    It must carry HTML.
    :param ordering_key: The writing's ordering key, from _ordering_keys.
    :return: None
    """
    opinion.html = _wrap(writing["html"])
    opinion.ordering_key = ordering_key
    centralia_type = writing.get("type")
    opinion.type = map_centralia_opinion_type(centralia_type)
    opinion.per_curiam = (
        normalize_centralia_opinion_type(centralia_type) == "per-curiam"
    )
    if not opinion.per_curiam:
        if author_name := writing.get("author_name"):
            opinion.author_str = titlecase(author_name)


def merge_structured_opinion_into_cl_opinion(
    opinion: Opinion, data: dict[str, Any], skip_validation: bool = False
) -> tuple[list[int], str]:
    """Merge a Centralia structured extraction into a CL opinion and save it.

    Stores the first writing's HTML in `Opinion.html` along with the
    opinion's ordering key, type, per curiam flag and author string, and the
    syllabus and headmatter in `OpinionCluster.syllabus` and `.headmatter`.
    A cluster field is only replaced when the read found that section, so
    existing content is never blanked.

    When the read found several writings, such as a majority and a dissent,
    each writing after the first becomes a new opinion in the cluster, with
    its text in `plain_text`. New opinions share the original opinion's
    `local_path`, but not its `sha1` or `download_url`, so duplicate and
    version detection don't mistake them for copies of it.

    Extractions that fail check_structured_extraction are logged and
    skipped, leaving the opinion and cluster untouched. Errors while saving
    are raised, and nothing is saved.

    Callers must run find_citations_and_parentheticals_for_opinion_by_pks
    on every returned opinion afterward to find and store citations in the
    new HTML.

    :param opinion: The opinion to update. It must be its cluster's only
    opinion when the read found several writings.
    :param data: A successful response payload from Doctor's structured
    opinion endpoint.
    :param skip_validation: Whether to skip the quality checks. See
    check_structured_extraction. A partial or garbled read can then replace
    the opinion's existing content.
    :return: A 2-tuple of the ids of the saved opinions, the updated one
    first and empty when skipped, and the reason, for logging.
    """
    log_extra = {
        "opinion_id": opinion.pk,
        "opinion_cluster_id": opinion.cluster_id,
    }
    mergeable, reason = check_structured_extraction(
        opinion, data, skip_validation=skip_validation
    )
    if not mergeable:
        logger.warning(
            "Skipped structured extraction for cluster %s: %s",
            opinion.cluster_id,
            reason,
            extra=log_extra,
        )
        return [], reason

    # check_structured_extraction has already rejected writings without HTML
    writings = data["opinions"]
    ordered = sorted(
        zip(_ordering_keys(writings), writings), key=lambda pair: pair[0]
    )
    # The first writing, normally the majority, goes on the existing opinion
    # so citations to it and its URL keep pointing at the decision.
    _apply_writing(opinion, ordered[0][1], ordered[0][0])
    siblings = []
    for ordering_key, writing in ordered[1:]:
        sibling = Opinion(
            cluster=opinion.cluster,
            plain_text=writing.get("text") or "",
            local_path=opinion.local_path.name,
        )
        _apply_writing(sibling, writing, ordering_key)
        siblings.append(sibling)

    cluster = opinion.cluster
    cluster_fields = []
    if syllabus := _wrap(_syllabus_html(data)):
        cluster.syllabus = syllabus
        cluster_fields.append("syllabus")
    headmatter = (data.get("headmatter") or {}).get("html") or ""
    if headmatter := _wrap(headmatter):
        cluster.headmatter = headmatter
        cluster_fields.append("headmatter")

    with transaction.atomic():
        opinion.save(
            update_fields=[
                "date_modified",
                "html",
                "ordering_key",
                "type",
                "per_curiam",
                "author_str",
            ]
        )
        # Saved one at a time, unlike bulk_create, so the signals that
        # index opinions in search run for each one.
        for sibling in siblings:
            sibling.save()
        if cluster_fields:
            cluster.save(update_fields=["date_modified", *cluster_fields])
    return [opinion.pk, *(sibling.pk for sibling in siblings)], reason
