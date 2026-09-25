"""Install centralia's structured opinion extraction onto CL models.

Doctor's ``/extract/opinion/structured/`` endpoint reads a digital court PDF
with centralia and returns the case-level criteria, one entry per writing
with its own HTML, and the cover page as portable inline-styled markup.
"""

import logging
import re
from datetime import date

from asgiref.sync import async_to_sync
from django.db import transaction
from django.utils.html import escape
from httpx import HTTPError

from cl.lib.microservice_utils import microservice
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    Docket,
    Opinion,
    OriginatingCourtInformation,
    RECAPDocument,
)

logger = logging.getLogger(__name__)

# The only verdict centralia gives that means "fully accounted for, nothing
# to look at". Its other three -- ``scanned`` (no text layer), ``review``
# (something unplaced or warned about) and ``failed`` (no usable output) --
# all leave the text pipeline's own extraction in place.
INSTALLABLE_STATUS = "valid"

# Below this share of the text the pipeline already extracted, the
# structured read likely lost whole pages. Centralia legitimately drops
# running headers and page furniture, so the bar is deliberately low.
MIN_TEXT_COVERAGE = 0.5

# Centralia names the status the way the court prints it; CL stores its own
# constants. Anything unrecognized is left alone rather than guessed at.
PRECEDENTIAL_STATUS_MAP = {
    "precedential": PRECEDENTIAL_STATUS.PUBLISHED,
    "published": PRECEDENTIAL_STATUS.PUBLISHED,
    "non-precedential": PRECEDENTIAL_STATUS.UNPUBLISHED,
    "nonprecedential": PRECEDENTIAL_STATUS.UNPUBLISHED,
    "unpublished": PRECEDENTIAL_STATUS.UNPUBLISHED,
    "errata": PRECEDENTIAL_STATUS.ERRATA,
    "in-chambers": PRECEDENTIAL_STATUS.IN_CHAMBERS,
    "relating-to": PRECEDENTIAL_STATUS.RELATING_TO,
    "separate": PRECEDENTIAL_STATUS.SEPARATE,
}


def get_structured_read(
    item: Opinion | RECAPDocument, court_id: str
) -> dict | None:
    """Ask doctor for a structured extraction of a stored PDF.

    The endpoint self-gates: a court centralia has no reader for answers
    UNKNOWN_COURT, and one it has not finished reviewing answers
    COURT_NOT_RELEASED, so callers need no allowlist of their own.

    :param item: The record whose stored file should be read. Any model
        carrying a PDF works -- an ``Opinion`` from a court's own website or
        a ``RECAPDocument`` from PACER.
    :param court_id: The court that issued it. Passed explicitly because
        the two models reach their court by different paths.
    :return: Doctor's payload, or None when the court is not supported or
        the call failed.
    """
    try:
        response = async_to_sync(microservice)(
            service="opinion-structured",
            item=item,
            data={"court_id": court_id},
        )
    except HTTPError:
        logger.warning(
            "opinion-structured transport failure for %s",
            court_id,
            exc_info=True,
        )
        return None
    if not response.is_success:
        try:
            code = response.json().get("error_code", "")
        except ValueError:
            code = ""
        if code in ("UNKNOWN_COURT", "COURT_NOT_RELEASED"):
            logger.info("No structured extraction for %s: %s", court_id, code)
        else:
            logger.error(
                "Error from opinion-structured microservice: %s",
                response.status_code,
                extra=dict(
                    item_id=item.pk,
                    court_id=court_id,
                    fingerprint=[f"{court_id}-opinion-structured-failure"],
                ),
            )
        return None
    return response.json()


def get_structured_opinion(opinion: Opinion) -> dict | None:
    """Ask doctor for a structured extraction of an opinion's PDF.

    :param opinion: The opinion to read.
    :return: Doctor's payload, or None when the court is not supported or
        the call failed.
    """
    return get_structured_read(opinion, opinion.cluster.docket.court_id)


def read_recap_caption(
    rd: RECAPDocument, court_id: str
) -> tuple[str | None, bool, str]:
    """Read the case name a PACER document prints on its own cover.

    PACER names a docket after the first defendant, so a docket's case name
    can name a different party than the paper is about -- an opinion "as to"
    a co-defendant -- and it is never the fuller caption the court itself
    printed. Centralia reads that caption off the page.

    Two different answers come back when it cannot. A pre-printed form is
    not the court's writing at all: its words belong to the Administrative
    Office, its blanks parse as party names, and every quality measure reads
    clean because there is no prose in it to be wrong about -- so the caller
    should ingest nothing. Anything else (a court centralia has not
    released, a scan, a read left for review) simply means no caption is
    available here, and the caller's own naming stands.

    :param rd: The PACER document to read.
    :param court_id: The court that issued it.
    :return: A 3-tuple of the caption (None when unavailable), whether the
        paper is rote and should not be ingested at all, and the reason.
    """
    payload = get_structured_read(rd, court_id)
    if payload is None:
        return None, False, "no structured read"

    diagnostics = payload.get("diagnostics") or {}
    if diagnostics.get("is_form"):
        return None, True, f"form={payload.get('form') or 'unnamed'}"

    status = payload.get("status") or ""
    if status != INSTALLABLE_STATUS:
        return None, False, f"status={status}"

    name = ((payload.get("cluster") or {}).get("case_name") or "").strip()
    if not name:
        return None, False, "no case name on the cover"
    return name, False, "ok"


# Words that carry no identity in a caption, so they never make two names
# match: the government's own styling, procedural noise, and party roles.
_CAPTION_NOISE = frozenset(
    {
        "united",
        "states",
        "state",
        "of",
        "america",
        "usa",
        "et",
        "al",
        "and",
        "the",
        "in",
        "re",
        "matter",
        "petitioner",
        "petitioners",
        "respondent",
        "respondents",
        "plaintiff",
        "plaintiffs",
        "defendant",
        "defendants",
        "appellant",
        "appellants",
        "appellee",
        "appellees",
        "jr",
        "sr",
        "ii",
        "iii",
        "iv",
    }
)


def _identifying_words(name: str) -> set[str]:
    """The words in a case name that actually identify a party.

    Drops the government's styling, party roles and generation suffixes, and
    the defendant numbers PACER prints ("(4)"), leaving surnames and the
    distinctive words of an entity's name.

    :param name: A case name, in any casing.
    :return: The lowercased identifying words.
    """
    lowered = re.sub(r"\bvs?\.?\b", " ", (name or "").lower())
    words = re.findall(r"[a-z][a-z'-]+", lowered)
    return {w for w in words if w not in _CAPTION_NOISE and len(w) > 1}


def same_case(docket_name: str, caption: str) -> bool:
    """Whether a docket's case name and a printed caption name one case.

    PACER's docket name is a short form of the same case far more often than
    it is the wrong one: "United States v. Canaca" against a cover reading
    "UNITED STATES OF AMERICA v. EDIMAR DABLADO CANACA" is one defendant
    written two ways. But a criminal docket is named for its first defendant,
    so "United States v. HARRISON" against "UNITED STATES OF AMERICA v.
    TYISHA SOMERVILLE" is a paper about somebody else in the same
    prosecution.

    Decided on shared identifying words rather than string equality, since
    the caption is almost always the fuller of the two.

    :param docket_name: The case name PACER gave the docket.
    :param caption: The caption centralia read off the page.
    :return: True when the two name the same party.
    """
    docket_words = _identifying_words(docket_name)
    caption_words = _identifying_words(caption)
    if not docket_words or not caption_words:
        return False
    return bool(docket_words & caption_words)


def map_opinion_type(centralia_type: str) -> tuple[str, bool]:
    """Map a centralia writing type to a CL opinion type.

    ``COMBINED`` is deliberately never returned. It means an import could
    not tell one writing from another, and centralia's whole purpose is to
    say how many a document holds and where each begins -- so a lone
    writing is the lead opinion, not a combined blob. An unrecognized type
    lands there too: a paper centralia cannot name is likelier to be the
    decision itself than a concurrence or dissent, both of which it names.

    :param centralia_type: The type field of the payload writing.
    :return: A 2-tuple of the CL opinion type and the per_curiam flag.
    """
    type_map = {
        "majority": (Opinion.LEAD, False),
        "per-curiam": (Opinion.LEAD, True),
        "concurrence": (Opinion.CONCURRENCE, False),
        "concurrence-in-result": (Opinion.CONCURRENCE, False),
        "concurring-in-part-and-dissenting-in-part": (
            Opinion.CONCUR_IN_PART,
            False,
        ),
        "dissent": (Opinion.DISSENT, False),
        "addendum": (Opinion.ADDENDUM, False),
        "rehearing": (Opinion.REHEARING, False),
    }
    key = (centralia_type or "").strip().lower()
    return type_map.get(key, (Opinion.LEAD, False))


def _wrap(html: str) -> str:
    """Scope a payload fragment under the class CL's stylesheet targets.

    :param html: Centralia markup for one writing.
    :return: The wrapped fragment, or "" when there is nothing to wrap.
    """
    html = (html or "").strip()
    if not html:
        return ""
    return f'<div class="centralia">{html}</div>'


def _payload_text_length(payload: dict) -> int:
    """Total plain text the structured read recovered.

    :param payload: Doctor's structured payload.
    :return: Combined length of the headmatter and every writing's text.
    """
    total = len((payload.get("headmatter") or {}).get("text") or "")
    for writing in payload.get("opinions") or []:
        total += len(writing.get("text") or "")
    return total


def should_install(opinion: Opinion, payload: dict) -> tuple[bool, str]:
    """Decide whether a structured read is good enough to store.

    Installing a bad read is worse than keeping the flat text, because the
    HTML it writes outranks ``plain_text`` for display, so this asks only
    whether the read itself is complete and trustworthy. What KIND of paper
    it is does not matter: centralia's ``doc_type`` is still approximate,
    and a filing can turn out to carry the court's writing.

    :param opinion: The opinion the payload was read from.
    :param payload: Doctor's structured payload.
    :return: A 2-tuple of whether to install and the reason, for logging.
    """
    status = payload.get("status") or ""
    if status != INSTALLABLE_STATUS:
        return False, f"status={status}, not a clean read"

    diagnostics = payload.get("diagnostics") or {}
    # Per-page facts that mean the same thing even when the overall status
    # came back valid: an image page, a page with no text layer, or a page
    # whose CID-encoded fonts extract as mojibake.
    for field, why in (
        ("scan_pages", "scanned pages"),
        ("text_missing_pages", "pages with no text layer"),
        ("cid_pages", "CID-encoded pages"),
    ):
        if pages := diagnostics.get(field):
            return False, f"{why} {list(pages)[:5]}, needs OCR"

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


def cluster_updates(payload: dict) -> dict:
    """Collect the OpinionCluster fields the payload can fill.

    Only fields centralia actually populated are returned, so a court that
    leaves a criterion empty never blanks existing CourtListener data.

    :param payload: Doctor's structured payload.
    :return: A mapping of field name to new value.
    """
    c = payload.get("cluster") or {}
    updates: dict = {}
    if filed := c.get("date_filed_iso"):
        updates["date_filed"] = date.fromisoformat(filed)
    # Prefer the parsed panel over the printed byline: the byline is a whole
    # sentence carrying the court's own typesetting (ca2 letter-spaces it),
    # where the parsed panel is just the names.
    if panel := c.get("panel"):
        updates["judges"] = ", ".join(panel)
    elif (judges := c.get("judges")) and len(judges) <= 300:
        # A byline centralia failed to detect can swallow the whole opinion
        # into this field, hence the length bound.
        updates["judges"] = judges
    for field in ("attorneys", "disposition", "history"):
        if value := c.get(field):
            updates[field] = value
    if short := c.get("case_name_short"):
        updates["case_name_short"] = short
    if status := PRECEDENTIAL_STATUS_MAP.get(
        (c.get("precedential_status") or "").strip().lower()
    ):
        updates["precedential_status"] = status
    # The cover page as centralia renders it for an ingest: every alignment,
    # indent and rule stated inline, so it needs no stylesheet of ours.
    if headmatter := ((payload.get("headmatter") or {}).get("html_inline")):
        updates["headmatter"] = headmatter
    # The payload's cluster entry is the merged view of the prose sections
    # and the cover rows that carry the same role, as plain text.
    for name in ("syllabus", "headnotes", "summary"):
        if text := (c.get(name) or "").strip():
            updates[name] = "\n".join(
                f"<p>{escape(line)}</p>"
                for line in text.split("\n")
                if line.strip()
            )
    return updates


def docket_updates(payload: dict) -> dict:
    """Collect the Docket fields the payload can fill.

    :param payload: Doctor's structured payload.
    :return: A mapping of field name to new value.
    """
    c = payload.get("cluster") or {}
    updates: dict = {}
    # docket_number is deliberately NOT written. The scraper reads it from
    # the court's own index, where it is already right, and a consolidated
    # record -- one PDF covering several petitions -- reports only its first
    # caption's number, which would relabel the docket as another case.
    #
    # That cover states every petition's origin too, merged into one value
    # with no way to tell which case each belongs to, so a consolidated
    # record contributes no lower court either.
    consolidated = bool(c.get("other_dockets"))
    if not consolidated and (lower_court := c.get("lower_court")):
        updates["appeal_from_str"] = lower_court
    if panel := c.get("panel"):
        updates["panel_str"] = ", ".join(panel)
    if argued := c.get("date_argued_iso"):
        updates["date_argued"] = date.fromisoformat(argued)
    return updates


def update_originating_court(docket: Docket, payload: dict) -> bool:
    """Record the lower court's own docket number and judge.

    The lower court's docket number and the judge who decided it belong on
    ``OriginatingCourtInformation``, not on the docket itself. Saves the
    OCI row; saving the docket is the caller's job.

    :param docket: The docket to attach the information to.
    :param payload: Doctor's structured payload.
    :return: Whether the docket's FK changed and needs saving.
    """
    c = payload.get("cluster") or {}
    # A consolidated record states every petition's origin on one cover, and
    # nothing in the payload says which lower-court number belongs to which
    # case. Attributing all of them to this docket would be wrong.
    if c.get("other_dockets"):
        return False
    judge = (c.get("lower_court_judge") or "").strip()
    dockets = [d for d in (c.get("lower_court_docket") or []) if d]
    dockets = dockets or [d for d in (c.get("other_dockets") or []) if d]
    if not judge and not dockets:
        return False

    oci = docket.originating_court_information
    if oci is None:
        oci = OriginatingCourtInformation()
    if dockets:
        oci.docket_number = "; ".join(dockets)
    if judge:
        oci.assigned_to_str = judge
    oci.save()
    if docket.originating_court_information_id != oci.pk:
        docket.originating_court_information = oci
        return True
    return False


@transaction.atomic
def install_structured_opinion(seed: Opinion, payload: dict) -> list[int]:
    """Map the payload onto the cluster, docket and one Opinion per writing.

    A court files several papers in one decision -- a majority plus its
    concurrences and dissents -- and each becomes its own ``Opinion``
    ordered within the cluster. ``seed`` (the row the scraper created)
    takes the first writing so its pk, download_url and inbound citations
    survive; prior non-seed writings are regenerated from the payload.

    ``xml_harvard`` is deliberately left alone: it outranks ``html`` in
    ``OPINION_TEXT_SOURCE_FIELDS``, so writing the casebody there would
    hide the formatted HTML behind flattened XML.

    Callers gate with ``should_install`` first; the payload must carry at
    least one writing.

    :param seed: The existing opinion, which becomes the first writing.
    :param payload: Doctor's structured payload.
    :return: Every affected opinion pk, the seed's first.
    """
    writings = payload.get("opinions") or []
    if not writings:
        return [seed.pk]

    cluster = seed.cluster
    if updates := cluster_updates(payload):
        for field, value in updates.items():
            setattr(cluster, field, value)
        cluster.save(update_fields=[*updates, "date_modified"])

    docket = cluster.docket
    dkt_updates = docket_updates(payload)
    for field, value in dkt_updates.items():
        setattr(docket, field, value)
    dkt_fields = list(dkt_updates)
    if update_originating_court(docket, payload):
        dkt_fields.append("originating_court_information")
    if dkt_fields:
        docket.save(update_fields=[*dkt_fields, "date_modified"])

    # Re-running must be safe, and (cluster, ordering_key) is unique. Every
    # non-seed writing is regenerated from the payload each run, so drop the
    # previous run's extras rather than trying to match them up.
    cluster.sub_opinions.exclude(pk=seed.pk).delete()
    seed.main_version = None

    created_pks = []
    for i, writing in enumerate(writings):
        html = _wrap(writing.get("html") or "")
        cl_type, per_curiam = map_opinion_type(writing.get("type") or "")
        author = (writing.get("author_name") or "").strip()
        ordering_key = writing.get("order") or i + 1
        if i == 0:
            seed.html = html
            seed.type = cl_type
            seed.per_curiam = per_curiam
            if author:
                seed.author_str = author
            # ordering_key drives OpinionCluster.ordered_opinions, which
            # drops null-keyed rows once a cluster holds several opinions.
            seed.ordering_key = ordering_key
            # A stale annotation outranks `html`; the citation task the
            # caller enqueues rebuilds it from the new markup.
            seed.html_with_citations = ""
            seed.save(
                update_fields=[
                    "html",
                    "type",
                    "per_curiam",
                    "author_str",
                    "ordering_key",
                    "html_with_citations",
                    "main_version",
                    "date_modified",
                ]
            )
            continue
        sibling = Opinion.objects.create(
            cluster=cluster,
            type=cl_type,
            per_curiam=per_curiam,
            author_str=author,
            html=html,
            ordering_key=ordering_key,
            download_url=seed.download_url,
            extracted_by_ocr=False,
        )
        created_pks.append(sibling.pk)
    return [seed.pk, *created_pks]
