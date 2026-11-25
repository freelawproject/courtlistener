import json
import re
from collections.abc import Iterator
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.template.loader import TemplateDoesNotExist, get_template
from django.test import override_settings
from django.urls import resolve, reverse
from django.utils.safestring import mark_safe
from lxml.html import HtmlElement, fromstring
from waffle.testutils import override_flag

from cl.custom_filters.templatetags.svg_tags import svg
from cl.lib.middleware import WIP_PROPS
from cl.lib.test_helpers import SimpleUserDataMixin
from cl.lib.types import TabItem
from cl.people_db.factories import PartyFactory, PartyTypeFactory
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import Docket
from cl.simple_pages.forms import ContactForm
from cl.simple_pages.sitemap import SimpleSitemap
from cl.tests.cases import CottonComponentMixin, SimpleTestCase, TestCase
from cl.tests.utils import parse_csp

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse


class ChangePasswordWellKnownTests(SimpleTestCase):
    """Ensure password managers can discover the password-change page."""

    def test_change_password(self) -> None:
        """The standard URL temporarily redirects to a real password page."""
        response = self.client.get(reverse("well_known_change_password"))

        self.assertRedirects(
            response,
            reverse("password_change"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            resolve(response["Location"]).url_name, "password_change"
        )


# Mock the hcaptcha thing so that we're sure it validates during tests
@patch("cl.simple_pages.views.create_zoho_desk_ticket")
@patch("hcaptcha.fields.hCaptchaField.validate", return_value=True)
class ContactTest(SimpleUserDataMixin, TestCase):
    test_msg = {
        "name": "pandora",
        "phone_number": "asdf",
        "issue_type": "support",
        "message": "123456789012345678901",
        "email": "pandora@box.com",
        "hcaptcha": "xxx",
        "checked_documentation": True,
    }

    async def test_multiple_requests_request(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Is state persisted in the contact form?

        The contact form is abstracted in a way that it can have peculiar
        behavior when called multiple times. This test makes sure that that
        behavior does not regress.
        """
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )
        await self.async_client.get(reverse("contact"))
        await self.async_client.alogout()

        # Now, as an anonymous user, we get the page again. If the bug is
        # resolved, we should not see anything about the previously logged-in
        # user, pandora.
        r = await self.async_client.get(reverse("contact"))
        self.assertNotIn("pandora", r.content.decode())

    async def test_contact_logged_in(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Can a logged-in user submit the form (without typing an email)?

        The form must not accept an email from a logged-in user — the
        account email is used directly. The resulting ticket also
        surfaces the user's account status so support staff don't need
        to verify it again.
        """
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )
        msg = self.test_msg.copy()
        msg.pop("email")
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        pandora_email = await User.objects.values_list(
            "email", flat=True
        ).aget(username="pandora")
        self.assertEqual(kwargs["email"], pandora_email)
        description = kwargs["description"]
        self.assertIn("Logged In As: pandora", description)
        self.assertIn("Email Confirmed: Yes", description)
        self.assertNotIn("User Email:", description)

    async def test_logged_in_user_email_field_is_ignored(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """An email submitted by a logged-in user must not reach Zoho.

        A malicious or confused logged-in user might POST a fake email
        (the field exists on the form even though the template hides
        it). Support staff rely on Zoho's email coming from the
        authenticated account, so the submitted value must be ignored
        in favor of the account email.
        """
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )
        msg = self.test_msg.copy()
        msg["email"] = "malevolent@evil.com"
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        mock_task.delay.assert_called_once()
        kwargs = mock_task.delay.call_args.kwargs
        pandora_email = await User.objects.values_list(
            "email", flat=True
        ).aget(username="pandora")
        self.assertEqual(kwargs["email"], pandora_email)
        self.assertNotIn("malevolent@evil.com", kwargs["description"])

    async def test_contact_logged_out(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Can we use the contact form to send a message when logged out?

        Anonymous submissions must not include any "Logged In As" line.
        """
        response = await self.async_client.post(
            reverse("contact"), self.test_msg
        )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        mock_task.delay.assert_called_once()
        description = mock_task.delay.call_args.kwargs["description"]
        self.assertNotIn("Logged In As", description)
        self.assertNotIn("Email Confirmed", description)

    async def test_logged_out_user_must_provide_email(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Anonymous submissions without an email are rejected."""
        msg = self.test_msg.copy()
        msg.pop("email")
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        mock_task.delay.assert_not_called()

    async def test_contact_unicode(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Can unicode be used when contacting us?"""
        msg = self.test_msg.copy()
        msg["message"] = (
            "Possible ideas and thoughts are vast in number. A distinct word "
            "for every distinct idea and thought would require a vast "
            "vocabulary. The problem in language is to express many ideas and "
            "thoughts with comparatively few words. — John Wesley Powell"
        )
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        mock_task.delay.assert_called_once()

    async def test_message_newlines_become_br(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Multi-line user input renders as <br> in the Zoho description."""
        msg = self.test_msg.copy()
        msg["message"] = "Line one\nLine two\nLine three"
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        description = mock_task.delay.call_args.kwargs["description"]
        self.assertIn("Line one<br>Line two<br>Line three", description)

    async def test_spam_message_is_rejected(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Do we reject it if people put a phone number in the phone_number field?

        We should! The phone_number field is labeled as the Subject field in the
        UI. Anything putting a phone number in here is a bot to be rejected.
        """
        msg = self.test_msg.copy()
        msg["phone_number"] = "909-576-4123"
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(mock_task.delay.call_count, 0)

        # Number in middle of subject is OK!
        msg["phone_number"] = "asdf 909 asdf"
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(mock_task.delay.call_count, 1)

    async def test_removals_require_http(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Do we ensure removals have an HTTP link?"""
        msg = self.test_msg.copy()

        # Removal subject without link fails
        msg["phone_number"] = "Removal request"
        msg["message"] = "test in message with lots of long words"
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(mock_task.delay.call_count, 0)

        msg["phone_number"] = "Please remove link!"
        msg["message"] = "test in message with lots of long words"
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(mock_task.delay.call_count, 0)

        # Test regex matching on removals fails
        msg["phone_number"] = "take down request"
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(mock_task.delay.call_count, 0)

        # Removal subject with link is OK!
        msg["message"] = "test http in message"
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertEqual(mock_task.delay.call_count, 1)

    async def test_documentation_checkbox_required(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Is the documentation checkbox required for support-type issues?"""
        for issue_type in ContactForm.DOCUMENTATION_CHECK_TYPES:
            with self.subTest(issue_type=issue_type):
                msg = self.test_msg.copy()
                msg["issue_type"] = issue_type
                if issue_type in ContactForm.TECH_ISSUE_TYPES:
                    msg["tech_description"] = "Something is broken"
                del msg["checked_documentation"]

                # Without checkbox, form is rejected
                response = await self.async_client.post(
                    reverse("contact"), msg
                )
                self.assertEqual(response.status_code, HTTPStatus.OK)

                # With checkbox, form is accepted
                msg["checked_documentation"] = True
                response = await self.async_client.post(
                    reverse("contact"), msg
                )
                self.assertEqual(response.status_code, HTTPStatus.FOUND)

    async def test_documentation_checkbox_not_required_for_other_types(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Is the documentation checkbox skipped for non-support issue types?"""
        msg = self.test_msg.copy()
        msg["issue_type"] = "data_quality"
        msg.pop("checked_documentation", None)
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    async def test_issue_type_prefilled_from_query_param(
        self, mock_captcha: MagicMock, mock_task: MagicMock
    ) -> None:
        """Does ?issue_type=mcp preselect the MCP option on first load?"""
        r = await self.async_client.get(
            reverse("contact"), {"issue_type": "mcp"}
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        html = fromstring(r.content.decode())
        selected = html.xpath(
            "//select[@name='issue_type']/option[@selected]/@value"
        )
        self.assertEqual(selected, ["mcp"])


class PageLoadTestMixin(TestCase):
    def assert_page_title_in_html(self, content: str) -> None:
        """Make sure a page has a valid HTML title."""
        html_tree = fromstring(content)
        title = cast(list[str], html_tree.xpath("//title/text()"))
        self.assertGreater(
            len(title),
            0,
            msg="This page didn't have any text in it's <title> tag.",
        )
        self.assertGreater(
            len(title[0].strip()),
            0,
            msg="The text in this title tag is empty.",
        )

    async def assert_page_loads_ok(self, reverse_param: dict) -> HttpResponse:
        """Does a page load properly?

        Args:
            reverse_param: Params that can be sent to Django's reverse
                function to get a URL path.

        Returns:
            The response object.
        """
        path = reverse(**reverse_param)
        r = await self.async_client.get(path)
        self.assertEqual(
            r.status_code,
            HTTPStatus.OK,
            msg="Got wrong status code for page at: {path}\n  args: "
            "{args}\n  kwargs: {kwargs}\n  Status Code: {code}".format(
                path=path,
                args=reverse_param.get("args", []),
                kwargs=reverse_param.get("kwargs", {}),
                code=r.status_code,
            ),
        )
        is_html = "text/html" in r["content-type"]
        if r["content-type"] and is_html:
            self.assert_page_title_in_html(r.content.decode())
        return r


class SimpleSitemapTest(TestCase):
    def test_every_sitemap_entry_reverses(self) -> None:
        """Does every sitemap entry point to a URL name that still exists?

        Regression test for stale entries left behind when a page is
        removed, like the old contribute page.
        """
        sitemap = SimpleSitemap()
        for item in sitemap.items():
            with self.subTest(view_name=item["view_name"]):
                self.assertTrue(sitemap.location(item))

        r = self.client.get(reverse("sitemaps", kwargs={"section": "simple"}))
        self.assertEqual(r.status_code, HTTPStatus.OK)


class SimplePagesTest(PageLoadTestMixin, SimpleUserDataMixin, TestCase):
    async def test_simple_pages(self) -> None:
        """Do all the simple pages load properly?"""
        reverse_params: list[dict[str, Any]] = [
            # Info pages
            {"viewname": "robots"},
            # Contact
            {"viewname": "contact"},
            {"viewname": "contact_thanks"},
            # Help pages
            {"viewname": "help_home"},
            {"viewname": "broken_email_help"},
            # Monitoring pages
            {"viewname": "celery_queue_lengths"},
            {"viewname": "heartbeat"},
            {"viewname": "health_check"},
            {"viewname": "check_redis_writes"},
            {"viewname": "elastic_status"},
            {"viewname": "replication_status"},
        ]
        for reverse_param in reverse_params:
            with self.subTest(
                "Checking simple pages", reverse_params=reverse_param
            ):
                await self.assert_page_loads_ok(reverse_param)

    async def test_profile_urls(self) -> None:
        """Do all of the profile URLs load properly?"""
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )
        reverse_params = [
            {"viewname": "view_settings"},
            {"viewname": "profile_notes"},
            {"viewname": "profile_search_alerts"},
            {"viewname": "profile_docket_alerts"},
            {"viewname": "password_change"},
            {"viewname": "delete_account"},
            {"viewname": "take_out"},
            {"viewname": "profile_your_support"},
            {"viewname": "view_api"},
        ]
        for reverse_param in reverse_params:
            await self.assert_page_loads_ok(reverse_param)


@override_flag("use_new_design", True)
@override_settings(WAFFLE_CACHE_PREFIX="test_v2_register_waffle")
class V2PagesRegisterTest(PageLoadTestMixin, SimpleUserDataMixin, TestCase):
    """Registry of pages with v2 (redesigned) templates.

    Adding a page here is part of the definition of done for a
    redesigned template. The homepage is excluded — it has dedicated
    tests in cl/search/tests/test_v2_pages.py.

    Unfinished pages go in WIP_PAGES instead, and move to V2_PAGES when
    their template is promoted from the WIP prefix to v2_.
    """

    # Built in setUpTestData: the docket tabs reverse against a docket
    # that has to exist first.
    V2_PAGES: list[tuple[dict[str, Any], str]]

    @classmethod
    def setUpTestData(cls) -> None:
        """Creates the records the registered pages need and lists the pages.

        Each entry is (reverse_param, expected v2 template).
        """
        super().setUpTestData()
        docket = DocketFactory(
            court=CourtFactory(id="canb", jurisdiction="FB"),
            source=Docket.RECAP,
        )
        PartyTypeFactory(
            docket=docket,
            party=PartyFactory(name="Test Plaintiff Inc.", docket=docket),
            name="Plaintiff",
        )
        docket_kwargs = {"docket_id": docket.pk, "slug": docket.slug}
        cls.V2_PAGES = [
            # Help pages
            ({"viewname": "help_home"}, "v2_help/index.html"),
            # Info pages
            ({"viewname": "components"}, "v2_components.html"),
            # API pages
            ({"viewname": "court_index"}, "v2_jurisdictions.html"),
            # Docket tabs
            (
                {"viewname": "docket_parties", "kwargs": docket_kwargs},
                "v2_docket_parties.html",
            ),
        ]

    # (reverse_param, expected WIP template)
    WIP_PAGES: list[tuple[dict[str, Any], str]] = []

    # WIP pages that redirect anonymous visitors to sign in
    AUTHENTICATED_WIP_PAGES: list[tuple[dict[str, Any], str]] = [
        ({"viewname": "view_api"}, "wip_profile/api.html"),
    ]

    @staticmethod
    def _get_legacy_counterpart(v2_template: str) -> str | None:
        """Returns the legacy template a v2 one replaces, None otherwise."""
        legacy = v2_template.removeprefix("v2_")
        try:
            get_template(legacy)
            return legacy
        except TemplateDoesNotExist:
            return None

    @staticmethod
    def _get_wip_fallback(wip_template: str) -> str | None:
        """Returns the template a WIP page shows without the WIP flag.

        Mirrors the middleware: the page's v2_ template when it has one,
        otherwise its legacy one. None means it has neither and is a 404.
        """
        name = wip_template.removeprefix(WIP_PROPS["prefix"])
        for candidate in (f"v2_{name}", name):
            try:
                get_template(candidate)
                return candidate
            except TemplateDoesNotExist:
                continue
        return None

    def _iter_wip_pages(self) -> Iterator[tuple[dict[str, Any], str]]:
        """Yields every registered WIP page, anonymous ones first.

        Logs self.client in before yielding AUTHENTICATED_WIP_PAGES, so
        callers must request each page with self.client as they iterate.
        """
        yield from self.WIP_PAGES
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        yield from self.AUTHENTICATED_WIP_PAGES

    async def test_v2_pages(self) -> None:
        """Do all registered v2 pages load properly with the redesign flag?"""
        for reverse_param, v2_template in self.V2_PAGES:
            with self.subTest(
                "Checking v2 page", reverse_params=reverse_param
            ):
                r = await self.assert_page_loads_ok(reverse_param)
                self.assertTemplateUsed(r, v2_template)

    def test_v2_pages_without_the_flag(self) -> None:
        """Do registered pages still load for a visitor without the flag?

        Each one falls back to its legacy template, or keeps rendering v2
        when the redesign left no legacy template behind.
        """
        for reverse_param, v2_template in self.V2_PAGES:
            with (
                self.subTest("Checking v2 page", reverse_params=reverse_param),
                override_flag("use_new_design", active=False),
            ):
                r = self.client.get(reverse(**reverse_param))
                self.assertEqual(r.status_code, HTTPStatus.OK)
                self.assertTemplateUsed(
                    r, self._get_legacy_counterpart(v2_template) or v2_template
                )

    @override_flag(WIP_PROPS["flag"], active=True)
    def test_wip_pages(self) -> None:
        """Do all registered WIP pages load with both redesign flags?"""
        for reverse_param, wip_template in self._iter_wip_pages():
            with self.subTest(
                "Checking WIP page", reverse_params=reverse_param
            ):
                r = self.client.get(reverse(**reverse_param))
                self.assertEqual(r.status_code, HTTPStatus.OK)
                self.assertTemplateUsed(r, wip_template)

    @override_flag(WIP_PROPS["flag"], active=False)
    def test_wip_pages_without_the_wip_flag(self) -> None:
        """Do registered WIP pages stay hidden with only use_new_design?

        Each one falls back to its v2_ template, then its legacy one, or is
        a 404 when the page has neither.
        """
        for reverse_param, wip_template in self._iter_wip_pages():
            with self.subTest(
                "Checking WIP page", reverse_params=reverse_param
            ):
                r = self.client.get(reverse(**reverse_param))
                fallback = self._get_wip_fallback(wip_template)
                if fallback is None:
                    self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)
                    continue
                self.assertEqual(r.status_code, HTTPStatus.OK)
                self.assertTemplateUsed(r, fallback)


@override_flag("use_new_design", True)
@override_settings(WAFFLE_CACHE_PREFIX="test_new_base_view_count_waffle")
class NewBaseViewCountTest(TestCase):
    """new_base.html only wires view counting for decorated views.

    The tracked side is covered on the docket page in
    cl/opinion_page/tests.py; this checks the untracked side on a page
    whose view has no track_view_counter.
    """

    async def test_untracked_page_sends_no_view_count(self) -> None:
        """A v2 page whose view is not decorated carries no label, no endpoint and no store, so the browser makes no request."""
        r = await self.async_client.get(reverse("help_home"))
        self.assertTemplateUsed(r, "new_base.html")
        html = r.content.decode()
        body = next(fromstring(html).iter("body"))
        self.assertIsNone(body.get("data-view-count-label"))
        self.assertIsNone(body.get("data-view-count-url"))
        self.assertNotIn("view_count.js", html)


@override_flag("use_new_design", True)
@override_settings(WAFFLE_CACHE_PREFIX="test_new_base_recap_waffle")
class NewBaseRecapDetectionTest(TestCase):
    """new_base.html loads the RECAP extension detector and reflects its cookie.

    The class on <html> is what the stylesheet keys on to hide RECAP pleas;
    rendering it from the cookie keeps later page loads from flashing them.
    """

    async def test_detector_is_loaded_on_every_page(self) -> None:
        """A v2 page requires the detector whether or not the cookie is set."""
        r = await self.async_client.get(reverse("help_home"))
        self.assertTemplateUsed(r, "new_base.html")
        self.assertIn("recap_detection.js", r.content.decode())

    async def test_html_class_follows_the_cookie(self) -> None:
        """<html> carries recap-installed only when the cookie is present."""
        r = await self.async_client.get(reverse("help_home"))
        self.assertNotIn(
            "recap-installed", fromstring(r.content.decode()).get("class", "")
        )

        self.async_client.cookies["recap_installed"] = "true"
        r = await self.async_client.get(reverse("help_home"))
        self.assertIn(
            "recap-installed", fromstring(r.content.decode()).get("class", "")
        )


@patch("hcaptcha.fields.hCaptchaField.validate", return_value=True)
class SealingOrderDetectionTest(SimpleTestCase):
    def _make_form(
        self,
        subject: str = "Test subject",
        message: str = "http://example.com",
        issue_type: str = ContactForm.REMOVAL_REQUEST,
        email: str = "test@example.com",
    ) -> ContactForm:
        data: dict[str, Any] = {
            "name": "Test User",
            "email": email,
            "phone_number": subject,
            "issue_type": issue_type,
            "message": message,
            "hcaptcha": "xxx",
        }
        if issue_type in ContactForm.DOCUMENTATION_CHECK_TYPES:
            data["checked_documentation"] = True
        form = ContactForm(data)
        form.is_valid()
        return form

    def test_sealing_keywords_trigger_recategorization(
        self, mock_captcha: MagicMock
    ) -> None:
        keywords = [
            "urgent",
            "sealing",
            "sealed",
            "redacted",
            "struck",
            "stricken",
            "pseudonym",
            "anonymity",
            "press coverage",
            "time sensitive",
        ]
        for keyword in keywords:
            with self.subTest(keyword=keyword):
                form = self._make_form(
                    message=f"Please this is {keyword} http://example.com",
                )
                self.assertEqual(form.get_zoho_request_type(), "Sealing Order")
                self.assertEqual(form.get_zoho_assignee_id(), "")

    def test_removal_without_keywords_stays_removal(
        self, mock_captcha: MagicMock
    ) -> None:
        form = self._make_form(
            subject="Remove my case",
            message="Please remove http://example.com/case/123",
        )
        self.assertEqual(form.get_zoho_request_type(), "Case Removal Request")

    def test_sealing_keyword_in_subject(self, mock_captcha: MagicMock) -> None:
        form = self._make_form(
            subject="Urgent sealing order needed",
            message="Please see http://example.com/case/123",
        )
        self.assertEqual(form.get_zoho_request_type(), "Sealing Order")
        self.assertEqual(form.get_zoho_assignee_id(), "")

    def test_uscourts_gov_email_treated_as_sealing(
        self, mock_captcha: MagicMock
    ) -> None:
        form = self._make_form(
            email="clerk@uscourts.gov",
            issue_type=ContactForm.SUPPORT_REQUEST,
            message="General question",
        )
        self.assertEqual(form.get_zoho_request_type(), "Sealing Order")
        self.assertEqual(form.get_zoho_assignee_id(), "")

    def test_usdoj_gov_email_treated_as_sealing(
        self, mock_captcha: MagicMock
    ) -> None:
        form = self._make_form(
            email="attorney@usdoj.gov",
            issue_type=ContactForm.DATA_QUALITY,
            message="Data issue",
        )
        self.assertEqual(form.get_zoho_request_type(), "Sealing Order")
        self.assertEqual(form.get_zoho_assignee_id(), "")

    def test_non_gov_email_not_treated_as_sealing(
        self, mock_captcha: MagicMock
    ) -> None:
        form = self._make_form(
            email="user@gmail.com",
            issue_type=ContactForm.SUPPORT_REQUEST,
            message="General question",
        )
        self.assertEqual(form.get_zoho_request_type(), "General Support")


@patch("hcaptcha.fields.hCaptchaField.validate", return_value=True)
class ZohoRoutingTest(SimpleUserDataMixin, TestCase):
    """Test that form submissions route to the correct Zoho category."""

    @patch("cl.simple_pages.views.create_zoho_desk_ticket")
    async def test_support_request_creates_desk_ticket(
        self, mock_task: MagicMock, mock_captcha: MagicMock
    ) -> None:
        msg = {
            "name": "Test User",
            "phone_number": "Help needed",
            "issue_type": "support",
            "message": "I need general help please",
            "email": "test@example.com",
            "hcaptcha": "xxx",
            "checked_documentation": True,
        }
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        self.assertEqual(call_kwargs["request_type"], "General Support")

    @patch("cl.simple_pages.views.create_zoho_desk_ticket")
    async def test_mcp_request_creates_desk_ticket(
        self, mock_task: MagicMock, mock_captcha: MagicMock
    ) -> None:
        msg = {
            "name": "Dev User",
            "phone_number": "MCP help",
            "issue_type": "mcp",
            "tech_description": "My MCP client cannot connect to the server",
            "message": "",
            "email": "dev@example.com",
            "hcaptcha": "xxx",
            "checked_documentation": True,
        }
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        self.assertEqual(call_kwargs["request_type"], "MCP Server")
        self.assertIn(
            "My MCP client cannot connect to the server",
            call_kwargs["description"],
        )

    @patch("cl.simple_pages.views.create_zoho_desk_ticket")
    async def test_partnership_creates_desk_ticket(
        self, mock_task: MagicMock, mock_captcha: MagicMock
    ) -> None:
        msg = {
            "name": "Partner Person",
            "phone_number": "Partnership request",
            "issue_type": "partnerships",
            "email": "partner@example.com",
            "message": "",
            "partner_background": ["founder"],
            "partner_current_work": "Building legal tech",
            "partner_prior_outreach": "Talked to some orgs",
            "partner_team_size": "2_5",
            "partner_founded_year": "2024",
            "partner_funding_total": "none",
            "partner_funding_stage": "pre_seed",
            "partner_ideal_outcome": "API access",
            "hcaptcha": "xxx",
        }
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        self.assertEqual(call_kwargs["email"], "partner@example.com")
        self.assertEqual(call_kwargs["request_type"], "Partnership Inquiry")

    @patch("cl.simple_pages.views.create_zoho_desk_ticket")
    async def test_removal_with_sealing_keyword_is_recategorized(
        self, mock_task: MagicMock, mock_captcha: MagicMock
    ) -> None:
        msg = {
            "name": "Test User",
            "phone_number": "Please seal my case",
            "issue_type": "removal",
            "message": "Urgent sealing order http://example.com/case",
            "email": "test@example.com",
            "hcaptcha": "xxx",
        }
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        self.assertEqual(call_kwargs["request_type"], "Sealing Order")
        self.assertEqual(call_kwargs["assignee_id"], "")

    @patch("cl.simple_pages.views.create_zoho_desk_ticket")
    async def test_uscourts_email_routed_as_sealing(
        self, mock_task: MagicMock, mock_captcha: MagicMock
    ) -> None:
        msg = {
            "name": "Court Clerk",
            "phone_number": "General inquiry",
            "issue_type": "support",
            "message": "I have a question about a case",
            "email": "clerk@uscourts.gov",
            "hcaptcha": "xxx",
            "checked_documentation": True,
        }
        response = await self.async_client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        self.assertEqual(call_kwargs["request_type"], "Sealing Order")
        self.assertEqual(call_kwargs["assignee_id"], "")


class ContentSecurityPolicyTest(TestCase):
    """Tests for the site-wide CSP header configured in cl.settings."""

    async def test_navigation_is_locked_to_our_own_domain(self) -> None:
        """Do we stop third-party content from sending users elsewhere?

        We publish a lot of HTML that we get from third parties, so we use CSP
        to keep any forms or <base> tags it contains from pointing at another
        site.
        """
        r = cast(
            HttpResponse, await self.async_client.get(reverse("help_home"))
        )
        directives = parse_csp(r)
        self.assertEqual(directives["form-action"], ["'self'"])
        self.assertEqual(directives["base-uri"], ["'self'"])

    async def test_script_nonce_matches_the_rendered_page(self) -> None:
        """Does the nonce in the header match the one in the HTML?

        If these ever drift apart, every inline script on the site breaks, so
        check that the nonce plumbing between the middleware and the templates
        is intact.
        """
        r = cast(
            HttpResponse, await self.async_client.get(reverse("help_home"))
        )
        script_src = parse_csp(r)["script-src"]
        nonces = [
            value[len("'nonce-") : -len("'")]
            for value in script_src
            if value.startswith("'nonce-")
        ]
        self.assertEqual(
            len(nonces), 1, msg=f"Expected one nonce in: {script_src}"
        )
        html = r.content.decode()
        self.assertIn(f'nonce="{nonces[0]}"', html)
        # A script left with an empty nonce would be refused by the browser,
        # and the assertion above would still pass on the other scripts.
        self.assertNotIn('nonce=""', html)


class ButtonComponentTest(CottonComponentMixin, SimpleTestCase):
    """The c-button busy state: declared by aria-busy, static or bound."""

    def test_a_plain_button_renders_no_busy_markup(self) -> None:
        """Without aria-busy there is no wrapper, spinner or status region."""
        for source, tag in (
            ('<c-button variant="primary">Save</c-button>', "button"),
            ('<c-button variant="primary" href="/x/">Save</c-button>', "a"),
            (
                '<c-button variant="primary" touch_target>Save</c-button>',
                "button",
            ),
        ):
            with self.subTest(tag=tag, source=source):
                root = fromstring(self.render_component(source))
                self.assertEqual(root.tag, tag)
                self.assertIsNone(root.get("x-busy-button"))
                self.assertEqual(root.xpath('.//*[local-name()="svg"]'), [])
                self.assertEqual(root.xpath('.//*[@role="status"]'), [])

    def test_caller_attributes_reach_the_busy_capable_button(self) -> None:
        """A bound aria-busy adds the busy markup without eating other attributes."""
        for source, tag in (
            (
                '<c-button variant="primary" type="submit" x-bind:aria-busy="busy" class="w-full">Save</c-button>',
                "button",
            ),
            (
                '<c-button variant="primary" href="/x/" rel="nofollow" x-bind:aria-busy="busy" class="w-full">Save</c-button>',
                "a",
            ),
        ):
            with self.subTest(tag=tag):
                root = fromstring(self.render_component(source))
                self.assertIsNotNone(root.get("x-busy-button"))
                element = root.find(tag)
                self.assertIsNotNone(element)
                self.assertEqual(element.get("x-bind:aria-busy"), "busy")
                self.assertIn("w-full", element.get("class").split())
                if tag == "a":
                    self.assertEqual(element.get("href"), "/x/")
                    self.assertEqual(element.get("rel"), "nofollow")
                else:
                    self.assertEqual(element.get("type"), "submit")

    def test_busy_keeps_the_label_and_hides_the_spinner_from_assistive_technology(
        self,
    ) -> None:
        """The label alone is the accessible name while busy."""
        for source in (
            '<c-button variant="primary" aria-busy="true">Save</c-button>',
            '<c-button variant="primary" touch_target aria-busy="true">Save</c-button>',
            '<c-button variant="primary" href="#" aria-busy="true">Save</c-button>',
        ):
            with self.subTest(source=source):
                root = fromstring(self.render_component(source))
                element = root[0]
                self.assertEqual(element.get("aria-busy"), "true")
                spinners = element.xpath('.//*[local-name()="svg"]')
                self.assertEqual(len(spinners), 1)
                self.assertEqual(spinners[0].get("aria-hidden"), "true")
                self.assertEqual(element.text_content().strip(), "Save")
                statuses = root.xpath('./*[@role="status"]')
                self.assertEqual(len(statuses), 1)
                self.assertEqual(statuses[0].text_content(), "")
                self.assertTrue(statuses[0].get("data-busy-text"))

    def test_busy_text_is_what_the_status_region_announces(self) -> None:
        """busy_text reaches the status region and never the button."""
        root = fromstring(
            self.render_component(
                '<c-button variant="primary" aria-busy="true" busy_text="Saving your changes">Save</c-button>'
            )
        )
        status = root.xpath('./*[@role="status"]')[0]
        self.assertEqual(status.get("data-busy-text"), "Saving your changes")
        self.assertIsNone(root[0].get("busy_text"))


class DialogComponentTest(CottonComponentMixin, SimpleTestCase):
    """The c-dialog component renders a trigger only when given one."""

    def test_trigger_slot_renders_a_trigger(self) -> None:
        """Trigger content renders the default trigger button."""
        html = self.render_component(
            '<c-dialog><c-slot name="button_content">Open</c-slot>'
            '<c-slot name="panel">Body</c-slot></c-dialog>'
        )
        self.assertIn('aria-haspopup="dialog"', html)

    def test_without_a_trigger_slot_no_trigger_is_rendered(self) -> None:
        """A dialog opened by other means, such as an event listener, has no trigger button."""
        html = self.render_component(
            '<c-dialog><c-slot name="panel">Body</c-slot></c-dialog>'
        )
        self.assertNotIn('aria-haspopup="dialog"', html)
        self.assertIn("Body", html)


class TooltipComponentTest(CottonComponentMixin, SimpleTestCase):
    """The c-tooltip component renders a help button and its message."""

    def test_button_is_named_after_what_it_explains(self) -> None:
        """The icon-only button gets a name that says what it explains."""
        tree = fromstring(
            self.render_component(
                '<c-tooltip label="Last Updated" message="Message" />'
            )
        )
        button = tree.xpath("//button")[0]
        self.assertEqual(button.get("aria-label"), "More about Last Updated")
        self.assertEqual(button.get("type"), "button")

    def test_button_exposes_whether_the_tooltip_is_open(self) -> None:
        """The button's aria-expanded is bound to the open state."""
        html = self.render_component(
            '<c-tooltip label="Item" message="Message" />'
        )
        self.assertIn('x-bind:aria-expanded="isOpen"', html)

    def test_live_region_starts_empty(self) -> None:
        """The live region is empty until the tooltip opens, so the message is announced as new content."""
        tree = fromstring(
            self.render_component(
                '<c-tooltip label="Item" message="Message" />'
            )
        )
        live = tree.xpath("//*[@role='status']")[0]
        self.assertEqual(len(live), 0)
        self.assertFalse((live.text or "").strip())

    def test_message_html_is_not_escaped(self) -> None:
        """A safe message, such as the Last Updated <strong>, renders as markup."""
        html = self.render_component(
            '<c-tooltip label="Item" :message="message" />',
            {"message": mark_safe("Updated by <strong>RECAP</strong>")},
        )
        self.assertIn("<strong>RECAP</strong>", html)

    def test_arrow_renders_only_when_requested(self) -> None:
        """has_arrow adds the arrow; leaving it out gives the no-arrow variant."""
        cases = [
            ('<c-tooltip label="Item" has_arrow message="Message" />', 1),
            ('<c-tooltip label="Item" message="Message" />', 0),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                tree = fromstring(self.render_component(source))
                self.assertEqual(len(tree.xpath("//*[@data-arrow]")), expected)

    def test_description_renders_only_when_given(self) -> None:
        """A description adds supporting text and the roomier padding."""
        with_description = self.render_component(
            '<c-tooltip label="Item" description="Supporting text" message="Message" />'
        )
        self.assertIn("Supporting text", with_description)
        self.assertIn("p-3", with_description)

        without_description = self.render_component(
            '<c-tooltip label="Item" message="Message" />'
        )
        self.assertIn("px-3 py-2", without_description)
        self.assertNotIn("p-3", without_description)

    def test_variant_picks_the_theme(self) -> None:
        """Dark is the default theme and light is opt-in."""
        cases = [
            (
                '<c-tooltip label="Item" message="Message" />',
                "bg-greyscale-900",
            ),
            (
                '<c-tooltip label="Item" variant="light" message="Message" />',
                "bg-white",
            ),
        ]
        for source, background in cases:
            with self.subTest(background=background):
                self.assertIn(background, self.render_component(source))

    def test_position_is_passed_to_the_anchor(self) -> None:
        """The position prop sets the x-anchor placement and its padding axis.

        Defaults to bottom; only that axis is padded to bridge the hover gap.
        """
        cases = [
            (
                '<c-tooltip label="Item" message="Message" />',
                "bottom",
                "py-1.5",
            ),
            (
                '<c-tooltip label="Item" position="top-start" message="Message" />',
                "top-start",
                "py-1.5",
            ),
            (
                '<c-tooltip label="Item" position="right" message="Message" />',
                "right",
                "px-1.5",
            ),
        ]
        for source, position, padding in cases:
            with self.subTest(position=position):
                live = fromstring(self.render_component(source)).xpath(
                    "//*[@role='status']"
                )[0]
                self.assertEqual(
                    live.get(f"x-anchor.{position}"), "$refs.trigger"
                )
                self.assertIn(padding, live.get("class").split())


class TabsComponentTest(CottonComponentMixin, SimpleTestCase):
    """c-tabs renders link tabs or panel tabs, depending on its tab list."""

    ROOT_ID = "my-tabs-tabs"
    LINK_SOURCE = (
        '<c-tabs label="My tabs" :tabs="tabs" :active_tab="active_tab">'
        "Page content</c-tabs>"
    )
    PANEL_SOURCE = (
        '<c-tabs label="My tabs" :tabs="tabs" :active_tab="active_tab">'
        '<c-tabs.panel key="first" tabs_label="My tabs" :active_tab="active_tab">One</c-tabs.panel>'
        '<c-tabs.panel key="second" tabs_label="My tabs" :active_tab="active_tab">Two</c-tabs.panel>'
        "</c-tabs>"
    )

    def panel_tabs(self) -> list[TabItem]:
        """Two tabs without urls; the first has a count."""
        return [
            {"key": "first", "label": "First", "count": 3},
            {"key": "second", "label": "Second"},
        ]

    def link_tabs(self) -> list[TabItem]:
        """The panel tabs, each with a url."""
        url = reverse("components")
        return [
            {**tab, "url": f"{url}?link_tab={tab['key']}"}
            for tab in self.panel_tabs()
        ]

    def render(self, source: str, **context: Any) -> HtmlElement:
        """Renders a Cotton snippet and parses the result."""
        return fromstring(self.render_component(source, context))

    def test_link_tabs_render_a_nav_of_links(self) -> None:
        """Link tabs are links in a nav, and htmx targets the component's root."""
        tabs = self.link_tabs()
        root = self.render(self.LINK_SOURCE, tabs=tabs, active_tab="first")

        self.assertEqual(root.get("id"), self.ROOT_ID)
        nav = root.xpath("//nav")[0]
        self.assertEqual(nav.get("aria-label"), "My tabs")
        self.assertEqual(nav.get("hx-target"), f"#{self.ROOT_ID}")
        self.assertEqual(nav.get("hx-select"), f"#{self.ROOT_ID}")
        for tab in tabs:
            with self.subTest(key=tab["key"]):
                link = root.get_element_by_id(
                    f"{self.ROOT_ID}-tab-{tab['key']}"
                )
                self.assertEqual(link.tag, "a")
                self.assertEqual(link.get("href"), tab["url"])

    def test_link_tabs_stay_out_of_the_history_cache(self) -> None:
        """Link tabs opt out of htmx's history cache, so private pages aren't stored."""
        root = self.render(
            self.LINK_SOURCE, tabs=self.link_tabs(), active_tab="first"
        )

        self.assertEqual(root.get("hx-history"), "false")

    def test_link_tabs_declare_their_error_messages(self) -> None:
        """The error messages come from the template, not from the JS."""
        root = self.render(
            self.LINK_SOURCE, tabs=self.link_tabs(), active_tab="first"
        )

        for attribute in (
            "data-error-message-connection",
            "data-error-message-server",
        ):
            with self.subTest(attribute=attribute):
                self.assertTrue(root.get(attribute))

    def test_only_the_active_link_is_current(self) -> None:
        """Only the active tab's link has aria-current="page"."""
        for active in ("first", "second"):
            with self.subTest(active=active):
                root = self.render(
                    self.LINK_SOURCE, tabs=self.link_tabs(), active_tab=active
                )
                current = root.xpath('//nav//a[@aria-current="page"]/@id')
                self.assertEqual(current, [f"{self.ROOT_ID}-tab-{active}"])

    def test_tabs_without_urls_render_as_tab_buttons(self) -> None:
        """A list without urls renders a tablist of buttons and no links."""
        root = self.render(
            self.PANEL_SOURCE, tabs=self.panel_tabs(), active_tab="first"
        )

        self.assertEqual(
            root.xpath('//*[@role="tablist"]/@aria-label'), ["My tabs"]
        )
        self.assertEqual(
            [tab.tag for tab in root.xpath('//*[@role="tab"]')],
            ["button", "button"],
        )
        self.assertFalse(root.xpath("//a"))

    def test_only_the_active_tab_is_selected_and_focusable(self) -> None:
        """The active tab starts selected and in the Tab order; the rest don't."""
        for active in ("first", "second"):
            with self.subTest(active=active):
                root = self.render(
                    self.PANEL_SOURCE,
                    tabs=self.panel_tabs(),
                    active_tab=active,
                )
                for button in root.xpath('//*[@role="tab"]'):
                    is_active = button.get("data-tab-key") == active
                    self.assertEqual(
                        button.get("aria-selected"),
                        "true" if is_active else "false",
                    )
                    self.assertEqual(
                        button.get("tabindex"), "0" if is_active else "-1"
                    )

    def test_tabs_and_panels_reference_each_other(self) -> None:
        """Each tab controls its panel, and each panel is labelled by its tab."""
        root = self.render(
            self.PANEL_SOURCE, tabs=self.panel_tabs(), active_tab="first"
        )
        for key in ("first", "second"):
            with self.subTest(key=key):
                tab_id = f"{self.ROOT_ID}-tab-{key}"
                panel_id = f"{self.ROOT_ID}-panel-{key}"
                panel = root.get_element_by_id(panel_id)
                self.assertEqual(
                    root.get_element_by_id(tab_id).get("aria-controls"),
                    panel_id,
                )
                self.assertEqual(panel.get("aria-labelledby"), tab_id)
                self.assertEqual(panel.get("role"), "tabpanel")
                self.assertEqual(panel.get("tabindex"), "0")

    def test_only_the_active_panel_is_visible(self) -> None:
        """Inactive panels are hidden on the server, so they never flash on load."""
        for active in ("first", "second"):
            with self.subTest(active=active):
                root = self.render(
                    self.PANEL_SOURCE,
                    tabs=self.panel_tabs(),
                    active_tab=active,
                )
                for panel in root.xpath('//*[@role="tabpanel"]'):
                    self.assertEqual(
                        "hidden" in panel.attrib,
                        panel.get("data-tab-key") != active,
                    )

    def test_first_tab_is_selected_without_active_tab(self) -> None:
        """Panel tabs fall back to the first tab when no active_tab is passed."""
        root = self.render(
            '<c-tabs label="My tabs" :tabs="tabs">One</c-tabs>',
            tabs=self.panel_tabs(),
        )

        self.assertEqual(root.get("data-active-tab"), "first")
        self.assertEqual(
            root.xpath('//*[@aria-selected="true"]/@data-tab-key'), ["first"]
        )

    def test_count_shows_in_a_chip(self) -> None:
        """A tab's count shows in a chip, and tabs without one have no chip."""
        root = self.render(
            self.PANEL_SOURCE, tabs=self.panel_tabs(), active_tab="first"
        )

        first = root.get_element_by_id(f"{self.ROOT_ID}-tab-first")
        second = root.get_element_by_id(f"{self.ROOT_ID}-tab-second")
        self.assertEqual([chip.text for chip in first.xpath("span")], ["3"])
        self.assertFalse(second.xpath("span"))

    def test_dropdown_lists_every_tab(self) -> None:
        """The mobile dropdown has one option per tab, with the active one selected."""
        cases = [
            ("link", self.LINK_SOURCE, self.link_tabs()),
            ("panel", self.PANEL_SOURCE, self.panel_tabs()),
        ]
        for mode, source, tabs in cases:
            with self.subTest(mode=mode):
                root = self.render(source, tabs=tabs, active_tab="second")
                select = root.get_element_by_id(f"{self.ROOT_ID}-select")
                options = select.xpath("option")

                self.assertEqual(select.get("aria-label"), "My tabs")
                self.assertEqual(
                    [option.get("value") for option in options],
                    ["first", "second"],
                )
                self.assertEqual(
                    [option.text_content() for option in options],
                    ["First (3)", "Second"],
                )
                self.assertEqual(
                    select.xpath("option[@selected]/@value"), ["second"]
                )


class IconComponentTest(CottonComponentMixin, SimpleTestCase):
    """Tests sizing, variant selection and accessibility of c-icon."""

    def path_data(self, html: str) -> list[str]:
        """Returns the drawing data of every path in the given SVG markup."""
        return fromstring(html).xpath("//path/@d")

    def test_icon_is_hidden_from_assistive_technology_by_default(self) -> None:
        """An icon without an aria_label is decorative."""
        icon = fromstring(self.render_component('<c-icon name="chevron" />'))
        self.assertEqual(icon.get("aria-hidden"), "true")
        self.assertIsNone(icon.get("aria-label"))

    def test_aria_label_gives_the_icon_an_accessible_name(self) -> None:
        """An icon with an aria_label is named and not hidden."""
        icon = fromstring(
            self.render_component(
                '<c-icon name="chevron" aria_label="Next page" />'
            )
        )
        self.assertEqual(icon.get("aria-label"), "Next page")
        self.assertIsNone(icon.get("aria-hidden"))

    def test_bound_aria_label_is_escaped(self) -> None:
        """An aria_label bound from the context can't break out of its attribute."""
        html = self.render_component(
            '<c-icon name="chevron" :aria_label="name" />',
            {"name": 'A "b" <c> & d'},
        )
        self.assertIn('aria-label="A &quot;b&quot; &lt;c&gt; &amp; d"', html)
        self.assertNotIn("<c>", html)

    def test_renders_without_surrounding_whitespace(self) -> None:
        """The icon can sit inline next to text without adding a space."""
        html = self.render_component('<c-icon name="chevron" />')
        self.assertTrue(html.startswith("<svg"), repr(html[:20]))
        self.assertTrue(html.endswith("</svg>"), repr(html[-20:]))

    def test_bound_class_is_escaped(self) -> None:
        """A class bound from the context can't add attributes to the icon."""
        icon = fromstring(
            self.render_component(
                '<c-icon name="chevron" :class="classes" />',
                {"classes": '" onload="alert(1)'},
            )
        )
        self.assertIsNone(icon.get("onload"))
        self.assertIn('onload="alert(1)', icon.get("class"))

    def test_outline_selects_the_outline_file(self) -> None:
        """The outline flag swaps the plain icon for its _outline file."""
        cases = [
            ('<c-icon name="bell" />', "bell"),
            ('<c-icon name="bell" outline />', "bell_outline"),
        ]
        for source, expected_file in cases:
            with self.subTest(source=source):
                self.assertEqual(
                    self.path_data(self.render_component(source)),
                    self.path_data(svg(expected_file)),
                )

    def test_size_sets_the_size_class(self) -> None:
        """Each size maps to its class, and anything else gets the default."""
        cases = {
            "sm": "size-4",
            "md": "size-5",
            "lg": "size-6",
            "": "size-4",
            "xs": "size-4",
        }
        for size, expected_class in cases.items():
            with self.subTest(size=size):
                icon = fromstring(
                    self.render_component(
                        f'<c-icon name="chevron" size="{size}" />'
                    )
                )
                self.assertEqual(
                    icon.get("class").split(), ["shrink-0", expected_class]
                )

    def test_class_is_added_after_the_size_class(self) -> None:
        """Extra classes keep the size class and follow it."""
        icon = fromstring(
            self.render_component(
                '<c-icon name="chevron" size="sm" class="rotate-90" />'
            )
        )
        self.assertEqual(
            icon.get("class").split(), ["shrink-0", "size-4", "rotate-90"]
        )

    def test_custom_size_leaves_sizing_to_class(self) -> None:
        """A custom size sets no size class, leaving sizing to `class`."""
        icon = fromstring(
            self.render_component(
                '<c-icon name="chevron" size="custom" class="size-3" />'
            )
        )
        self.assertEqual(icon.get("class").split(), ["shrink-0", "size-3"])


class ToastComponentTest(CottonComponentMixin, SimpleTestCase):
    """The c-toast component renders its optional parts only when given."""

    def test_title_alone_renders_only_the_close_icon(self) -> None:
        """Without a variant, icon or description, the only svg is the close button's."""
        html = self.render_component('<c-toast title="Link copied" />')
        self.assertIn("Link copied", html)
        self.assertEqual(html.count("<svg"), 1)

    @staticmethod
    def icon(name: str) -> str:
        """The markup the toast renders for a named icon."""
        return svg(name, **{"class": "size-5", "aria_hidden": "true"})

    def test_variant_adds_its_icon_and_description_its_text(self) -> None:
        """Each variant adds its own icon; the description renders when given."""
        variant_icons = {
            "info": "info",
            "success": "circle_check",
            "warning": "triangle_exclamation",
        }
        for variant, icon in variant_icons.items():
            with self.subTest(variant=variant):
                html = self.render_component(
                    f'<c-toast variant="{variant}" title="Docket blocked"'
                    ' description="No longer indexed" />'
                )
                self.assertIn("No longer indexed", html)
                self.assertEqual(html.count("<svg"), 2)
                self.assertIn(self.icon(icon), html)

    def test_unknown_variant_renders_no_icon(self) -> None:
        """A variant outside the presets renders neither an icon nor its slot."""
        html = self.render_component(
            '<c-toast variant="error" title="Oops" />'
        )
        self.assertEqual(html.count("<svg"), 1)

    def test_icon_prop_replaces_the_variant_icon(self) -> None:
        """A named icon renders instead of the variant's, as the only icon."""
        html = self.render_component(
            '<c-toast variant="success" title="Alert created" icon="bell" />'
        )
        self.assertIn(self.icon("bell"), html)
        self.assertNotIn(self.icon("circle_check"), html)

    def test_trigger_slot_renders_inside_the_root(self) -> None:
        """A trigger slot renders; a toast opened by an event has none."""
        with_trigger = self.render_component(
            '<c-toast title="Saved"><c-slot name="trigger">'
            '<button x-on:click="open">Show</button></c-slot></c-toast>'
        )
        self.assertIn('x-on:click="open"', with_trigger)
        self.assertNotIn(
            'x-on:click="open"',
            self.render_component('<c-toast title="Saved" />'),
        )

    def test_action_container_renders_only_with_content(self) -> None:
        """A trigger slot written on its own lines leaves no empty action box."""
        with_trigger = self.render_component(
            '<c-toast title="Saved">\n'
            '  <c-slot name="trigger"><button x-on:click="open">Show</button></c-slot>\n'
            "</c-toast>"
        )
        self.assertNotIn("shrink-0 items-center gap-2", with_trigger)
        with_action = self.render_component(
            '<c-toast title="Saved"><button>Undo</button></c-toast>'
        )
        self.assertIn("shrink-0 items-center gap-2", with_action)

    def test_live_region_renders_empty_and_polite(self) -> None:
        """The message column is an empty polite live region at render time."""
        html = self.render_component('<c-toast title="Docket blocked" />')
        region = re.search(r'<div[^>]*x-ref="live"[^>]*></div>', html)
        self.assertIsNotNone(region)
        for attribute in (
            'role="status"',
            'aria-live="polite"',
            'aria-atomic="true"',
        ):
            self.assertIn(attribute, region[0])

    def test_message_waits_in_a_template(self) -> None:
        """The title and description render inside a template, not in the live region."""
        html = self.render_component(
            '<c-toast title="Docket blocked" description="No longer indexed" />'
        )
        template = re.search(r"<template[^>]*>(.*?)</template>", html, re.S)
        self.assertIsNotNone(template)
        self.assertIn("Docket blocked", template[1])
        self.assertIn("No longer indexed", template[1])

    def test_controls_are_hidden_until_open(self) -> None:
        """The action container and the Close button render under an x-show gate."""
        html = self.render_component(
            '<c-toast title="Docket blocked"><button>Undo</button></c-toast>'
        )
        close_button = re.search(r'<button[^>]*aria-label="Close"[^>]*>', html)
        self.assertIsNotNone(close_button)
        self.assertIn('x-show="isOpen"', close_button[0])
        action_container = re.search(
            r"<div[^>]*shrink-0 items-center gap-2[^>]*>", html
        )
        self.assertIsNotNone(action_container)
        self.assertIn('x-show="isOpen"', action_container[0])

    def test_undeclared_attributes_land_on_the_root(self) -> None:
        """A listener passed to the component opens the toast from an event."""
        html = self.render_component(
            '<c-toast title="Saved" x-on:docket-blocked.window="open" />'
        )
        self.assertIn('x-on:docket-blocked.window="open"', html)


class ComboboxComponentTest(CottonComponentMixin, SimpleTestCase):
    """The markup c-combobox renders for each prop, which its script and the Alpine UI plugin read in the browser."""

    options = [
        {"value": 1, "label": "appeals", "selected": True},
        {"value": 2, "label": "<b>bankruptcy</b>", "selected": False},
    ]

    def render(self, source: str) -> HtmlElement:
        """Renders a Cotton snippet and returns the component's root."""
        html = self.render_component(source, {"options": self.options})
        return fromstring(html).xpath("//*[@x-data='combobox']")[0]

    def test_options_reach_the_script_as_json(self) -> None:
        """The JSON script the component's script loads parses back to the options given, HTML in a label included."""
        root = self.render('<c-combobox label="Tags" :options="options" />')
        script = root.xpath("./script[@type='application/json']")[0]
        self.assertEqual(json.loads(script.text), self.options)

    def test_listeners_land_on_the_root(self) -> None:
        """A listener written on the component tag sits on the element that dispatches the component's events."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" x-on:combobox-add="attach" />'
        )
        self.assertEqual(root.get("x-on:combobox-add"), "attach")

    def test_single_selection_is_the_default(self) -> None:
        """Without `multiple`, the root lacks the attribute that turns on multiple selection."""
        root = self.render('<c-combobox label="Tags" :options="options" />')
        self.assertIsNone(root.get("multiple"))

    def test_multiple_turns_on_multiple_selection(self) -> None:
        """With `multiple`, the root carries the attribute that turns on multiple selection."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" multiple />'
        )
        self.assertIsNotNone(root.get("multiple"))

    def test_only_multiple_shows_the_selection_as_chips(self) -> None:
        """The chip rendered per selected option exists only with `multiple`."""
        chips = ".//template[@x-for='option in $combobox.value']"
        single = self.render('<c-combobox label="Tags" :options="options" />')
        multiple = self.render(
            '<c-combobox label="Tags" :options="options" multiple />'
        )
        self.assertEqual(len(single.xpath(chips)), 0)
        self.assertEqual(len(multiple.xpath(chips)), 1)

    def test_creatable_offers_the_create_option(self) -> None:
        """With `creatable`, the list has the option that creates the typed text and the root enables it."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" creatable />'
        )
        self.assertEqual(len(root.xpath(".//template[@x-if='canCreate']")), 1)
        self.assertIsNotNone(root.get("data-creatable"))

    def test_without_creatable_there_is_no_create_option(self) -> None:
        """Without `creatable`, the list only holds the options given."""
        root = self.render('<c-combobox label="Tags" :options="options" />')
        self.assertEqual(len(root.xpath(".//template[@x-if='canCreate']")), 0)
        self.assertIsNone(root.get("data-creatable"))

    def test_creatable_needs_search(self) -> None:
        """`creatable` has no effect on a combobox that takes no typed text."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" creatable :searchable="False" />'
        )
        self.assertEqual(len(root.xpath(".//template[@x-if='canCreate']")), 0)
        self.assertIsNone(root.get("data-creatable"))

    def test_searchable_is_the_default(self) -> None:
        """Without the prop, the input accepts the text that filters the options."""
        root = self.render('<c-combobox label="Tags" :options="options" />')
        self.assertIsNone(root.xpath(".//input")[0].get("x-on:beforeinput"))

    def test_not_searchable_blocks_typing(self) -> None:
        """With search turned off, the input rejects the text entered in it."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" :searchable="False" />'
        )
        self.assertEqual(
            root.xpath(".//input")[0].get("x-on:beforeinput"), "blockTyping"
        )

    def test_only_clearable_adds_the_clear_button(self) -> None:
        """The button that empties the single selection exists only with `clearable`."""
        button = ".//button[@*[name()='x-on:click']='clear']"
        plain = self.render('<c-combobox label="Tags" :options="options" />')
        clearable = self.render(
            '<c-combobox label="Tags" :options="options" clearable />'
        )
        self.assertEqual(len(plain.xpath(button)), 0)
        self.assertEqual(len(clearable.xpath(button)), 1)

    def test_clearable_has_no_effect_with_multiple(self) -> None:
        """A combobox with chips, each with its own remove button, gets no clear button."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" multiple clearable />'
        )
        buttons = root.xpath(".//button[@*[name()='x-on:click']='clear']")
        self.assertEqual(len(buttons), 0)

    def test_name_submits_the_single_selection(self) -> None:
        """With `name`, a hidden input of that name carries the selected option's value."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" name="tag" />'
        )
        hidden = root.xpath("./input[@type='hidden'][@name='tag']")
        self.assertEqual(len(hidden), 1)
        self.assertEqual(hidden[0].get("x-bind:value"), "formValue")

    def test_name_submits_each_of_multiple_selections(self) -> None:
        """With `name` and `multiple`, one hidden input of that name is rendered per selected option."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" name="tag" multiple />'
        )
        hidden = root.xpath(
            "./template[@x-for='option in $combobox.value']/input[@type='hidden'][@name='tag']"
        )
        self.assertEqual(len(hidden), 1)

    def test_without_name_nothing_is_submitted(self) -> None:
        """Without `name`, the combobox renders no form input for its selection."""
        root = self.render('<c-combobox label="Tags" :options="options" />')
        self.assertEqual(len(root.xpath(".//input[@type='hidden']")), 0)

    def test_name_stays_off_the_root(self) -> None:
        """The root carries no `name`, which the plugin would turn into inputs of its own."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" name="tag" />'
        )
        self.assertIsNone(root.get("name"))

    def test_disabled_disables_every_control(self) -> None:
        """With `disabled`, the root, the text input, the buttons and the form input are all disabled."""
        for flags in ("multiple", "clearable"):
            with self.subTest(flags=flags):
                root = self.render(
                    f'<c-combobox label="Tags" :options="options" name="tag" {flags} disabled />'
                )
                controls = [root, *root.xpath(".//input | .//button")]
                self.assertEqual(
                    [
                        control.get("disabled") is not None
                        for control in controls
                    ],
                    [True] * len(controls),
                )

    def test_enabled_is_the_default(self) -> None:
        """Without `disabled`, no control of the combobox is disabled."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" name="tag" multiple />'
        )
        self.assertEqual(
            len(root.xpath("descendant-or-self::*[@disabled]")), 0
        )

    def test_list_is_a_popup_by_default(self) -> None:
        """Without `inline`, the plugin opens and closes the list."""
        root = self.render('<c-combobox label="Tags" :options="options" />')
        listbox = root.xpath(".//ul[@*[name()='x-combobox:options']]")[0]
        self.assertIsNone(listbox.get("static"))

    def test_inline_keeps_the_list_visible(self) -> None:
        """With `inline`, the list tells the plugin to keep it shown."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" inline />'
        )
        listbox = root.xpath(".//ul[@*[name()='x-combobox:options']]")[0]
        self.assertIsNotNone(listbox.get("static"))

    def test_inline_keeps_the_button_the_plugin_needs(self) -> None:
        """An inline combobox still renders the plugin's button, which the plugin reads on every click outside."""
        root = self.render(
            '<c-combobox label="Tags" :options="options" inline />'
        )
        buttons = root.xpath(".//button[@*[name()='x-combobox:button']]")
        self.assertEqual(len(buttons), 1)


class ComponentsToastDemoTest(TestCase):
    """The components view answers the server-rendered toast demo's htmx request."""

    def get(self, toast: str, **headers: str) -> _MonkeyPatchedWSGIResponse:
        """Requests the components page the way a demo button does."""
        return self.client.get(
            reverse("components"),
            {"toast": toast},
            headers={"HX-Request": "true", "X-CL-Design": "v2", **headers},
        )

    def test_server_renders_the_toast_partial(self) -> None:
        """The server-rendered demo swaps a toast in and opens it after settle."""
        r = self.get("server")
        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(r, "v2_includes/components/toast_demo.html")
        self.assertEqual(
            r["HX-Trigger-After-Settle"], "toast-demo-server-ready"
        )
        self.assertContains(r, 'id="toast-demo-server"')
        self.assertContains(r, 'hx-swap-oob="true"')

    def test_other_requests_get_the_page(self) -> None:
        """Another name, or a request that is not htmx, renders the library."""
        for toast, headers in (("nope", {}), ("server", {"HX-Request": ""})):
            with self.subTest(toast=toast, headers=headers):
                r = self.get(toast, **headers)
                self.assertEqual(r.status_code, HTTPStatus.OK)
                self.assertTemplateUsed(r, "v2_components.html")
