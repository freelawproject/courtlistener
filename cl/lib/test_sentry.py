import socket
from collections.abc import Callable
from typing import Any
from unittest import mock

import httpx
import sentry_sdk
from asgiref.sync import async_to_sync
from juriscraper.lib.exceptions import UnexpectedContentTypeError
from juriscraper.lib.utils import (
    check_download_url,
    check_empty_downloaded_file,
)

from cl.lib.sentry import fingerprint_sentry_error, set_scraper_tags
from cl.tests.cases import SimpleTestCase

URL = "https://www.courts.example.gov/opinions?page=2"


def classify(
    raiser: Callable[[], Any], tags: dict[str, str] | None = None
) -> dict[str, Any]:
    """Run `raiser`, catch what it raises and classify it like the SDK would"""
    try:
        raiser()
    except Exception as exc:
        exc_info = (type(exc), exc, exc.__traceback__)
    else:
        raise AssertionError("raiser did not raise")
    event = {"tags": dict(tags or {}), "extra": {}}
    return fingerprint_sentry_error(event, {"exc_info": exc_info})


def raise_http_status(status: int) -> None:
    request = httpx.Request("GET", URL)
    response = httpx.Response(status, request=request)
    raise httpx.HTTPStatusError("bad", request=request, response=response)


class _RaisingResponse:
    """A response whose body raises, so the error happens inside juriscraper"""

    def __init__(self, raiser: Callable[[], Any]) -> None:
        self._raiser = raiser

    @property
    def content(self) -> bytes:
        self._raiser()
        return b""


def in_juriscraper(raiser: Callable[[], Any]) -> Callable[[], Any]:
    """Make `raiser` fail with a juriscraper frame on the stack, the way a
    real request made by a scraper does"""
    return lambda: check_empty_downloaded_file(_RaisingResponse(raiser), URL)


def raise_key_error() -> None:
    raise KeyError("case_names")


class SentryClassifierTest(SimpleTestCase):
    """fingerprint_sentry_error groups scraper errors by cause"""

    def test_log_fingerprint_wins(self) -> None:
        """A fingerprint passed in a log call's extra is used as is"""
        event = {"extra": {"fingerprint": ["ky", "citation-not-found"]}}
        result = fingerprint_sentry_error(event, {})
        self.assertEqual(result["fingerprint"], ["ky", "citation-not-found"])
        self.assertNotIn("fingerprint", result["extra"])

    def test_http_status_error_groups_by_host_and_status(self) -> None:
        event = classify(
            in_juriscraper(lambda: raise_http_status(502)),
            {"scrape_kind": "opinions"},
        )
        self.assertEqual(
            event["fingerprint"],
            ["scraper-http", "www.courts.example.gov", "502"],
        )
        self.assertEqual(event["tags"]["owner"], "court-site")
        self.assertEqual(event["tags"]["host"], "www.courts.example.gov")
        self.assertEqual(event["tags"]["http_status"], "502")

    def test_wrapped_http_error_uses_the_cause(self) -> None:
        """A CourtListener wrapper raised from an HTTP error keeps the
        host and status grouping"""

        def wrap() -> None:
            try:
                in_juriscraper(lambda: raise_http_status(403))()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError("Blocked by court") from exc

        event = classify(wrap, {"scrape_kind": "pacer"})
        self.assertEqual(
            event["fingerprint"],
            ["scraper-http", "www.courts.example.gov", "403"],
        )

    def test_dns_errors(self) -> None:
        """Temporary resolution failures belong to the cluster; a missing
        name belongs to the court website"""

        def raise_gaierror(errno: int) -> None:
            exc = socket.gaierror(errno, "Name or service not known")
            raise httpx.ConnectError(
                "fail", request=httpx.Request("GET", URL)
            ) from exc

        event = classify(
            in_juriscraper(lambda: raise_gaierror(-3)), {"scrape_kind": "x"}
        )
        self.assertEqual(event["fingerprint"], ["cluster-network", "-3"])
        self.assertEqual(event["tags"]["owner"], "infra")

        event = classify(
            in_juriscraper(lambda: raise_gaierror(-2)), {"scrape_kind": "x"}
        )
        self.assertEqual(
            event["fingerprint"], ["scraper-dns", "www.courts.example.gov"]
        )
        self.assertEqual(event["tags"]["owner"], "court-site")

    def test_transport_error_groups_by_type_and_host(self) -> None:
        def raise_timeout() -> None:
            raise httpx.ReadTimeout("slow", request=httpx.Request("GET", URL))

        event = classify(
            in_juriscraper(raise_timeout), {"scrape_kind": "opinions"}
        )
        self.assertEqual(
            event["fingerprint"],
            ["scraper-network", "ReadTimeout", "www.courts.example.gov"],
        )
        self.assertEqual(event["tags"]["owner"], "court-site")

    def test_internal_service_errors_are_not_blamed_on_the_court(self) -> None:
        """A doctor timeout inside a tagged task has no juriscraper frame"""

        def raise_timeout() -> None:
            raise httpx.ReadTimeout(
                "slow", request=httpx.Request("GET", "http://cl-doctor:5050")
            )

        event = classify(raise_timeout, {"scrape_kind": "extract-from-text"})
        self.assertEqual(
            event["fingerprint"],
            ["cl.lib.test_sentry", "ReadTimeout", "raise_timeout"],
        )
        self.assertEqual(event["tags"]["owner"], "courtlistener")

    def test_bug_inside_except_block_is_not_grouped_by_the_handled_error(
        self,
    ) -> None:
        def buggy_handler() -> None:
            try:
                in_juriscraper(lambda: raise_http_status(404))()
            except httpx.HTTPStatusError:
                raise KeyError("case_names")

        event = classify(buggy_handler, {"scrape_kind": "opinions"})
        self.assertEqual(
            event["fingerprint"],
            ["cl.lib.test_sentry", "KeyError", "buggy_handler"],
        )
        self.assertEqual(event["tags"]["owner"], "courtlistener")

    def test_existing_fingerprint_is_kept(self) -> None:
        """The Celery integration fingerprints soft time limits itself"""
        event = {
            "fingerprint": ["celery", "SoftTimeLimitExceeded", "task"],
            "tags": {"scrape_kind": "pacer"},
            "extra": {},
        }
        result = fingerprint_sentry_error(event, {"exc_info": None})
        self.assertEqual(
            result["fingerprint"], ["celery", "SoftTimeLimitExceeded", "task"]
        )

    def test_courtlistener_log_in_tagged_work_is_owned_by_courtlistener(
        self,
    ) -> None:
        event = {
            "logger": "cl.scrapers.tasks",
            "logentry": {"message": "Error from document-extract: %s"},
            "tags": {
                "scrape_kind": "extract-from-text",
                "owner": "juriscraper",
            },
            "extra": {"fingerprint": ["ky-document-extract-failure"]},
        }
        result = fingerprint_sentry_error(event, {})
        self.assertEqual(result["tags"]["owner"], "courtlistener")
        self.assertEqual(
            result["fingerprint"], ["ky-document-extract-failure"]
        )

    def test_exception_fingerprint_attribute(self) -> None:
        """juriscraper sets sentry_fingerprint on the exception"""

        class TaggedError(ValueError):
            sentry_fingerprint = ["www.courts.example.gov", "bot-challenge"]
            sentry_owner = "court-site"

        def raise_tagged() -> None:
            raise TaggedError("blocked")

        event = classify(raise_tagged, {"scrape_kind": "opinions"})
        self.assertEqual(
            event["fingerprint"], ["www.courts.example.gov", "bot-challenge"]
        )
        self.assertEqual(event["tags"]["owner"], "court-site")

    def test_unexpected_content_type_matches_juriscraper_log(self) -> None:
        """The exception and juriscraper's own log of it share one issue"""

        def raise_content_type() -> None:
            raise UnexpectedContentTypeError("'u' 'text/html' not in [pdf]")

        event = classify(
            raise_content_type, {"scrape_kind": "opinions", "court_id": "ky"}
        )
        self.assertEqual(event["fingerprint"], ["ky-unexpected-content-type"])
        self.assertEqual(event["tags"]["owner"], "juriscraper")

    def test_other_errors_group_by_raising_frame(self) -> None:
        """No source line in the hash, so a deploy does not split the issue"""
        event = classify(lambda: check_download_url(""))
        self.assertEqual(
            event["fingerprint"],
            [
                "juriscraper.lib.utils",
                "NoDownloadUrlError",
                "check_download_url",
            ],
        )
        self.assertEqual(event["tags"]["owner"], "juriscraper")

    def test_courtlistener_error_in_scraper_work(self) -> None:
        """A CourtListener bug hit while scraping is owned by CourtListener"""
        event = classify(raise_key_error, {"scrape_kind": "opinions"})
        self.assertEqual(
            event["fingerprint"],
            ["cl.lib.test_sentry", "KeyError", "raise_key_error"],
        )
        self.assertEqual(event["tags"]["owner"], "courtlistener")

    def test_unrelated_errors_are_left_alone(self) -> None:
        event = classify(raise_key_error)
        self.assertNotIn("fingerprint", event)
        self.assertNotIn("owner", event["tags"])

    def test_juriscraper_log_events_group_by_message(self) -> None:
        event = {
            "logger": "juriscraper.lib.log_tools",
            "logentry": {"message": "%s: Returned with zero items"},
            "tags": {"scraper": "opinions.united_states.state.ky"},
            "extra": {},
        }
        result = fingerprint_sentry_error(event, {})
        self.assertEqual(
            result["fingerprint"],
            [
                "juriscraper-log",
                "opinions.united_states.state.ky",
                "%s: Returned with zero items",
            ],
        )
        self.assertEqual(result["tags"]["owner"], "juriscraper")

    def test_classifier_failure_returns_the_event(self) -> None:
        """A bug in the hook must never drop an event"""
        event = {"extra": {}, "tags": {}}
        # The test runner disables logging, so check the logger call directly
        with (
            mock.patch("cl.lib.sentry._classify", side_effect=RuntimeError),
            mock.patch("cl.lib.sentry.logger") as logger_mock,
        ):
            result = fingerprint_sentry_error(event, {})
        self.assertIs(result, event)
        logger_mock.warning.assert_called_once()


class ScraperTagsTest(SimpleTestCase):
    def test_tags_reach_code_run_through_async_to_sync(self) -> None:
        """The scrape command sets tags, then runs the coroutine in a
        worker thread; the tags must follow it there"""

        async def read_tags() -> dict[str, str]:
            return dict(sentry_sdk.get_isolation_scope()._tags)

        # Other tests may have tagged the process-wide scope already; the
        # forked scope must not change it
        before = dict(sentry_sdk.get_isolation_scope()._tags)
        with sentry_sdk.isolation_scope():
            set_scraper_tags("ky", "opinions")
            tags = async_to_sync(read_tags)()

        self.assertEqual(tags["court_id"], "ky")
        self.assertEqual(tags["scrape_kind"], "opinions")
        self.assertEqual(tags["owner"], "juriscraper")
        self.assertEqual(dict(sentry_sdk.get_isolation_scope()._tags), before)
