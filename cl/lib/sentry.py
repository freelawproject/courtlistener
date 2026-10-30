"""Sentry helpers: classify events in `before_send` and tag scraper work

Errors from juriscraper, eyecite and CourtListener share one Sentry project.
`fingerprint_sentry_error` decides how each event groups and who owns it,
and `set_scraper_tags` records which court and which kind of work an event
came from.
"""

import logging
import socket
import urllib.error
from types import TracebackType
from typing import Any
from urllib.parse import urlparse

import httpx
import sentry_sdk

logger = logging.getLogger(__name__)

# Owner by the module prefix of the frame that raised
OWNER_BY_PREFIX = (
    ("juriscraper.", "juriscraper"),
    ("eyecite.", "eyecite"),
    ("cl.", "courtlistener"),
)
CLASSIFIED_PREFIXES = tuple(prefix for prefix, _ in OWNER_BY_PREFIX)
SCRAPER_PREFIXES = ("juriscraper.", "eyecite.")

# EAI_AGAIN and ENETUNREACH: the cluster could not resolve or route, which
# is an infrastructure problem, not a scraper one
TRANSIENT_NETWORK_ERRNOS = {-3, 101}
# EAI_NONAME and EAI_NODATA: the name does not exist, so the court moved
MISSING_NAME_ERRNOS = {-2, -5}


def set_scraper_tags(
    court_id: str | None, kind: str, owner: str = "juriscraper"
) -> None:
    """Tag every event captured in the current isolation scope

    Celery opens one isolation scope per task and the scrape commands fork
    one per court, so the tags stay with that unit of work. Call it as soon
    as the court is known.

    :param court_id: the CourtListener court pk, if known
    :param kind: what the code is doing: "opinions", "oral_args",
        "backscrape", "extract-from-text", "email", "pacer", "state-docket"
    :param owner: default owner for events that `fingerprint_sentry_error`
        does not classify on its own
    """
    scope = sentry_sdk.get_isolation_scope()
    scope.set_tag("scrape_kind", kind)
    scope.set_tag("owner", owner)
    if court_id:
        scope.set_tag("court_id", court_id)


def fingerprint_sentry_error(
    event: dict[str, Any], hint: dict[str, Any]
) -> dict[str, Any]:
    """`before_send` hook: set the fingerprint and owner of each event

    A `fingerprint` key in a log call's `extra` always wins, for example
    `logger.error(..., extra={"fingerprint": [court_id, "citation-not-found"]})`.

    Exceptions that passed through juriscraper or eyecite, or that happened
    inside tagged scraper work, are grouped by cause instead of by stack:
    one issue per host and status for HTTP errors, one per host for DNS and
    transport errors (only when juriscraper made the request, so a timeout
    from an internal service is not blamed on a court), the fingerprint the
    exception carries when juriscraper set one, and otherwise the raising
    module, exception type and function, so a deploy that edits a line no
    longer opens a new issue. Only explicit causes (`raise ... from`) are
    followed, so a bug inside an except block is not filed under the error
    it was handling.

    A fingerprint already on the event, for example the one the Celery
    integration sets for soft time limits, is left alone.

    Logged events from juriscraper without a fingerprint are grouped by
    scraper and message instead of by the attached stack.

    Any failure inside the hook returns the event unchanged; the hook must
    never drop an event.

    :param event: event dict to be sent to Sentry
    :param hint: dict with extra information about the event
    :return: the event, with explicit fingerprint and tags where known
    """
    try:
        return _classify(event, hint)
    except Exception:
        # WARNING, not ERROR: an error log here would become another event
        # that runs this hook again
        logger.warning("Sentry event classification failed", exc_info=True)
        return event


def _classify(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    tags = event.get("tags")
    if not isinstance(tags, dict):
        tags = {}
    _set_owner_from_logger(event, tags)

    if fingerprint := event.get("extra", {}).pop("fingerprint", []):
        event["fingerprint"] = fingerprint
        return event
    if event.get("fingerprint"):
        return event

    exc_info = hint.get("exc_info")
    if not exc_info:
        return _classify_log_event(event, tags)

    chain = _exception_chain(exc_info[1])
    touches_scraper = any(_touches_scraper(exc.__traceback__) for exc in chain)
    if "scrape_kind" not in tags and not touches_scraper:
        return event

    fingerprint, owner, extra_tags = _classify_exception(
        chain, tags, touches_scraper
    )
    event["fingerprint"] = fingerprint
    tags["owner"] = owner
    tags.update(extra_tags)
    event["tags"] = tags
    return event


def _set_owner_from_logger(
    event: dict[str, Any], tags: dict[str, Any]
) -> None:
    """Inside tagged scraper work, a CourtListener log call is CourtListener's

    The scope default is "juriscraper", which is right for exceptions that
    the rules below do not classify, but wrong for `logger.error` calls in
    CourtListener code such as the document-extract failure.
    """
    if "scrape_kind" not in tags:
        return
    if str(event.get("logger", "")).startswith("cl."):
        tags["owner"] = "courtlistener"
        event["tags"] = tags


def _classify_log_event(
    event: dict[str, Any], tags: dict[str, Any]
) -> dict[str, Any]:
    """Group juriscraper log messages by scraper and message template"""
    if not str(event.get("logger", "")).startswith("juriscraper"):
        return event
    message = event.get("logentry", {}).get("message") or event.get(
        "message", ""
    )
    event["fingerprint"] = [
        "juriscraper-log",
        str(tags.get("scraper", "")),
        str(message),
    ]
    tags.setdefault("owner", "juriscraper")
    event["tags"] = tags
    return event


def _exception_chain(exc: BaseException) -> list[BaseException]:
    """The exception and its explicit causes, outermost first

    Only `raise ... from` links are followed. The implicit context of an
    exception raised inside an except block is the error that was being
    handled, not the cause of the new one.
    """
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__
    return chain


def _frames(tb: TracebackType | None) -> list[tuple[str, str]]:
    """(module, function) for each frame, outermost first"""
    frames = []
    while tb is not None:
        frame = tb.tb_frame
        frames.append(
            (str(frame.f_globals.get("__name__", "")), frame.f_code.co_name)
        )
        tb = tb.tb_next
    return frames


def _touches_scraper(tb: TracebackType | None) -> bool:
    return any(
        module.startswith(SCRAPER_PREFIXES) for module, _ in _frames(tb)
    )


def _raising_frame(tb: TracebackType | None) -> tuple[str, str]:
    """The innermost frame in our code, so lxml or dateutil frames called
    from a scraper are attributed to the scraper"""
    frames = _frames(tb)
    for module, function in reversed(frames):
        if module.startswith(CLASSIFIED_PREFIXES):
            return module, function
    if frames:
        return frames[-1]
    return "unknown", "unknown"


def _host_from_chain(chain: list[BaseException], tags: dict[str, Any]) -> str:
    """Host of the request that failed, from the exceptions or the tags"""
    for exc in chain:
        if isinstance(exc, httpx.RequestError):
            try:
                return exc.request.url.host
            except RuntimeError:
                # the request was never attached to the exception
                pass
        if url := getattr(exc, "url", None):
            if host := urlparse(str(url)).hostname:
                return host
    if url := tags.get("url"):
        if host := urlparse(str(url)).hostname:
            return host
    return "unknown"


def _classify_exception(
    chain: list[BaseException], tags: dict[str, Any], touches_scraper: bool
) -> tuple[list[str], str, dict[str, str]]:
    """Fingerprint, owner and extra tags for an exception chain

    Rules apply in order to the whole chain, innermost cause first, so a
    CourtListener wrapper raised from an HTTP error is still grouped by host
    and status. The HTTP, DNS and transport rules only apply when juriscraper
    made the request; a request to an internal service that fails inside
    tagged work falls through to the raising-frame rule.
    """
    causes = list(reversed(chain))
    network_causes = causes if touches_scraper else []

    for exc in network_causes:
        if isinstance(exc, httpx.HTTPStatusError):
            host = exc.request.url.host
            status = str(exc.response.status_code)
            return (
                ["scraper-http", host, status],
                "court-site",
                {"host": host, "http_status": status},
            )
        if isinstance(exc, urllib.error.HTTPError):
            host = urlparse(exc.url).hostname or "unknown"
            status = str(exc.code)
            return (
                ["scraper-http", host, status],
                "court-site",
                {"host": host, "http_status": status},
            )

    for exc in network_causes:
        if not isinstance(exc, OSError) or exc.errno is None:
            continue
        if exc.errno in TRANSIENT_NETWORK_ERRNOS:
            return ["cluster-network", str(exc.errno)], "infra", {}
        if (
            isinstance(exc, socket.gaierror)
            and exc.errno in MISSING_NAME_ERRNOS
        ):
            host = _host_from_chain(chain, tags)
            return ["scraper-dns", host], "court-site", {"host": host}

    for exc in network_causes:
        if isinstance(exc, httpx.TransportError | urllib.error.URLError):
            host = _host_from_chain(chain, tags)
            return (
                ["scraper-network", type(exc).__name__, host],
                "court-site",
                {"host": host},
            )

    for exc in causes:
        if fingerprint := getattr(exc, "sentry_fingerprint", None):
            owner = getattr(exc, "sentry_owner", None) or "juriscraper"
            return [str(part) for part in fingerprint], owner, {}
        # juriscraper releases before `sentry_fingerprint` existed log this
        # error themselves with this fingerprint; match it so the exception
        # and the log land in the same issue
        if type(exc).__name__ == "UnexpectedContentTypeError" and tags.get(
            "court_id"
        ):
            return (
                [f"{tags['court_id']}-unexpected-content-type"],
                "juriscraper",
                {},
            )

    root = causes[0]
    module, function = _raising_frame(root.__traceback__)
    owner = next(
        (
            owner
            for prefix, owner in OWNER_BY_PREFIX
            if module.startswith(prefix)
        ),
        "courtlistener",
    )
    return [module, type(root).__name__, function], owner, {}
