# Code for importing Centralia structured opinion extractions into the DB
from cl.search.models import Opinion

# The only verdict centralia gives that means "fully accounted for, nothing
# to look at". Its other three -- ``scanned`` (no text layer), ``review``
# (something unplaced or warned about) and ``failed`` (no usable output) --
# all leave the text pipeline's own extraction in place.
INGESTIBLE_STATUS = "valid"

# Below this share of the text the pipeline already extracted, the
# structured read likely lost whole pages. Centralia legitimately drops
# running headers and page furniture, so the bar is deliberately low.
MIN_TEXT_COVERAGE = 0.5


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
