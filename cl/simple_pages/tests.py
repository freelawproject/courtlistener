from django.core import mail
from django.test import TestCase
from django.urls import reverse
from lxml.html import fromstring
from rest_framework.status import HTTP_200_OK, HTTP_302_FOUND


class ContactTest(TestCase):
    fixtures = ["authtest_data.json"]
    test_msg = {
        "name": "pandora",
        "phone_number": "asdf",
        "message": "123456789012345678901",
        "email": "pandora@box.com",
        "skip_me_if_alive": "",
    }

    def test_multiple_requests_request(self):
        """Is state persisted in the contact form?

        The contact form is abstracted in a way that it can have peculiar
        behavior when called multiple times. This test makes sure that that
        behavior does not regress.
        """
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        self.client.get(reverse("contact"))
        self.client.logout()

        # Now, as an anonymous user, we get the page again. If the bug is
        # resolved, we should not see anything about the previously logged-in
        # user, pandora.
        r = self.client.get(reverse("contact"))
        self.assertNotIn("pandora", r.content.decode())

    def test_contact_logged_in(self):
        """Can we use the contact form to send a message when logged in?"""
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        response = self.client.post(reverse("contact"), self.test_msg)
        self.assertEqual(response.status_code, HTTP_302_FOUND)
        self.assertEqual(len(mail.outbox), 1)

    def test_contact_logged_out(self):
        """Can we use the contact form to send a message when logged out?"""
        response = self.client.post(reverse("contact"), self.test_msg)
        self.assertEqual(response.status_code, HTTP_302_FOUND)
        self.assertEqual(len(mail.outbox), 1)

    def test_contact_unicode(self):
        """Can unicode be used when contacting us?"""
        msg = self.test_msg.copy()
        msg["message"] = (
            "Possible ideas and thoughts are vast in number. A distinct word "
            "for every distinct idea and thought would require a vast "
            "vocabulary. The problem in language is to express many ideas and "
            "thoughts with comparatively few words. — John Wesley Powell"
        )
        response = self.client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTP_302_FOUND)
        self.assertEqual(len(mail.outbox), 1)

    def test_spam_message_is_rejected(self):
        """Do we reject it if people put a phone number in the phone_number
        field?

        We should! The phone_number field is labeled as the Subject field in the
        UI. Anything putting a phone number in here is a bot to be rejected.
        """
        msg = self.test_msg.copy()
        msg["phone_number"] = "909-576-4123"
        response = self.client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTP_302_FOUND)
        self.assertEqual(len(mail.outbox), 0)

        # Number in middle of subject is OK!
        msg["phone_number"] = "asdf 909 asdf"
        response = self.client.post(reverse("contact"), msg)
        self.assertEqual(response.status_code, HTTP_302_FOUND)
        self.assertEqual(len(mail.outbox), 1)


class SimplePagesTest(TestCase):
    fixtures = ["authtest_data.json"]

    def assert_page_title_in_html(self, content: str) -> None:
        """Make sure a page has a valid HTML title"""
        print("Checking for HTML title tag....", end="")
        html_tree = fromstring(content)
        title = html_tree.xpath("//title/text()")
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
        print("✓")

    def assert_page_loads_ok(self, reverse_param: dict) -> None:
        """Does a page load properly?

        :param reverse_param: Params that can be sent to Django's reverse
        function to get a URL path.
        :return: None
        """
        path = reverse(**reverse_param)
        print("Testing basic load of: {path}...".format(path=path), end="")
        r = self.client.get(path)
        self.assertEqual(
            r.status_code,
            HTTP_200_OK,
            msg="Got wrong status code for page at: {path}\n  args: "
            "{args}\n  kwargs: {kwargs}\n  Status Code: {code}".format(
                path=path,
                args=reverse_param.get("args", []),
                kwargs=reverse_param.get("kwargs", {}),
                code=r.status_code,
            ),
        )
        print("✓")
        is_html = "text/html" in r["content-type"]
        if r["content-type"] and is_html:
            self.assert_page_title_in_html(r.content)

    def test_simple_pages(self) -> None:
        """Do all the simple pages load properly?"""
        reverse_params = [
            {"viewname": "faq"},
            {"viewname": "coverage"},
            {"viewname": "feeds_info"},
            {"viewname": "contribute"},
            {"viewname": "contact"},
            {"viewname": "contact_thanks"},
            {"viewname": "alert_help"},
            {"viewname": "delete_help"},
            {"viewname": "markdown_help"},
            {"viewname": "advanced_search"},
            {"viewname": "old_terms", "args": ["1"]},
            {"viewname": "old_terms", "args": ["2"]},
            {"viewname": "terms"},
            {"viewname": "robots"},
        ]
        for reverse_param in reverse_params:
            self.assert_page_loads_ok(reverse_param)

    def test_profile_urls(self) -> None:
        """Do all of the profile URLs load properly?"""
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        reverse_params = [
            {"viewname": "view_settings"},
            {"viewname": "profile_favorites"},
            {"viewname": "profile_alerts"},
            {"viewname": "view_visualizations"},
            {"viewname": "view_deleted_visualizations"},
            {"viewname": "password_change"},
            {"viewname": "delete_account"},
            {"viewname": "take_out"},
            {"viewname": "profile_donations"},
            {"viewname": "view_api"},
        ]
        for reverse_param in reverse_params:
            self.assert_page_loads_ok(reverse_param)
