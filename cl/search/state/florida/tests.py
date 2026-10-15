import base64
import json
from unittest import mock
from urllib.parse import parse_qs, urlparse

import httpx
import requests
from juriscraper.state.florida.scraper import FLORIDA_API_BASE

from cl.search.state.florida.factories import FloridaDocumentFactory
from cl.search.state.florida.models import (
    AltchaChallenge,
    AltchaChallengeResponse,
    AltchaChallengeSolution,
    FloridaDocument,
)
from cl.tests.cases import SimpleTestCase, TestCase

# A real challenge issued by Florida ACIS and the solution the browser
# submitted for it, both taken from the token in the issue that introduced the
# gate. Keys are in the order the server serializes them.
CHALLENGE_RESOURCE = "/courts/68f021c4-6a44-4735-9a76-5360b2e8af13/cms/case/4b5eafaf-a6c7-4556-9a60-cf173c204883/docketentrydocuments/7b6b41bf-3eb6-4704-8f9b-093367be9d69"
CHALLENGE_JSON = {
    "parameters": {
        "algorithm": "PBKDF2/SHA-256",
        "cost": 10000,
        "data": {"resource": CHALLENGE_RESOURCE},
        "expiresAt": 1789424228,
        "keyLength": 32,
        "keyPrefix": "d003cf8e29159842a4dd2abb90a6d68a",
        "keySignature": "1912061753893c495c19080c40d90eb9029919d47b17b8c6cfb97d1af86a997a",
        "nonce": "ee760148b810f7fd855b75fb728bc54b",
        "salt": "8a4d1d31f3e89688791f46e1941a6cd7",
    },
    "signature": "bfe8968a0b09e59072225361880098d663323e1245ce129f55e44a4a8f372aec",
}
SOLUTION_JSON = {
    "counter": 229,
    "derivedKey": "d003cf8e29159842a4dd2abb90a6d68ad21e5bbb1b09ede19320c43a152d0c87",
    "time": 243.6,
}
BROWSER_TOKEN = "eyJjaGFsbGVuZ2UiOnsicGFyYW1ldGVycyI6eyJhbGdvcml0aG0iOiJQQktERjIvU0hBLTI1NiIsImNvc3QiOjEwMDAwLCJkYXRhIjp7InJlc291cmNlIjoiL2NvdXJ0cy82OGYwMjFjNC02YTQ0LTQ3MzUtOWE3Ni01MzYwYjJlOGFmMTMvY21zL2Nhc2UvNGI1ZWFmYWYtYTZjNy00NTU2LTlhNjAtY2YxNzNjMjA0ODgzL2RvY2tldGVudHJ5ZG9jdW1lbnRzLzdiNmI0MWJmLTNlYjYtNDcwNC04ZjliLTA5MzM2N2JlOWQ2OSJ9LCJleHBpcmVzQXQiOjE3ODk0MjQyMjgsImtleUxlbmd0aCI6MzIsImtleVByZWZpeCI6ImQwMDNjZjhlMjkxNTk4NDJhNGRkMmFiYjkwYTZkNjhhIiwia2V5U2lnbmF0dXJlIjoiMTkxMjA2MTc1Mzg5M2M0OTVjMTkwODBjNDBkOTBlYjkwMjk5MTlkNDdiMTdiOGM2Y2ZiOTdkMWFmODZhOTk3YSIsIm5vbmNlIjoiZWU3NjAxNDhiODEwZjdmZDg1NWI3NWZiNzI4YmM1NGIiLCJzYWx0IjoiOGE0ZDFkMzFmM2U4OTY4ODc5MWY0NmUxOTQxYTZjZDcifSwic2lnbmF0dXJlIjoiYmZlODk2OGEwYjA5ZTU5MDcyMjI1MzYxODgwMDk4ZDY2MzMyM2UxMjQ1Y2UxMjlmNTVlNDRhNGE4ZjM3MmFlYyJ9LCJzb2x1dGlvbiI6eyJjb3VudGVyIjoyMjksImRlcml2ZWRLZXkiOiJkMDAzY2Y4ZTI5MTU5ODQyYTRkZDJhYmI5MGE2ZDY4YWQyMWU1YmJiMWIwOWVkZTE5MzIwYzQzYTE1MmQwYzg3IiwidGltZSI6MjQzLjZ9fQ=="

CHALLENGE_URL = f"{FLORIDA_API_BASE}/altcha/challenge"
REFUSED_URL = "https://acis-api.test/refused"


def challenge_response(status: int, **kwargs) -> httpx.Response:
    """Build an `httpx.Response` for the challenge endpoint that supports
    `raise_for_status`, which needs the request attached."""
    return httpx.Response(
        status, request=httpx.Request("GET", CHALLENGE_URL), **kwargs
    )


class AltchaTokenTest(SimpleTestCase):
    """Solving and encoding an ACIS proof-of-work challenge."""

    def setUp(self) -> None:
        self.challenge = AltchaChallenge.model_validate(CHALLENGE_JSON)

    def test_solve_reproduces_browser_solution(self) -> None:
        """Does the solver land on the counter and key the browser found?"""
        solution = self.challenge.solve()

        self.assertIsNotNone(solution)
        self.assertEqual(solution.counter, SOLUTION_JSON["counter"])
        self.assertEqual(solution.derived_key, SOLUTION_JSON["derivedKey"])

    def test_encode_matches_browser_token(self) -> None:
        """Is the token byte-for-byte what the ACIS frontend submits?

        The server's signature covers the challenge parameters, so the
        encoding has to preserve the server's key names and key order."""
        solution = AltchaChallengeSolution.model_validate(SOLUTION_JSON)

        token = AltchaChallengeResponse(
            challenge=self.challenge, solution=solution
        ).encode()

        self.assertEqual(token, BROWSER_TOKEN)


class DocumentDownloadTest(TestCase):
    """`FloridaDocument.download` against the ACIS gate, with only the network
    and microservices mocked."""

    def setUp(self) -> None:
        self.document = FloridaDocumentFactory.create(
            url=f"{FLORIDA_API_BASE}{CHALLENGE_RESOURCE}"
        )

        self.pdf_response = mock.Mock()
        self.pdf_response.headers = {"content-type": "application/pdf"}
        self.pdf_response.iter_content.return_value = [b"%PDF-1.4 fake"]
        self.pdf_response.raise_for_status.return_value = None
        self.document_get = self.enterContext(
            mock.patch("cl.corpus_importer.tasks.requests.get")
        )
        self.document_get.return_value.__enter__.return_value = (
            self.pdf_response
        )

        self.challenge_get = self.enterContext(
            mock.patch("cl.search.state.florida.models.httpx.get")
        )
        self.enterContext(
            mock.patch("cl.scrapers.utils.get_extension", return_value=".pdf")
        )
        self.enterContext(
            mock.patch("cl.scrapers.tasks.extract_formatted_text_document.si")
        )
        # Downloads log from both modules; one mock stands in for both loggers.
        self.logger = mock.Mock()
        for module in (
            "cl.search.state.shared",
            "cl.search.state.florida.models",
        ):
            self.enterContext(mock.patch(f"{module}.logger", self.logger))

    def fetched_url(self):
        """The URL the document body was requested from, parsed."""
        self.document_get.assert_called_once()
        return urlparse(self.document_get.call_args.args[0])

    def test_download_appends_solved_token(self) -> None:
        """Does a download request the challenge for the document's path,
        solve it, and fetch the document with the encoded token appended?"""
        self.challenge_get.return_value = challenge_response(
            200, json=CHALLENGE_JSON
        )

        result = FloridaDocument.download(self.document.pk)

        self.assertEqual(result, self.document)
        self.challenge_get.assert_called_once_with(
            CHALLENGE_URL,
            params={"resource": CHALLENGE_RESOURCE},
            headers=mock.ANY,
            timeout=mock.ANY,
        )

        fetched = self.fetched_url()
        self.assertEqual(
            fetched._replace(query="").geturl(), self.document.url
        )
        query = parse_qs(fetched.query)
        self.assertEqual(list(query), ["altcha"])

        token = json.loads(base64.b64decode(query["altcha"][0]))
        self.assertEqual(token["challenge"], CHALLENGE_JSON)
        self.assertEqual(
            token["solution"]["counter"], SOLUTION_JSON["counter"]
        )
        self.assertEqual(
            token["solution"]["derivedKey"], SOLUTION_JSON["derivedKey"]
        )

    def test_download_logs_token_failures_and_skips(self) -> None:
        """When retrieving or solving the challenge raises, is the error
        logged and the document skipped rather than the task failing?"""
        failures = {
            "challenge endpoint error": challenge_response(500),
            "malformed challenge": challenge_response(200, json={"bad": 1}),
        }
        for name, response in failures.items():
            with self.subTest(name):
                self.challenge_get.return_value = response
                self.document_get.reset_mock()
                self.logger.reset_mock()

                result = FloridaDocument.download(self.document.pk)

                self.assertIsNone(result)
                self.document_get.assert_not_called()
                self.logger.exception.assert_called_once()
                self.assertIn(
                    self.document.pk, self.logger.exception.call_args.args
                )

    def test_download_logs_refusals_distinctly(self) -> None:
        """Does a 403 from either the challenge endpoint or the document
        fetch go to the dedicated refusal logger, and nowhere else?"""
        ok_challenge = challenge_response(200, json=CHALLENGE_JSON)
        refused_document = mock.Mock(status_code=403)
        refused_document.request.url = REFUSED_URL
        refused = requests.HTTPError(response=refused_document)
        cases = {
            "challenge endpoint": (
                challenge_response(403),
                None,
                CHALLENGE_URL,
            ),
            "document fetch": (ok_challenge, refused, REFUSED_URL),
        }
        for name, (challenge, fetch_error, refused_url) in cases.items():
            with self.subTest(name):
                self.challenge_get.return_value = challenge
                self.pdf_response.raise_for_status.side_effect = fetch_error
                self.logger.reset_mock()

                result = FloridaDocument.download(self.document.pk)

                self.assertIsNone(result)
                self.logger.error.assert_called_once()
                *_, logged_pk, logged_url = self.logger.error.call_args.args
                self.assertEqual(logged_pk, self.document.pk)
                # The endpoint that refused us, not the document's stored URL:
                # a block on the shared challenge endpoint must be
                # distinguishable from a block on one document.
                self.assertTrue(
                    str(logged_url).startswith(refused_url),
                    f"{logged_url!r} does not start with {refused_url!r}",
                )
                self.logger.exception.assert_not_called()
                self.document.refresh_from_db()
                self.assertFalse(self.document.filepath_local)

    def test_download_retries_transient_challenge_failures(self) -> None:
        """Is a dropped connection to the challenge endpoint retried rather
        than costing us the document?"""
        self.challenge_get.side_effect = [
            httpx.ConnectTimeout("slow gate"),
            challenge_response(200, json=CHALLENGE_JSON),
        ]

        result = FloridaDocument.download(self.document.pk)

        self.assertEqual(result, self.document)
        self.assertEqual(self.challenge_get.call_count, 2)

    def test_download_logs_other_fetch_errors_generically(self) -> None:
        """Is a non-403 HTTP error on the document fetch logged as an ordinary
        failure and the document skipped?"""
        self.challenge_get.return_value = challenge_response(
            200, json=CHALLENGE_JSON
        )
        self.pdf_response.raise_for_status.side_effect = requests.HTTPError(
            response=mock.Mock(status_code=500)
        )

        result = FloridaDocument.download(self.document.pk)

        self.assertIsNone(result)
        self.logger.exception.assert_called_once()
        self.assertIn(self.document.pk, self.logger.exception.call_args.args)
        self.logger.error.assert_not_called()

    def test_download_without_gate_uses_bare_url(self) -> None:
        """When the challenge endpoint reports the gate is off (204), is the
        stored URL fetched unchanged?"""
        self.challenge_get.return_value = challenge_response(204)

        result = FloridaDocument.download(self.document.pk)

        self.assertEqual(result, self.document)
        self.assertEqual(self.fetched_url().geturl(), self.document.url)
