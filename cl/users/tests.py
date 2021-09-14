from datetime import timedelta

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.timezone import now
from rest_framework.status import HTTP_200_OK
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator

from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import LiveServerTestCase, TestCase
from cl.users.models import UserProfile


class UserTest(LiveServerTestCase):
    fixtures = ["authtest_data.json"]

    def test_simple_auth_urls_GET(self) -> None:
        """Can we at least GET all the basic auth URLs?"""
        reverse_names = [
            "sign-in",
            "password_reset",
            "password_reset_done",
            "password_reset_complete",
            "email_confirmation_request",
            "email_confirm_success",
        ]
        for reverse_name in reverse_names:
            path = reverse(reverse_name)
            r = self.client.get(path)
            self.assertEqual(
                r.status_code,
                HTTP_200_OK,
                msg="Got wrong status code for page at: {path}. "
                "Status Code: {code}".format(path=path, code=r.status_code),
            )

    def test_creating_a_new_user(self) -> None:
        """Can we register a new user in the front end?"""
        params = {
            "username": "pan",
            "email": "pan@courtlistener.com",
            "password1": "test_creating_a_new_user",
            "password2": "test_creating_a_new_user",
            "first_name": "dora",
            "last_name": "☠☠☠☠☠☠☠☠☠☠☠",
            "skip_me_if_alive": "",
            "consent": True,
        }
        response = self.client.post(
            f"{self.live_server_url}{reverse('register')}",
            params,
            follow=True,
        )
        self.assertRedirects(
            response,
            f"{reverse('register_success')}"
            f"?next=/&email=pan%40courtlistener.com",
        )

    def test_redirects(self) -> None:
        """Do we allow good redirects while banning bad ones?"""
        next_params = [
            # No open redirects (to a domain outside CL)
            ("https://evil.com&email=e%40e.net", True),
            # No javascript (!)
            ("javascript:confirm(document.domain)", True),
            # No spaces
            ("/test test", True),
            # A safe redirect
            (reverse("faq"), False),
            # CRLF injection attack
            (
                "/%0d/evil.com/&email=Your+Account+still+in+maintenance,please+click+Return+below",
                True,
            ),
            # XSS vulnerabilities
            (
                "register/success/?next=java%0d%0ascript%0d%0a:alert(document.cookie)&email=Reflected+XSS+here",
                True,
            ),
        ]
        for next_param, is_evil in next_params:
            bad_url = "{host}{path}?next={next}".format(
                host=self.live_server_url,
                path=reverse("register_success"),
                next=next_param,
            )
            response = self.client.get(bad_url)
            with self.subTest("Checking redirect", url=bad_url):
                if is_evil:
                    self.assertNotIn(
                        next_param,
                        response.content.decode(),
                        msg="'%s' found in HTML of response. This suggests it was "
                        "not cleaned by the sanitize_redirection function."
                        % next_param,
                    )
                else:
                    self.assertIn(
                        next_param,
                        response.content.decode(),
                        msg="'%s' not found in HTML of response. This suggests it "
                        "was sanitized when it should not have been."
                        % next_param,
                    )

    def test_signing_in(self) -> None:
        """Can we create a user on the backend then sign them in"""
        params = {
            "username": "pandora",
            "password": "password",
        }
        r = self.client.post(reverse("sign-in"), params, follow=True)
        self.assertRedirects(r, "/")

    def test_confirming_an_email_address(self) -> None:
        """Tests whether we can confirm the case where an email is associated
        with a single account.
        """
        # Update the expiration since the fixture has one some time ago.
        u = UserProfile.objects.get(pk=1002)
        u.key_expires = now() + timedelta(days=2)
        u.save()

        r = self.client.get(
            reverse(
                "email_confirm",
                args=["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
            )
        )
        self.assertEqual(
            200,
            r.status_code,
            msg="Did not get 200 code when activating account. "
            "Instead got %s" % r.status_code,
        )
        self.assertIn(
            "has been confirmed",
            r.content.decode(),
            msg="Test string not found in response.content",
        )

    def test_confirming_an_email_when_it_is_associated_with_multiple_accounts(
        self,
    ) -> None:
        """Test the trickier case when an email is associated with many accounts"""
        # Update the accounts to have keys that are not expired.
        (
            UserProfile.objects.filter(pk__in=[1003, 1004, 1005]).update(
                key_expires=now() + timedelta(days=2)
            )
        )
        r = self.client.get(
            reverse(
                "email_confirm",
                args=["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaab"],
            )
        )
        self.assertIn(
            "has been confirmed",
            r.content.decode(),
            msg="Test string not found in response.content",
        )
        self.assertEqual(
            200,
            r.status_code,
            msg="Did not get 200 code when activating account. "
            "Instead got %s" % r.status_code,
        )
        ups = UserProfile.objects.filter(pk__in=(3, 4, 5))
        for up in ups:
            self.assertTrue(up.email_confirmed)


class ProfileTest(TestCase):
    fixtures = ["authtest_data.json"]

    def test_api_page_with_data(self) -> None:
        """Can we access the API stats page after the API has been used?"""
        # Get the page anonymously to populate the stats with anon data
        self.client.get(reverse("audio-list", kwargs={"version": "v3"}))

        # Log in, get the API again, and then load the profile page
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        self.client.get(reverse("audio-list", kwargs={"version": "v3"}))

        # Now get the API page
        r = self.client.get(reverse("view_api"))
        self.assertEqual(r.status_code, HTTP_200_OK)

    def test_deleting_your_account(self) -> None:
        """Can we delete an account properly?"""
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        response = self.client.post(reverse("delete_account"), follow=True)
        self.assertRedirects(
            response,
            reverse("delete_profile_done"),
        )

    def test_generate_recap_email_with_non_email_username(self) -> None:
        user_profile = UserProfile.objects.get(
            recap_email="pandora@recap.email"
        )
        self.assertEqual(user_profile.user.pk, 1001)

    def test_generate_recap_email_with_email_username(self) -> None:
        user_profile = UserProfile.objects.get(
            recap_email="pandora.gmail.com@recap.email"
        )
        self.assertEqual(user_profile.user.pk, 1006)


class DisposableEmailTest(TestCase):
    fixtures = ["authtest_data.json"]
    """
    Tests for issue #724 to block people with bad disposable email addresses.

    https://github.com/freelawproject/courtlistener/issues/724
    """

    bad_domain = "yopmail.com"
    user = "Aamon"
    bad_email = f"{user}@{bad_domain}"

    def setUp(self) -> None:
        self.client = Client()

    def test_can_i_create_account_with_bad_email_address(self) -> None:
        """Is an error thrown if we try to use a banned email address?"""
        r = self.client.post(
            reverse("register"),
            {
                "username": "aamon",
                "email": self.bad_email,
                "password1": "a",
                "password2": "a",
                "first_name": "Aamon",
                "last_name": "Marquis of Hell",
                "skip_me_if_alive": "",
            },
        )
        self.assertIn(
            f"{self.bad_domain} is a blocked email provider",
            r.content.decode(),
        )

    def test_can_i_change_to_bad_email_address(self) -> None:
        """Is an error thrown if we try to change to a bad email address?"""
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        r = self.client.post(
            reverse("view_settings"),
            {"email": self.bad_email},
            follow=True,
        )
        self.assertIn(
            f"{self.bad_domain} is a blocked email provider",
            r.content.decode(),
        )


class LiveUserTest(BaseSeleniumTest):
    fixtures = ["authtest_data.json"]

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_reset_password_using_the_HTML(self) -> None:
        """Can we use the HTML form to send a reset email?

        This test checks that the email goes out and that the status code
        returned is valid.
        """
        self.browser.get(f"{self.live_server_url}{reverse('password_reset')}")
        email_input = self.browser.find_element(By.NAME, "email")
        email_input.send_keys("pandora@courtlistener.com")
        email_input.submit()

        # self.selenium.save_screenshot('/home/mlissner/phantom.png')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            self.browser.current_url,
            f"{self.live_server_url}{reverse('password_reset_done')}",
        )

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_set_password_using_the_HTML(self) -> None:
        """Can we reset our password after generating a confirmation link?"""
        # Generate a token and use it to visit a generated reset URL
        up = UserProfile.objects.get(pk=1001)
        token = default_token_generator.make_token(up.user)
        url = "{host}{path}".format(
            host=self.live_server_url,
            path=reverse(
                "confirm_password",
                kwargs={
                    "uidb64": urlsafe_base64_encode(str(up.user.pk).encode()),
                    "token": token,
                },
            ),
        )
        self.browser.get(url)
        # self.selenium.save_screenshot('/home/mlissner/phantom.png')

        self.assertIn("Enter New Password", self.browser.page_source)

        # Next, change the user's password and submit the form.
        pwd1 = self.browser.find_element(By.NAME, "new_password1")
        pwd1.send_keys("reallylonghardpassword")
        pwd2 = self.browser.find_element(By.NAME, "new_password2")
        pwd2.send_keys("reallylonghardpassword")
        pwd2.submit()

        self.assertEqual(
            self.browser.current_url,
            f"{self.live_server_url}{reverse('password_reset_complete')}",
        )
