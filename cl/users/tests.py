import json
import os
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.timezone import now
from django_ses import signals
from rest_framework.status import HTTP_200_OK
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator

from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import LiveServerTestCase, TestCase
from cl.users.models import BackoffEvent, EmailFlag, UserProfile


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

    def test_generate_recap_email_username_lowercase(self) -> None:
        user_profile = UserProfile.objects.get(
            recap_email="test.user@recap.email"
        )
        self.assertEqual(user_profile.user.pk, 1007)


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


class SNSWebhookTest(TestCase):
    def setUp(self) -> None:
        test_dir = os.path.join(
            settings.INSTALL_ROOT, "cl", "users", "test_assets"
        )
        with open(os.path.join(test_dir, "general_soft_bounce.json")) as file:
            self.soft_bounce_asset = json.loads(file.read())
        with open(os.path.join(test_dir, "msg_large_bounce.json")) as file:
            self.soft_bounce_msg_large_asset = json.loads(file.read())
        with open(os.path.join(test_dir, "cnt_rejected_bounce.json")) as file:
            self.soft_bounce_cnt_rejected_asset = json.loads(file.read())
        with open(os.path.join(test_dir, "hard_bounce.json")) as file:
            self.hard_bounce_asset = json.loads(file.read())
        with open(os.path.join(test_dir, "complaint.json")) as file:
            self.complaint_asset = json.loads(file.read())
        with open(os.path.join(test_dir, "delivery.json")) as file:
            self.delivery_asset = json.loads(file.read())

    def send_signal(self, test_asset, event_name, signal) -> None:
        """Function to dispatch signal that mocks a SNS notification event
        :param test_asset: the json object that contains notification
        :param event_name: the signal event name
        :param signal: the signal corresponding to the event
        :return: None
        """
        # Prepare parameters
        raw = json.dumps(test_asset)
        notification = json.loads(raw)
        message = json.loads(notification["Message"])
        mail_obj = message.get("mail")
        event_obj = message.get(event_name, {})

        # Send signal
        signal_kwargs = dict(
            sender=self,
            mail_obj=mail_obj,
            raw_message=raw,
        )
        signal_kwargs["%s_obj" % event_name] = event_obj
        signal.send(**signal_kwargs)

    @mock.patch("cl.users.models.handle_hard_bounce")
    def test_hard_bounce_signal(self, mock_hard_bounce) -> None:
        """This test checks if handle_hard_bounce function is called
        when a hard bounce event is received
        """
        # Trigger a hard bounce event
        self.send_signal(
            self.hard_bounce_asset, "bounce", signals.bounce_received
        )
        # Check if handle_hard_bounce is called
        mock_hard_bounce.assert_called()

    @mock.patch("cl.users.models.handle_soft_bounce")
    def test_soft_bounce_signal(self, mock_soft_bounce) -> None:
        """This test checks if handle_soft_bounce function is called
        when a soft bounce event is received
        """
        # Trigger a soft bounce event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        # Check if handle_soft_bounce is called
        mock_soft_bounce.assert_called()

    @mock.patch("cl.users.models.handle_complaint")
    def test_complaint_signal(self, mock_complaint) -> None:
        """This test checks if handle_complaint function is called
        when a complaint event is received
        """
        # Trigger a complaint event
        self.send_signal(
            self.complaint_asset, "complaint", signals.complaint_received
        )
        # Check if handle_complaint is called
        mock_complaint.assert_called()

    @mock.patch("cl.users.models.handle_delivery")
    def test_delivery_signal(self, mock_delivery) -> None:
        """This test checks if handle_delivery function is called
        when a delivery event is received
        """
        # Trigger a delivery event
        self.send_signal(
            self.delivery_asset, "delivery", signals.delivery_received
        )

        # Check if handle_delivery is called
        mock_delivery.assert_called()

    def test_handle_soft_bounce_create_small_only(self) -> None:
        """This test checks if a small_email_only flag is created for
        an email address if it doesn't exist previously when a
        small_email_only soft bounce is received
        """

        email_flag_exists = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type="flag",
            flag="small_email_only",
        ).exists()
        self.assertEqual(email_flag_exists, False)

        # Trigger a small_email_only soft bounce
        self.send_signal(
            self.soft_bounce_msg_large_asset, "bounce", signals.bounce_received
        )

        email_flag_exists = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type="flag",
            flag="small_email_only",
        ).exists()
        # Check if small_email_only was created
        self.assertEqual(email_flag_exists, True)

    def test_handle_soft_bounce_small_only_exist(self) -> None:
        """This test checks if a small_email_only flag is not created for
        an email address if it exists previously when a
        small_email_only soft bounce is received
        """
        # Create a small_email_only flag
        email_flag_count = EmailFlag.objects.create(
            email_address="bounce@simulator.amazonses.com",
            flag_type="flag",
            flag="small_email_only",
            reason="MessageTooLarge",
        )
        email_flag_count = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type="flag",
            flag="small_email_only",
        ).count()
        self.assertEqual(email_flag_count, 1)

        # Trigger a small_email_only soft bounce
        self.send_signal(
            self.soft_bounce_msg_large_asset, "bounce", signals.bounce_received
        )

        email_flag_count = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type="flag",
            flag="small_email_only",
        ).count()

        # Check if new small_email_only was not created
        self.assertEqual(email_flag_count, 1)

    @mock.patch("cl.users.models.logging")
    def test_handle_soft_bounce_unexpected(self, mock_logging) -> None:
        """This test checks if a warning is logged when a
        unexpected bounceSubType event is received
        """
        # Trigger a content_rejected event
        self.send_signal(
            self.soft_bounce_cnt_rejected_asset,
            "bounce",
            signals.bounce_received,
        )
        # Check if warning is logged
        warning_part_one = "Unexpected ContentRejected soft bounce for "
        warning_part_two = "bounce@simulator.amazonses.com"
        mock_logging.warning.assert_called_with(
            f"{warning_part_one}{warning_part_two}"
        )

    def test_handle_soft_bounce_create_back_off(self) -> None:
        """This test checks if a back_off event is created for
        an email address if it doesn't exist previously when a
        backoff type soft bounce is received
        """
        email_backoff_exists = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        ).exists()

        self.assertEqual(email_backoff_exists, False)
        # Trigger a backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )

        email_backoff_exists = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        ).exists()
        # Check if backoff event was created
        self.assertEqual(email_backoff_exists, True)

    def test_handle_soft_bounce_waiting_back_off(self) -> None:
        """This test checks if a back_off event exists for
        an email address and is under waiting period,
        backoff event is not updated
        """
        # Trigger first backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_backoff_event = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        email_backoff_exists = email_backoff_event.exists()
        # Check if backoff event was created
        self.assertEqual(email_backoff_exists, True)

        if email_backoff_exists:
            # Store parameters from backoff event
            retry_counter_before = email_backoff_event[0].retry_counter
            next_retry_date_before = email_backoff_event[0].next_retry_date

        # Trigger second backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )

        email_backoff_event_after = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        # Store parameters after second backoff notification event
        retry_counter_after = email_backoff_event_after[0].retry_counter
        next_retry_date_after = email_backoff_event_after[0].next_retry_date

        # Check parameters were not updated
        self.assertEqual(retry_counter_before, retry_counter_after)
        self.assertEqual(next_retry_date_before, next_retry_date_after)

    def test_handle_soft_bounce_not_waiting_back_off(self) -> None:
        """This test checks if a back_off event exists for
        an email address and is not under waiting period and,
        max_retry has not been reached, backoff event is updated
        """
        # Trigger first backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        # Update next_retry_date to expire waiting time
        BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        ).update(next_retry_date=now() - timedelta(hours=3))

        email_ban_event = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        # Store parameters after first backoff event
        retry_counter_before = email_ban_event[0].retry_counter
        next_retry_date_before = email_ban_event[0].next_retry_date
        # Trigger second backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban_event_after = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        # Store parameters after second backoff notification event
        retry_counter_after = email_ban_event_after[0].retry_counter
        next_retry_date_after = email_ban_event_after[0].next_retry_date

        # Check parameters were updated
        self.assertNotEqual(retry_counter_before, retry_counter_after)
        self.assertNotEqual(next_retry_date_before, next_retry_date_after)

    def test_handle_soft_bounce_not_max_retry_reached(self) -> None:
        """This test checks if a back_off event exists for
        an email address and is not under waiting period and,
        max_retry has been reached, email address is banned
        """
        # Trigger first backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban_exist = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type="ban",
        ).exists()
        # Check email address is not banned
        self.assertEqual(email_ban_exist, False)

        # Update next_retry_date to expire waiting time and retry_counter to
        # reach max_retry_counter
        BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        ).update(next_retry_date=now() - timedelta(hours=3), retry_counter=5)
        # Trigger second backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban_exist = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type="ban",
        ).exists()
        # Check email address is now banned
        self.assertEqual(email_ban_exist, True)

    def test_handle_soft_bounce_max_retry_reached(self) -> None:
        """This test checks if the exponential waiting period
        is computed properly
        """
        # Trigger first backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        # Update next_retry_date to expire waiting time and retry_counter to 4
        BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        ).update(next_retry_date=now() - timedelta(hours=3), retry_counter=4)

        email_ban_event = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        # Store parameter after backoff event update
        retry_counter_before = email_ban_event[0].retry_counter
        # Trigger second backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban_event_after = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        # Store parametes after second backoff event update
        retry_counter_after = email_ban_event_after[0].retry_counter
        next_retry_date_after = email_ban_event_after[0].next_retry_date

        # Hours expected for the final backoff waiting period
        expected_waiting_period = 64

        # Obtain waiting period in hours after backoff notification
        waiting_period = next_retry_date_after - now()
        actual_waiting_period = round(waiting_period.total_seconds() / 3600)

        # Check retry counter is updated
        self.assertNotEqual(retry_counter_before, retry_counter_after)
        # Check expected waiting period equals to computed waiting period
        self.assertEqual(expected_waiting_period, actual_waiting_period)
