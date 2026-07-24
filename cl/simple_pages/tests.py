from http import HTTPStatus
from typing import Any, cast
from unittest.mock import MagicMock, patch

from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import HttpResponse
from django.test import override_settings
from django.urls import reverse
from lxml.html import fromstring
from waffle.testutils import override_flag

from cl.audio.factories import AudioWithParentsFactory
from cl.lib.test_helpers import SimpleUserDataMixin
from cl.simple_pages.forms import ContactForm
from cl.tests.cases import SimpleTestCase, TestCase


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
        """Do we reject it if people put a phone number in the phone_number
        field?

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
        """Make sure a page has a valid HTML title"""
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

        :param reverse_param: Params that can be sent to Django's reverse
        function to get a URL path.
        :return: The response object.
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


class SimplePagesTest(PageLoadTestMixin, SimpleUserDataMixin, TestCase):
    async def test_simple_pages(self) -> None:
        """Do all the simple pages load properly?"""
        reverse_params: list[dict[str, Any]] = [
            # Coverage
            {"viewname": "coverage"},
            {"viewname": "coverage_fds"},
            {"viewname": "coverage_recap"},
            {"viewname": "coverage_oa"},
            {"viewname": "coverage_scotus"},
            {"viewname": "coverage_texas"},
            # Info pages
            {"viewname": "faq"},
            {"viewname": "feeds_info"},
            {"viewname": "robots"},
            # Contact
            {"viewname": "contact"},
            {"viewname": "contact_thanks"},
            # Help pages
            {"viewname": "help_home"},
            {"viewname": "alert_help"},
            {"viewname": "delete_help"},
            {"viewname": "markdown_help"},
            {"viewname": "advanced_search"},
            {"viewname": "recap_email_help"},
            {"viewname": "broken_email_help"},
            {"viewname": "citegeist_help"},
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

    async def test_oa_minute_count_in_the_coverage_page(self) -> None:
        "is the minute count rounded in the coverage page?"
        cache.delete("coverage-data-v3")
        await sync_to_async(AudioWithParentsFactory)(duration=250)
        r = await self.async_client.get(reverse("coverage"))
        self.assertIn("4 minutes of recordings.", r.content.decode())
        self.assertIn(
            "with 4 minutes of recordings (and counting).", r.content.decode()
        )


@override_flag("use_new_design", True)
@override_settings(WAFFLE_CACHE_PREFIX="test_v2_register_waffle")
class V2PagesRegisterTest(PageLoadTestMixin, SimpleUserDataMixin, TestCase):
    """Registry of pages with v2 (redesigned) templates.

    Adding a page here is part of the definition of done for a
    redesigned template. The homepage is excluded — it has dedicated
    tests in cl/search/tests/test_v2_pages.py.
    """

    V2_PAGES: list[tuple[dict[str, Any], str]] = [
        # Help pages — (reverse_param, expected v2 template)
        ({"viewname": "help_home"}, "v2_help/index.html"),
        ({"viewname": "coverage"}, "v2_help/coverage.html"),
        ({"viewname": "coverage_fds"}, "v2_help/coverage_fds.html"),
        ({"viewname": "coverage_oa"}, "v2_help/coverage_oa.html"),
        ({"viewname": "coverage_recap"}, "v2_help/coverage_recap.html"),
        ({"viewname": "coverage_scotus"}, "v2_help/coverage_scotus.html"),
        ({"viewname": "coverage_texas"}, "v2_help/coverage_texas.html"),
        ({"viewname": "alert_help"}, "v2_help/alert_help.html"),
        ({"viewname": "tag_notes_help"}, "v2_help/tags_help.html"),
        ({"viewname": "recap_email_help"}, "v2_help/recap_email_help.html"),
        ({"viewname": "markdown_help"}, "v2_help/markdown_help.html"),
        # Info pages
        ({"viewname": "citegeist_help"}, "v2_citegeist.html"),
        ({"viewname": "components"}, "v2_components.html"),
    ]

    async def test_v2_pages(self) -> None:
        """Do all registered v2 pages load properly with the redesign flag?"""
        for reverse_param, v2_template in self.V2_PAGES:
            with self.subTest(
                "Checking v2 page", reverse_params=reverse_param
            ):
                r = await self.assert_page_loads_ok(reverse_param)
                self.assertTemplateUsed(r, v2_template)


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
