import json
from datetime import timedelta
from pathlib import Path
from time import time
from unittest import mock

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives, send_mail
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.timezone import now
from django_ses import signals
from rest_framework.status import HTTP_200_OK
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator

from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import LiveServerTestCase, TestCase
from cl.users.email_handlers import (
    add_bcc_random,
    compose_stored_message,
    get_email_body,
    normalize_addresses,
)
from cl.users.factories import UserFactory
from cl.users.models import (
    EMAIL_NOTIFICATIONS,
    OBJECT_TYPES,
    STATUS_TYPES,
    BackoffEvent,
    EmailFlag,
    EmailSent,
    FailedEmail,
    UserProfile,
)


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
    @classmethod
    def setUpTestData(cls):
        test_dir = Path(settings.INSTALL_ROOT) / "cl" / "users" / "test_assets"
        with (
            open(
                test_dir / "general_soft_bounce.json", encoding="utf-8"
            ) as general_soft_bounce,
            open(
                test_dir / "msg_large_bounce.json", encoding="utf-8"
            ) as msg_large_bounce,
            open(
                test_dir / "cnt_rejected_bounce.json", encoding="utf-8"
            ) as cnt_rejected_bounce,
            open(
                test_dir / "hard_bounce.json", encoding="utf-8"
            ) as hard_bounce,
            open(test_dir / "complaint.json", encoding="utf-8") as complaint,
            open(test_dir / "delivery.json", encoding="utf-8") as delivery,
            open(
                test_dir / "suppressed_bounce.json", encoding="utf-8"
            ) as suppressed_bounce,
        ):
            cls.soft_bounce_asset = json.load(general_soft_bounce)
            cls.soft_bounce_msg_large_asset = json.load(msg_large_bounce)
            cls.soft_bounce_cnt_rejected_asset = json.load(cnt_rejected_bounce)
            cls.hard_bounce_asset = json.load(hard_bounce)
            cls.complaint_asset = json.load(complaint)
            cls.delivery_asset = json.load(delivery)
            cls.suppressed_asset = json.load(suppressed_bounce)

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
        signal_kwargs[f"{event_name}_obj"] = event_obj
        signal.send(**signal_kwargs)

    @mock.patch("cl.users.signals.handle_hard_bounce")
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

    @mock.patch("cl.users.signals.handle_soft_bounce")
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

    @mock.patch("cl.users.signals.handle_complaint")
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

    @mock.patch("cl.users.signals.handle_delivery")
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
            object_type=OBJECT_TYPES.FLAG,
            flag=EmailFlag.SMALL_ONLY,
        ).exists()
        self.assertEqual(email_flag_exists, False)

        # Trigger a small_email_only soft bounce
        self.send_signal(
            self.soft_bounce_msg_large_asset, "bounce", signals.bounce_received
        )

        email_flag_exists = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.FLAG,
            flag=EmailFlag.SMALL_ONLY,
        ).exists()
        # Check if small_email_only was created
        self.assertEqual(email_flag_exists, True)

        # Trigger another small_email_only event to check if
        # no new ban register is created
        self.send_signal(
            self.soft_bounce_msg_large_asset, "bounce", signals.bounce_received
        )
        email_flag = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.FLAG,
            flag=EmailFlag.SMALL_ONLY,
        )

        # Checks no new ban object is created for this email address
        self.assertEqual(email_flag.count(), 1)
        self.assertEqual(email_flag[0].flag, EmailFlag.SMALL_ONLY)

    def test_handle_soft_bounce_small_only_exist(self) -> None:
        """This test checks if a small_email_only flag is not created for
        an email address if it exists previously when a
        small_email_only soft bounce is received
        """
        # Create a small_email_only flag
        email_flag_count = EmailFlag.objects.create(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.FLAG,
            flag=EmailFlag.SMALL_ONLY,
            event_sub_type=EMAIL_NOTIFICATIONS.MESSAGE_TOO_LARGE,
        )
        email_flag_count = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.FLAG,
            flag=EmailFlag.SMALL_ONLY,
        ).count()
        self.assertEqual(email_flag_count, 1)

        # Trigger a small_email_only soft bounce
        self.send_signal(
            self.soft_bounce_msg_large_asset, "bounce", signals.bounce_received
        )

        email_flag_count = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.FLAG,
            flag=EmailFlag.SMALL_ONLY,
        ).count()

        # Check if new small_email_only was not created
        self.assertEqual(email_flag_count, 1)

    @mock.patch("cl.users.email_handlers.logging")
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

        email_backoff = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        # Store parameters after first backoff event
        retry_counter_before = email_backoff[0].retry_counter
        next_retry_date_before = email_backoff[0].next_retry_date
        # Trigger second backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_backoff_after = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        # Store parameters after second backoff notification event
        retry_counter_after = email_backoff_after[0].retry_counter
        next_retry_date_after = email_backoff_after[0].next_retry_date

        # Check parameters were updated
        self.assertNotEqual(retry_counter_before, retry_counter_after)
        self.assertNotEqual(next_retry_date_before, next_retry_date_after)

    def test_handle_soft_bounce_max_retry_reached(self) -> None:
        """This test checks if a back_off event exists for
        an email address and if is not under waiting period and if
        max_retry has been reached, email address is banned
        """
        # Trigger first backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban_exist = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
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
            object_type=OBJECT_TYPES.BAN,
        ).exists()
        # Check email address is now banned
        self.assertEqual(email_ban_exist, True)

        # Trigger another notification event to check
        # no new ban register is created
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )

        # Checks no new ban object is created for this email address
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].event_sub_type, EMAIL_NOTIFICATIONS.GENERAL
        )

    def test_handle_soft_bounce_compute_waiting_period(self) -> None:
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

    @mock.patch("cl.users.email_handlers.logging")
    def test_handle_hard_bounce_unexpected(self, mock_logging) -> None:
        """This test checks if a warning is logged and email address is banned
        when an unexpected hard bounceSubType event is received.
        Also checks that if an email address is previously banned avoid
        creating a new ban object for that email address
        """
        # Trigger a suppressed_asset event
        self.send_signal(
            self.suppressed_asset,
            "bounce",
            signals.bounce_received,
        )
        # Check if a warning is logged
        warning_part_one = "Unexpected Suppressed hard bounce for "
        warning_part_two = "bounce@simulator.amazonses.com"
        mock_logging.warning.assert_called_with(
            f"{warning_part_one}{warning_part_two}"
        )
        email_ban_count = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        ).count()

        # Check if email address is now banned
        self.assertEqual(email_ban_count, 1)

        # Trigger another suppressed_asset event
        self.send_signal(
            self.suppressed_asset,
            "bounce",
            signals.bounce_received,
        )

        email_ban_count = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        ).count()

        # Check no additional email ban object is created
        self.assertEqual(email_ban_count, 1)

    def test_handle_hard_bounce(self) -> None:
        """This test checks if an email address is banned
        when a hard bounce event is received.
        Also checks that if an email address is previously banned avoid to
        create a new ban register for that email address
        """
        # Trigger a hard_bounce event
        self.send_signal(
            self.hard_bounce_asset,
            "bounce",
            signals.bounce_received,
        )

        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )

        # Checks email address is now banned
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].event_sub_type, EMAIL_NOTIFICATIONS.GENERAL
        )

        # Trigger another hard_bounce event
        self.send_signal(
            self.suppressed_asset,
            "bounce",
            signals.bounce_received,
        )

        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )

        # Check no additional email ban object is created
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].event_sub_type, EMAIL_NOTIFICATIONS.GENERAL
        )

    def test_handle_complaint(self) -> None:
        """This test checks if an email address is banned
        when a complaint event is received.
        Also checks that if an email address is previously banned avoid to
        create a new ban register for that email address
        """

        # Trigger a complaint event
        self.send_signal(
            self.complaint_asset, "complaint", signals.complaint_received
        )

        email_ban = EmailFlag.objects.filter(
            email_address="complaint@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )

        # Checks email address is now banned
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].event_sub_type, EMAIL_NOTIFICATIONS.COMPLAINT
        )

        # Trigger another complaint event
        self.send_signal(
            self.complaint_asset, "complaint", signals.complaint_received
        )

        email_ban = EmailFlag.objects.filter(
            email_address="complaint@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )

        # Check no additional email ban object is created
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].event_sub_type, EMAIL_NOTIFICATIONS.COMPLAINT
        )

    @mock.patch("cl.users.email_handlers.schedule_failed_email")
    def test_handle_delivery(self, mock_schedule) -> None:
        """This test checks if a delivery notification is received
        and exists a previous Backoffevent it's deleted and
        schedule_failed_email function is called
        """
        # Trigger soft bounce event to create backoff event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_backoff_event = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        email_backoff_exists = email_backoff_event.exists()
        # Check if backoff event was created
        self.assertEqual(email_backoff_exists, True)

        # Trigger a delivery event
        self.send_signal(
            self.delivery_asset, "delivery", signals.delivery_received
        )

        email_backoff_event = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        email_backoff_exists = email_backoff_event.exists()

        # Check if backoff event was deleted
        self.assertEqual(email_backoff_exists, False)

        # Check if schedule_failed_email is called
        mock_schedule.assert_called()

    def test_update_ban_object(self) -> None:
        """This test checks if an email ban object is updated when receiving
        a new ban notification, e.g: complaint -> hard bounce
        """

        # Trigger a complaint event
        self.send_signal(
            self.complaint_asset, "complaint", signals.complaint_received
        )

        email_ban = EmailFlag.objects.filter(
            email_address="complaint@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )

        # Checks email address is now banned due to a complaint
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].event_sub_type, EMAIL_NOTIFICATIONS.COMPLAINT
        )

        # Trigger a hard_bounce event
        self.send_signal(
            self.hard_bounce_asset,
            "bounce",
            signals.bounce_received,
        )

        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )

        # Checks email ban is updated with the hard bounce subtype
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].event_sub_type, EMAIL_NOTIFICATIONS.GENERAL
        )


@override_settings(
    EMAIL_BACKEND="cl.lib.email_backends.EmailBackend",
    BASE_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_BCC_COPY_RATE=0,
)
class CustomBackendEmailTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        test_dir = Path(settings.INSTALL_ROOT) / "cl" / "users" / "test_assets"
        with (
            open(
                test_dir / "hard_bounce.json", encoding="utf-8"
            ) as hard_bounce,
            open(
                test_dir / "general_soft_bounce.json", encoding="utf-8"
            ) as soft_bounce,
            open(
                test_dir / "general_soft_bounce_2.json", encoding="utf-8"
            ) as general_soft_bounce_2,
            open(
                test_dir / "msg_large_bounce.json", encoding="utf-8"
            ) as large_bounce,
            open(test_dir / "complaint.json", encoding="utf-8") as complaint,
        ):
            cls.hard_bounce_asset = json.load(hard_bounce)
            cls.soft_bounce_asset = json.load(soft_bounce)
            cls.soft_bounce_asset_2 = json.load(general_soft_bounce_2)
            cls.soft_bounce_msg_large_asset = json.load(large_bounce)
            cls.complaint_asset = json.load(complaint)

        cls.attachment_150 = test_dir / "file_sample_150kB.pdf"
        cls.attachment_500 = test_dir / "file_example_500kB.pdf"

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
        signal_kwargs[f"{event_name}_obj"] = event_obj
        signal.send(**signal_kwargs)

    def mock_send_failed_email(failed_pk, start):
        """This function mocks the send_failed_email function to avoid calling
        the celery task and avoid unxpected errors.
        """
        return None

    def test_send_mail_function(self) -> None:
        """This test checks if Django send_mail() works properly using the
        custom email backend, the email should be stored automatically.
        """
        send_mail(
            subject="This is the subject",
            message="Body goes here",
            html_message="<p>Body goes here</p>",
            from_email="testing@courtlistener.com",
            recipient_list=["success@simulator.amazonses.com"],
        )

        # Retrieve stored email and compare content
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(
            stored_email[0].to, ["success@simulator.amazonses.com"]
        )
        self.assertEqual(stored_email[0].plain_text, "Body goes here")
        self.assertEqual(stored_email[0].html_message, "<p>Body goes here</p>")

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)

        message_sent = mail.outbox[0]
        message = message_sent.message()

        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Verify if the email unique identifier "X-CL-ID" header was added
        self.assertTrue(message_sent.extra_headers["X-CL-ID"])
        # Compare body contents
        self.assertEqual(plaintext_body, "Body goes here")
        self.assertEqual(html_body, "<p>Body goes here</p>")

    def test_email_message_class(self) -> None:
        """This test checks if Django EmailMessage class works properly using
        the custom email backend, the email should be stored automatically.
        """

        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            ["success@simulator.amazonses.com"],
            ["bcc_success@simulator.amazonses.com"],
            cc=["cc_success@simulator.amazonses.com"],
            headers={"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
            reply_to=["reply_success@simulator.amazonses.com"],
        )

        email.send()

        # Retrieve stored email and compare content
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(
            stored_email[0].to, ["success@simulator.amazonses.com"]
        )
        self.assertEqual(stored_email[0].plain_text, "Body goes here")
        self.assertEqual(
            stored_email[0].bcc, ["bcc_success@simulator.amazonses.com"]
        )
        self.assertEqual(
            stored_email[0].cc, ["cc_success@simulator.amazonses.com"]
        )
        self.assertEqual(
            stored_email[0].reply_to, ["reply_success@simulator.amazonses.com"]
        )
        self.assertEqual(
            stored_email[0].headers, {"X-Entity-Ref-ID": "9598e6b0-d88c-488e"}
        )

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)

        message_sent = mail.outbox[0]
        message = message_sent.message()

        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Verify if the email unique identifier "X-CL-ID" header was added
        self.assertTrue(message_sent.extra_headers["X-CL-ID"])
        # Compare body contents, this message only has plain/text version
        self.assertEqual(plaintext_body, "Body goes here")
        self.assertEqual(html_body, "")

    def test_multialternative_email(self) -> None:
        """This test checks if Django EmailMultiAlternatives class works
        properly sending html and plain versions using the custom backend
        email,the email should be stored automatically.
        """

        msg = EmailMultiAlternatives(
            subject="This is the subject",
            body="Body goes here",
            from_email="testing@courtlistener.com",
            to=["success@simulator.amazonses.com"],
            bcc=["bcc_success@simulator.amazonses.com"],
            cc=["cc_success@simulator.amazonses.com"],
            headers={f"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )
        html = "<p>Body goes here</p>"
        msg.attach_alternative(html, "text/html")
        msg.send()

        # Retrieve stored email and compare content
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(
            stored_email[0].to, ["success@simulator.amazonses.com"]
        )
        self.assertEqual(stored_email[0].plain_text, "Body goes here")
        self.assertEqual(stored_email[0].html_message, "<p>Body goes here</p>")
        self.assertEqual(
            stored_email[0].bcc, ["bcc_success@simulator.amazonses.com"]
        )
        self.assertEqual(
            stored_email[0].cc, ["cc_success@simulator.amazonses.com"]
        )
        self.assertEqual(
            stored_email[0].headers, {"X-Entity-Ref-ID": "9598e6b0-d88c-488e"}
        )

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)

        message_sent = mail.outbox[0]
        message = message_sent.message()

        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Verify if the email unique identifier "X-CL-ID" header was added
        self.assertTrue(message_sent.extra_headers["X-CL-ID"])
        # Compare body contents, this message has a plain and html version
        self.assertEqual(plaintext_body, "Body goes here")
        self.assertEqual(html_body, "<p>Body goes here</p>")

    def test_multialternative_only_plain_email(self) -> None:
        """This test checks if Django EmailMultiAlternatives class works
        properly sending plain version using the custom backend
        email,the email should be stored automatically.
        """

        msg = EmailMultiAlternatives(
            subject="This is the subject",
            body="Body goes here",
            from_email="testing@courtlistener.com",
            to=["success@simulator.amazonses.com"],
            bcc=["bcc_success@simulator.amazonses.com"],
            cc=["cc_success@simulator.amazonses.com"],
            headers={f"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )
        msg.send()

        # Retrieve stored email and compare content
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(stored_email[0].plain_text, "Body goes here")
        self.assertEqual(stored_email[0].html_message, "")

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)

        message_sent = mail.outbox[0]
        message = message_sent.message()

        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Verify if the email unique identifier "X-CL-ID" header was added
        # and original headers are preserved
        self.assertTrue(message_sent.extra_headers["X-Entity-Ref-ID"])
        self.assertTrue(message_sent.extra_headers["X-CL-ID"])
        # Compare body contents, this message has only plain/text version
        self.assertEqual(plaintext_body, "Body goes here")
        self.assertEqual(html_body, "")

    def test_multialternative_only_html_email(self) -> None:
        """This test checks if Django EmailMultiAlternatives class works
        properly sending html version using the custom backend
        email,the email should be stored automatically.
        """

        msg = EmailMultiAlternatives(
            subject="This is the subject",
            body="<p>Body goes here</p>",
            from_email="testing@courtlistener.com",
            to=["success@simulator.amazonses.com"],
            bcc=["bcc_success@simulator.amazonses.com"],
            cc=["cc_success@simulator.amazonses.com"],
            headers={f"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )
        msg.content_subtype = "html"
        msg.send()

        # Retrieve stored email and compare content
        stored_email = EmailSent.objects.latest("id")
        self.assertEqual(stored_email.html_message, "<p>Body goes here</p>")
        self.assertEqual(stored_email.plain_text, "")

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)

        message_sent = mail.outbox[0]
        message = message_sent.message()
        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Verify if the email unique identifier "X-CL-ID" header was added
        self.assertTrue(message_sent.extra_headers["X-CL-ID"])
        # Compare body contents, this message has only html/text version
        self.assertEqual(plaintext_body, "")
        self.assertEqual(html_body, "<p>Body goes here</p>")

    def test_sending_email_with_attachment(self) -> None:
        """This test checks if Django EmailMessage class works
        properly sending a message with an attachment using the custom
        email backend.
        """
        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            ["success@simulator.amazonses.com"],
            ["bcc_success@simulator.amazonses.com"],
            cc=["cc_success@simulator.amazonses.com"],
            headers={"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )

        email.attach_file(self.attachment_150)
        email.send()

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]

        # Confirm the attachment is sent
        self.assertEqual(len(message_sent.attachments), 1)

    def test_link_user_to_email(self) -> None:
        """This test checks if a User is properly linked to a stored Email
        is created, we search for the user by email address if found it's
        assigned.
        """
        # Get user factory
        user_email = self.user

        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            [user_email.email],
            headers={"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )
        email.send()

        # Retrieve stored email and compare content
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(stored_email[0].user_id, user_email.id)

    def test_sending_to_banned_email(self) -> None:
        """This test checks if an email address is banned and we try to send
        it an email, the message is discarded and not stored.
        """

        # Trigger a hard_bounce event
        self.send_signal(
            self.hard_bounce_asset,
            "bounce",
            signals.bounce_received,
        )

        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )

        # Checks email address is now banned
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].event_sub_type, EMAIL_NOTIFICATIONS.GENERAL
        )

        send_mail(
            "Subject here",
            "Here is the message.",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
            fail_silently=False,
        )

        # Confirm if email is not sent
        self.assertEqual(len(mail.outbox), 0)

        # Confirm if email is not stored
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 0)

    @mock.patch(
        "cl.users.email_handlers.send_failed_email",
        side_effect=mock_send_failed_email,
    )
    def test_sending_email_within_back_off(self, mock_send_email) -> None:
        """This test checks if an email address is under a backoff waiting
        period and we try to send it an email, the message is stored but
        not sent.
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

        send_mail(
            "Subject here",
            "Here is the message.",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
            fail_silently=False,
        )

        # Confirm if email is stored
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)

        # Confirm if email is not sent
        self.assertEqual(len(mail.outbox), 0)

    def test_sending_small_only_email(self) -> None:
        """This test checks if an email address is flagged with a small email
        only flag and try to send an email with an attachment, the small email
        version is sent without attachment.
        """
        # Trigger a small_email_only soft bounce
        self.send_signal(
            self.soft_bounce_msg_large_asset, "bounce", signals.bounce_received
        )

        email_flag_exists = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.FLAG,
            flag=EmailFlag.SMALL_ONLY,
        ).exists()
        # Check if small_email_only flag was created
        self.assertEqual(email_flag_exists, True)

        email = EmailMultiAlternatives(
            subject="This is the subject",
            body="Body for attachment version",
            from_email="testing@courtlistener.com",
            to=["bounce@simulator.amazonses.com"],
            headers={f"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )

        html = "<p>Body for attachment version</p>"
        email.attach_alternative(html, "text/html")
        # When sending an email with an attachment is necessary to add a small
        # email body in case we need to send a small email only version.
        small_plain = "Body for small version"
        email.attach_alternative(small_plain, "text/plain_small")
        small_html = "<p>Body for small version</p>"
        email.attach_alternative(small_html, "text/html_small")
        # Attach file
        email.attach_file(self.attachment_150)
        email.send()

        # Retrieve stored email and compare content
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(
            stored_email[0].html_message, "<p>Body for small version</p>"
        )
        self.assertEqual(stored_email[0].plain_text, "Body for small version")

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]

        # Confirm not attachment is sent
        self.assertEqual(len(message_sent.attachments), 0)

        message = message_sent.message()

        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Confirm small email only version is sent
        self.assertEqual(plaintext_body, "Body for small version")
        self.assertEqual(html_body, "<p>Body for small version</p>")

    def test_sending_no_small_only_email(self) -> None:
        """This test checks if an email address is not flagged with a small
        email only flag and we try to send an email with an attachment, the
        normal email version is sent with its attachment, however, we store the
        small email version in case we need it in the future.
        """

        email = EmailMultiAlternatives(
            subject="This is the subject",
            body="Body for attachment version",
            from_email="testing@courtlistener.com",
            to=["bounce@simulator.amazonses.com"],
            headers={f"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )

        html = "<p>Body for attachment version</p>"
        email.attach_alternative(html, "text/html")
        # When sending an email with an attachment is necessary to add a small
        # email body in case we'll need to send a small email only version.
        small_plain = "Body for small version"
        email.attach_alternative(small_plain, "text/plain_small")
        small_html = "<p>Body for small version</p>"
        email.attach_alternative(small_html, "text/html_small")
        # Attach a file
        email.attach_file(self.attachment_150)
        email.send()

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]

        # Confirm the attachment is sent
        self.assertEqual(len(message_sent.attachments), 1)

        message = message_sent.message()

        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Confirm if normal email version is sent
        self.assertEqual(plaintext_body, "Body for attachment version")
        self.assertEqual(html_body, "<p>Body for attachment version</p>")

        # Retrieve stored email and compare content, small version should
        # be stored
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(
            stored_email[0].html_message, "<p>Body for small version</p>"
        )
        self.assertEqual(stored_email[0].plain_text, "Body for small version")

    @override_settings(
        MAX_ATTACHMENT_SIZE=350_000,
    )
    def test_sending_over_file_size_limit(self) -> None:
        """This test checks if we try to send an email with an attachment that
        exceeds the MAX_ATTACHMENT_SIZE set in settings, the small email
        version is sent without an attachment.
        """
        email = EmailMultiAlternatives(
            subject="This is the subject",
            body="Body for attachment version",
            from_email="testing@courtlistener.com",
            to=["bounce@simulator.amazonses.com"],
            headers={f"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )

        html = "<p>Body for attachment version</p>"
        email.attach_alternative(html, "text/html")
        # When sending an email with an attachment is necessary to add a small
        # email body in case we'll need to send a small email only version.
        small_plain = "Body for small version"
        email.attach_alternative(small_plain, "text/plain_small")
        small_html = "<p>Body for small version</p>"
        email.attach_alternative(small_html, "text/html_small")
        # Attach a file that exceeds the MAX_ATTACHMENT_SIZE
        email.attach_file(self.attachment_500)
        email.send()

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]

        # Confirm the attachment is not sent
        self.assertEqual(len(message_sent.attachments), 0)

        message = message_sent.message()

        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Confirm if small email version is sent
        self.assertEqual(plaintext_body, "Body for small version")
        self.assertEqual(html_body, "<p>Body for small version</p>")

    def test_compose_message_from_db(self) -> None:
        """This test checks if we can compose and send a new message based on
        a stored message.
        """

        msg = EmailMultiAlternatives(
            subject="This is the subject",
            body="Body goes here",
            from_email="testing@courtlistener.com",
            to=["success@simulator.amazonses.com"],
            bcc=["bcc_success@simulator.amazonses.com"],
            cc=["cc_success@simulator.amazonses.com"],
            reply_to=["reply_success@simulator.amazonses.com"],
            headers={f"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )
        html = "<p>Body goes here</p>"
        msg.attach_alternative(html, "text/html")
        msg.send()

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)

        # Retrieve the stored message by message_id
        first_stored_email = EmailSent.objects.filter()[0]
        message_id = first_stored_email.message_id
        stored_email = EmailSent.objects.get(message_id=message_id)

        # Compose and send the email based on the stored message
        email = EmailMultiAlternatives(
            stored_email.subject,
            stored_email.plain_text,
            stored_email.from_email,
            stored_email.to,
            stored_email.bcc,
            cc=stored_email.cc,
            reply_to=stored_email.reply_to,
            headers=stored_email.headers,
        )
        html = stored_email.html_message
        email.attach_alternative(html, "text/html")
        email.send()

        # Confirm if we have two stored messages
        stored_email = EmailSent.objects.filter()
        self.assertEqual(stored_email.count(), 2)

        # Confirm if second email is sent
        self.assertEqual(len(mail.outbox), 2)

        message_sent = mail.outbox[1]
        message = message_sent.message()

        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )
        # Compare second message sent with the original message content
        self.assertEqual(message_sent.subject, "This is the subject")
        self.assertEqual(plaintext_body, "Body goes here")
        self.assertEqual(html_body, "<p>Body goes here</p>")
        self.assertEqual(message_sent.from_email, "testing@courtlistener.com")
        self.assertEqual(message_sent.to, ["success@simulator.amazonses.com"])
        self.assertEqual(
            message_sent.bcc, ["bcc_success@simulator.amazonses.com"]
        )
        self.assertEqual(
            message_sent.cc, ["cc_success@simulator.amazonses.com"]
        )
        self.assertEqual(
            message_sent.reply_to, ["reply_success@simulator.amazonses.com"]
        )
        self.assertTrue(message_sent.extra_headers["X-CL-ID"])
        self.assertTrue(message_sent.extra_headers["X-Entity-Ref-ID"])

    def test_normalize_addresses(self) -> None:
        """Test if the normalize_addresses function parses and normalizes
        properly different combinations of list recipients, returns a list of
        normalized email addresses.
        """
        test_cases = (
            (
                [
                    "success@simulator.amazonses.com",
                    "bounce@simulator.amazonses.com",
                    "complaint@simulator.amazonses.com",
                ],
                [
                    "success@simulator.amazonses.com",
                    "bounce@simulator.amazonses.com",
                    "complaint@simulator.amazonses.com",
                ],
            ),
            (
                [
                    "Admin User <success_1@simulator.amazonses.com>",
                    "New User <bounce_1@simulator.amazonses.com>",
                    "complaint_1@simulator.amazonses.com",
                ],
                [
                    "success_1@simulator.amazonses.com",
                    "bounce_1@simulator.amazonses.com",
                    "complaint_1@simulator.amazonses.com",
                ],
            ),
            (
                [
                    "<success_2@simulator.amazonses.com>",
                    "<bounce_2@simulator.amazonses.com>",
                    "complaint_2@simulator.amazonses.com",
                ],
                [
                    "success_2@simulator.amazonses.com",
                    "bounce_2@simulator.amazonses.com",
                    "complaint_2@simulator.amazonses.com",
                ],
            ),
            (
                ["success@simulator.amazonses.com"],
                ["success@simulator.amazonses.com"],
            ),
            ([], []),
        )

        for test, result in test_cases:
            normalized_emails = normalize_addresses(test)
            self.assertEqual(normalized_emails, result)

    def test_sending_multiple_recipients_email(self) -> None:
        """Test if we can send a message to multiple recipients, bcc, cc, and
        reply_to email addresses.

        We should store recipients, bcc, cc, and reply_to as a list of
        normalized email addresses.
        """

        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "User Admin <testing@courtlistener.com>",
            [
                "Admin User <success@simulator.amazonses.com>",
                "bounce@simulator.amazonses.com",
                "<complaint@simulator.amazonses.com>",
            ],
            ["BCC User <bcc@example.com>", "bcc@example.com"],
            cc=["CC User <cc@example.com>", "cc@example.com"],
            reply_to=["Reply User <another@example.com>", "reply@example.com"],
            headers={"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )
        email.send()

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]

        self.assertEqual(
            message_sent.from_email, "User Admin <testing@courtlistener.com>"
        )
        self.assertEqual(
            message_sent.to,
            [
                "success@simulator.amazonses.com",
                "bounce@simulator.amazonses.com",
                "complaint@simulator.amazonses.com",
            ],
        )
        self.assertEqual(
            message_sent.bcc, ["BCC User <bcc@example.com>", "bcc@example.com"]
        )
        self.assertEqual(
            message_sent.cc, ["CC User <cc@example.com>", "cc@example.com"]
        )
        self.assertEqual(
            message_sent.reply_to,
            ["Reply User <another@example.com>", "reply@example.com"],
        )

        message = message_sent.message()
        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Confirm if normal email version is sent
        self.assertEqual(plaintext_body, "Body goes here")

        # Retrieve stored email and compare content, small version should
        # be stored
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(stored_email[0].plain_text, "Body goes here")
        self.assertEqual(
            stored_email[0].from_email,
            "User Admin <testing@courtlistener.com>",
        )
        self.assertEqual(
            stored_email[0].to,
            [
                "success@simulator.amazonses.com",
                "bounce@simulator.amazonses.com",
                "complaint@simulator.amazonses.com",
            ],
        )
        self.assertEqual(
            stored_email[0].bcc, ["bcc@example.com", "bcc@example.com"]
        )
        self.assertEqual(
            stored_email[0].cc, ["cc@example.com", "cc@example.com"]
        )
        self.assertEqual(
            stored_email[0].reply_to,
            ["another@example.com", "reply@example.com"],
        )

    def test_sending_multiple_recipients_banned_email(self) -> None:
        """When sending an email to multiple recipients we verify if each
        recipient is not banned, we remove the banned email addresses from
        the list of recipients to avoid sending email to those addresses
        """
        # Trigger a hard_bounce event
        self.send_signal(
            self.hard_bounce_asset,
            "bounce",
            signals.bounce_received,
        )
        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )
        # Checks email address is now banned
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].event_sub_type, EMAIL_NOTIFICATIONS.GENERAL
        )

        send_mail(
            "Subject here",
            "Here is the message.",
            "testing@courtlistener.com",
            [
                "success@simulator.amazonses.com",
                "bounce@simulator.amazonses.com",
                "complaint@simulator.amazonses.com",
            ],
            fail_silently=False,
        )

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)

        # Send only to no banned email addresses
        message_sent = mail.outbox[0]
        self.assertEqual(
            message_sent.to,
            [
                "success@simulator.amazonses.com",
                "complaint@simulator.amazonses.com",
            ],
        )

        # Confirm if email is stored
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)

    def test_sending_multiple_recipients_all_banned(self) -> None:
        """When sending an email to multiple recipients and all of them are
        banned, we discard the message, we don't send and store it.
        """
        # Trigger a hard_bounce event
        self.send_signal(
            self.hard_bounce_asset,
            "bounce",
            signals.bounce_received,
        )
        # Trigger a complaint event
        self.send_signal(
            self.complaint_asset, "complaint", signals.complaint_received
        )
        send_mail(
            "Subject here",
            "Here is the message.",
            "testing@courtlistener.com",
            [
                "bounce@simulator.amazonses.com",
                "complaint@simulator.amazonses.com",
            ],
            fail_silently=False,
        )

        # Confirm if email is not sent
        self.assertEqual(len(mail.outbox), 0)
        # Confirm if email is not stored
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 0)

    def test_sending_multiple_recipients_small_email_only(self) -> None:
        """When sending an email to multiple recipients, if at least one of
        the recipients requires a small version, we send the small email only
        version for all recipients.
        """
        # Trigger a small_email_only soft bounce
        self.send_signal(
            self.soft_bounce_msg_large_asset, "bounce", signals.bounce_received
        )
        email = EmailMultiAlternatives(
            subject="This is the subject",
            body="Body for attachment version",
            from_email="testing@courtlistener.com",
            to=[
                "success@simulator.amazonses.com",
                "bounce@simulator.amazonses.com",
                "complaint@simulator.amazonses.com",
            ],
            headers={f"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )
        # Attach file and small email version
        html = "<p>Body for attachment version</p>"
        email.attach_alternative(html, "text/html")
        small_plain = "Body for small version"
        email.attach_alternative(small_plain, "text/plain_small")
        small_html = "<p>Body for small version</p>"
        email.attach_alternative(small_html, "text/html_small")
        email.attach_file(self.attachment_150)
        email.send()

        # Retrieve stored email and compare content
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(
            stored_email[0].html_message, "<p>Body for small version</p>"
        )
        self.assertEqual(stored_email[0].plain_text, "Body for small version")

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]

        # Confirm not attachment is sent
        self.assertEqual(len(message_sent.attachments), 0)

        message = message_sent.message()

        # Confirm we sent it to all recipients
        self.assertEqual(
            message_sent.to,
            [
                "success@simulator.amazonses.com",
                "bounce@simulator.amazonses.com",
                "complaint@simulator.amazonses.com",
            ],
        )

        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Confirm small email only version is sent
        self.assertEqual(plaintext_body, "Body for small version")
        self.assertEqual(html_body, "<p>Body for small version</p>")

    def test_sending_multiple_recipients_no_small_email_only(self) -> None:
        """When sending an email to multiple recipients and the message
        has a small version but none of the recipients are small_email_only
        flagged, we send the normal email version with attachments.
        """
        email = EmailMultiAlternatives(
            subject="This is the subject",
            body="Body for attachment version",
            from_email="testing@courtlistener.com",
            to=[
                "success@simulator.amazonses.com",
                "bounce@simulator.amazonses.com",
                "complaint@simulator.amazonses.com",
            ],
            headers={f"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )

        html = "<p>Body for attachment version</p>"
        email.attach_alternative(html, "text/html")
        small_plain = "Body for small version"
        email.attach_alternative(small_plain, "text/plain_small")
        small_html = "<p>Body for small version</p>"
        email.attach_alternative(small_html, "text/html_small")
        # Attach a file
        email.attach_file(self.attachment_150)
        email.send()

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]

        self.assertEqual(
            message_sent.to,
            [
                "success@simulator.amazonses.com",
                "bounce@simulator.amazonses.com",
                "complaint@simulator.amazonses.com",
            ],
        )

        # Confirm the attachment is sent
        self.assertEqual(len(message_sent.attachments), 1)
        message = message_sent.message()
        # Extract body content from the message
        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )
        # Confirm if normal email version is sent
        self.assertEqual(plaintext_body, "Body for attachment version")
        self.assertEqual(html_body, "<p>Body for attachment version</p>")

        # Retrieve stored email and compare content, small version should
        # be stored
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(
            stored_email[0].html_message, "<p>Body for small version</p>"
        )
        self.assertEqual(stored_email[0].plain_text, "Body for small version")
        self.assertEqual(
            stored_email[0].to,
            [
                "success@simulator.amazonses.com",
                "bounce@simulator.amazonses.com",
                "complaint@simulator.amazonses.com",
            ],
        )

    @mock.patch(
        "cl.users.email_handlers.send_failed_email",
        side_effect=mock_send_failed_email,
    )
    def test_sending_multiple_recipients_within_backoff(
        self, mock_send_email
    ) -> None:
        """When sending an email to multiple recipients, if we detect an email
        address that is under a backoff waiting period we should eliminate
        that address from the recipient list to avoid sending to it
        and queue for sending later.
        """
        # Trigger first backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )

        send_mail(
            "Subject here",
            "Here is the message.",
            "testing@courtlistener.com",
            [
                "success_back@simulator.amazonses.com",
                "bounce@simulator.amazonses.com",
                "complaint_back@simulator.amazonses.com",
            ],
            fail_silently=False,
        )

        # Confirm if email is sent
        self.assertEqual(len(mail.outbox), 1)

        # Send only to addresses that are not under a backoff waiting period
        message_sent = mail.outbox[0]
        self.assertEqual(
            message_sent.to,
            [
                "success_back@simulator.amazonses.com",
                "complaint_back@simulator.amazonses.com",
            ],
        )

        # Confirm if email is stored
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)

    @mock.patch(
        "cl.users.email_handlers.send_failed_email",
        side_effect=mock_send_failed_email,
    )
    def test_sending_multiple_recipients_all_within_backoff(
        self, mock_send_email
    ) -> None:
        """When sending an email to multiple recipients, if we detect that all
        email addresses are under a backoff waiting period we don't send the
        message, we should store the message.
        """
        # Trigger first backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        # Trigger second backoff notification event
        self.send_signal(
            self.soft_bounce_asset_2, "bounce", signals.bounce_received
        )
        msg_count = send_mail(
            "Subject here",
            "Here is the message.",
            "testing@courtlistener.com",
            [
                "bounce@simulator.amazonses.com",
                "soft_bounce@simulator.amazonses.com",
            ],
        )
        # Confirm if email is not sent
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(msg_count, 0)

        # Confirm if email is stored
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)

    def call_bcc_random(self, message, bcc_rate, iterations) -> int:
        """This function simulates n (iterations) calls to the add_bcc_random
        function and returns a counter_bcc that represents the number of
        messages that are bcc'ed.
        """
        counter_bcc = 0
        for i in range(iterations):
            message = add_bcc_random(message, bcc_rate)
            if message.bcc:
                counter_bcc += 1
            # Clean bcc to test next iteration.
            message.bcc = []
        return counter_bcc

    def average_bcc_random(self, message, bcc_rate, iterations) -> int:
        """This function simulates 50 calls to the call_bcc_random
        function and returns the average number of times that add_bcc_random
        returned True.
        """
        total = 0
        for i in range(50):
            val = self.call_bcc_random(message, bcc_rate, iterations)
            total = total + val
        average = total / 50
        return int(round(average))

    def test_add_bcc_random(self) -> None:
        """Test the add_bcc_random function to verify if it produces the
        expected results based on the bcc_rate provided.

        We use call_bcc_random(bcc_rate, iterations) function with a bcc_rate
        to simulate n calls of the add_bcc_random function, this functions
        returns the total number of times that add_bcc_random returned True
        """

        # Test differnt BCC rates
        # No messages are BCC'ed
        zero_bcc_rate = 0
        # All messages are BCC'ed
        all_bcc_rate = 1
        # 10% are BCC'ed
        ten_bcc_rate = 0.1
        # 1% are BCC'ed
        one_bcc_rate = 0.01

        message = EmailMessage(
            "This is the subject",
            "Body goes here",
            "User Admin <testing@courtlistener.com>",
            [
                "bounce@simulator.amazonses.com",
            ],
        )

        # Get the average number of times that add_bcc_random returns True
        # for different bcc_rate and 10_000 iterations
        average_ten = self.average_bcc_random(message, ten_bcc_rate, 10_000)
        average_one = self.average_bcc_random(message, one_bcc_rate, 10_000)
        average_none = self.average_bcc_random(message, zero_bcc_rate, 10_000)
        average_all = self.average_bcc_random(message, all_bcc_rate, 10_000)

        # For 0.1 bcc rate of 10_000 calls we should get a number very close
        # to 1000, however, to ensure the test never fails we use a range
        # between 900 and 1100
        self.assertTrue(average_ten >= 900 and average_ten <= 1100)

        # For 0.01 bcc rate of 10_000 calls we should get a number very close
        # to 100, however, to ensure the test never fails we use a range
        # between 90 and 110
        self.assertTrue(average_one >= 90 and average_one <= 110)

        # For 1 bcc rate of 10_000 calls we should get 10_000
        self.assertEqual(average_all, 10_000)

        # For 0 bcc rate of 10_000 calls we should get 0
        self.assertEqual(average_none, 0)

    @override_settings(EMAIL_BCC_COPY_RATE=1)
    def test_add_bcc_to_emails(self) -> None:
        """This test checks if bcc is added to the message when we use a
        EMAIL_BCC_COPY_RATE = 1, all messages should be bcc'ed
        """

        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "User Admin <testing@courtlistener.com>",
            [
                "Admin User <success@simulator.amazonses.com>",
            ],
        )

        email.send()
        # Verify if BCC was added to the message
        message_sent = mail.outbox[0]
        self.assertEqual(message_sent.bcc, [settings.BCC_EMAIL_ADDRESS])
        # Retrieve stored email and compare content, additional BCC shouldn't
        # be stored because is not part of the original message
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email[0].bcc, [])

        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "User Admin <testing@courtlistener.com>",
            [
                "Admin User <success@simulator.amazonses.com>",
            ],
            ("BCC User <bcc@example.com>", "bcc@example.com"),
        )
        email.send()
        message_sent = mail.outbox[1]
        # Verify if BCC was added to the message as an additional address
        self.assertEqual(
            message_sent.bcc,
            [
                "BCC User <bcc@example.com>",
                "bcc@example.com",
                settings.BCC_EMAIL_ADDRESS,
            ],
        )
        # Retrieve stored email and compare content, additional BCC shouldn't
        # be stored because is not part of the original message
        stored_email = EmailSent.objects.all()
        self.assertEqual(
            stored_email[1].bcc, ["bcc@example.com", "bcc@example.com"]
        )

    @override_settings(EMAIL_BCC_COPY_RATE=0)
    def test_avoid_add_bcc_to_emails(self) -> None:
        """This test checks if bcc is not added to the message when we use a
        EMAIL_BCC_COPY_RATE = 0, no messages should be bcc'ed
        """

        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "User Admin <testing@courtlistener.com>",
            [
                "Admin User <success@simulator.amazonses.com>",
            ],
        )

        email.send()
        # Verify if the BCC was not added to the message
        message_sent = mail.outbox[0]
        self.assertEqual(message_sent.bcc, [])
        # Retrieve stored email and compare content, additional BCC shouldn't
        # be stored because is not part of the original message
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email[0].bcc, [])

        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "User Admin <testing@courtlistener.com>",
            [
                "Admin User <success@simulator.amazonses.com>",
            ],
            ("BCC User <bcc@example.com>", "bcc@example.com"),
        )
        email.send()
        message_sent = mail.outbox[1]
        # Verify if the BCC was not added to the message
        self.assertEqual(
            message_sent.bcc, ["BCC User <bcc@example.com>", "bcc@example.com"]
        )
        # Retrieve stored email and compare content, additional BCC shouldn't
        # be stored because is not part of the original message
        stored_email = EmailSent.objects.all()
        self.assertEqual(
            stored_email[1].bcc, ["bcc@example.com", "bcc@example.com"]
        )


@override_settings(
    EMAIL_BACKEND="cl.lib.email_backends.EmailBackend",
    BASE_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_BCC_COPY_RATE=0,
)
class RetryFailedEmailTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        test_dir = Path(settings.INSTALL_ROOT) / "cl" / "users" / "test_assets"
        with (
            open(
                test_dir / "general_soft_bounce.json", encoding="utf-8"
            ) as soft_bounce,
            open(
                test_dir / "soft_bounce_with_id.json", encoding="utf-8"
            ) as soft_bounce_with_id,
            open(test_dir / "delivery.json", encoding="utf-8") as delivery,
        ):
            cls.soft_bounce_asset = json.load(soft_bounce)
            cls.soft_bounce_with_id_asset = json.load(soft_bounce_with_id)
            cls.delivery_asset = json.load(delivery)

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
        signal_kwargs[f"{event_name}_obj"] = event_obj
        signal.send(**signal_kwargs)

    def mock_send_failed_email(failed_pk, start):
        """This function mocks the send_failed_email function to avoid calling
        the celery task and avoid unxpected errors.
        """
        return None

    @mock.patch("cl.users.email_handlers.logging")
    def test_avoid_enqueue_a_non_existing_message(self, mock_logging) -> None:
        """This test checks if a warning is logged when trying to enqueue a
        message but the stored message doesn't exist anymore because it was
        deleted.
        """

        # Create a backoff event message ID:
        # 5e9b3e8e-93c8-497f-abd4-00f6ddd566f0
        self.send_signal(
            self.soft_bounce_with_id_asset, "bounce", signals.bounce_received
        )
        # Check message is not queued
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 0)

        # Check if warning is logged
        mock_logging.warning.assert_called_with(
            f"The message: 5e9b3e8e-93c8-497f-abd4-00f6ddd566f0 can't be "
            "enqueued because it doesn't exist anymore."
        )

    def test_compose_message_from_db_retrieve_user_email(self) -> None:
        """This test checks if we can compose an email object from the stored
        message, and also verify if we can retrieve the updated user email
        address in case it has changed.
        """
        # Get user factory
        user_email = self.user

        # Send a message to user_email
        msg = EmailMultiAlternatives(
            subject="This is the subject",
            body="Body goes here",
            from_email="testing@courtlistener.com",
            to=[user_email.email],
            bcc=["bcc_success@simulator.amazonses.com"],
            cc=["cc_success@simulator.amazonses.com"],
            reply_to=["reply_success@simulator.amazonses.com"],
            headers={f"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )
        html = "<p>Body goes here</p>"
        msg.attach_alternative(html, "text/html")
        msg.send()

        # Retrieve stored email and it was linked to the CL user.
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(stored_email[0].user_id, user_email.id)

        # Update user email address
        user_email.email = "new_address@courtlistener.com"
        user_email.save()
        # Compose message from stored message and send.
        message = compose_stored_message(stored_email[0].message_id)
        message.send()
        # Confirm if second email is sent
        self.assertEqual(len(mail.outbox), 2)

        message_sent = mail.outbox[1]
        message = message_sent.message()

        plaintext_body, html_body = get_email_body(
            message, small_version=False
        )

        # Compare second message sent with the original message content
        self.assertEqual(message_sent.subject, "This is the subject")
        self.assertEqual(plaintext_body, "Body goes here")
        self.assertEqual(html_body, "<p>Body goes here</p>")
        self.assertEqual(message_sent.from_email, "testing@courtlistener.com")
        self.assertEqual(message_sent.to, ["new_address@courtlistener.com"])
        self.assertEqual(
            message_sent.reply_to, ["reply_success@simulator.amazonses.com"]
        )
        self.assertTrue(message_sent.extra_headers["X-CL-ID"])
        self.assertTrue(message_sent.extra_headers["X-Entity-Ref-ID"])

    def test_compose_message_from_db_no_cl_user(self) -> None:
        """This test checks if we can compose a message from the stored message
        and check if the message doesn't have a related user we send it to the
        message's original recipient.
        """

        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            ["anon_address@courtlistener.com"],
            bcc=["bcc_success@simulator.amazonses.com"],
            headers={"X-Entity-Ref-ID": "9598e6b0-d88c-488e"},
        )
        email.send()

        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        message = compose_stored_message(stored_email[0].message_id)
        message.send()

        # Confirm if the second email is sent and compare its content.
        self.assertEqual(len(mail.outbox), 2)
        message_sent = mail.outbox[1]
        self.assertEqual(message_sent.to, ["anon_address@courtlistener.com"])
        self.assertEqual(message_sent.bcc, [])

    @mock.patch(
        "cl.users.email_handlers.send_failed_email",
        side_effect=mock_send_failed_email,
    )
    def test_enqueue_email_backoff_event(self, mock_send_email) -> None:
        """This test checks if an email is properly enqueued when the
        recipient's email address is under a backoff event waiting period and
        we send more messages to the user.
        """

        # Create a backoff event for bounce@simulator.amazonses.com
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )

        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )

        email.send()

        # Email is sent
        self.assertEqual(len(mail.outbox), 0)

        # Retrieve stored email and compare content
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(
            stored_email[0].to, ["bounce@simulator.amazonses.com"]
        )

        # Check the message is queued
        mock_send_email.assert_called()
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 1)

        # The message should be enqueued as ENQUEUED status since there wasn't
        # a previous ENQUEUED message.
        self.assertEqual(failed_email[0].status, STATUS_TYPES.ENQUEUED)
        self.assertEqual(
            failed_email[0].message_id, stored_email[0].message_id
        )
        EmailSent.objects.all().delete()

        # Send another message
        email = EmailMessage(
            "This is the subject two",
            "Body goes here",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )

        email.send()

        # This time since the recipient is under a backoff waiting period and
        # it already has a ENQUEUE message, following messages are going to be
        # enqueued in a WAITING status.

        # Email is not sent
        self.assertEqual(len(mail.outbox), 0)

        # Retrieve stored email
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)

        # Check the email is queued, now we have two FailedEmail objects.
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 2)

        # Confirm if the second FailedEmail object status is WAITING
        failed_email = FailedEmail.objects.filter(status=STATUS_TYPES.WAITING)
        self.assertEqual(failed_email[0].status, STATUS_TYPES.WAITING)
        self.assertEqual(
            failed_email[0].message_id, stored_email[0].message_id
        )

    @mock.patch(
        "cl.users.email_handlers.send_failed_email",
        side_effect=mock_send_failed_email,
    )
    def test_enqueue_email_soft_bounce(self, mock_send_email) -> None:
        """This test checks if we can queue a message properly after receiving
        a soft bounce notification.
        """

        # Send a message
        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )
        email.send()
        # Email is sent
        self.assertEqual(len(mail.outbox), 1)

        # Retrieve the stored message and update its message_id for testing
        stored_email = EmailSent.objects.all()[0]
        stored_email.message_id = "5e9b3e8e-93c8-497f-abd4-00f6ddd566f0"
        stored_email.save()

        self.assertEqual(stored_email.to, ["bounce@simulator.amazonses.com"])
        self.assertEqual(
            str(stored_email.message_id),
            "5e9b3e8e-93c8-497f-abd4-00f6ddd566f0",
        )

        # Create a backoff event for bounce@simulator.amazonses.com and
        # Message ID: 5e9b3e8e-93c8-497f-abd4-00f6ddd566f0
        self.send_signal(
            self.soft_bounce_with_id_asset, "bounce", signals.bounce_received
        )

        # Check the soft bounce message related is queued
        mock_send_email.assert_called()
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 1)

        self.assertEqual(failed_email[0].status, STATUS_TYPES.ENQUEUED)
        self.assertEqual(
            str(failed_email[0].message_id), stored_email.message_id
        )

        # Send another bounce notification for the same recipient
        # the related message has to be created as a WAITING status since we
        # have already an ENQUEUED message.
        self.send_signal(
            self.soft_bounce_with_id_asset, "bounce", signals.bounce_received
        )

        # Check the message is queued
        mock_send_email.assert_called()
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 2)

        failed_email = FailedEmail.objects.filter(status=STATUS_TYPES.WAITING)
        self.assertEqual(failed_email[0].status, STATUS_TYPES.WAITING)
        self.assertEqual(
            str(failed_email[0].message_id), stored_email.message_id
        )

    @mock.patch(
        "cl.users.email_handlers.send_failed_email",
        side_effect=mock_send_failed_email,
    )
    def test_enqueue_email_after_delivery(self, mock_send_email) -> None:
        """This test checks if after a delivery notification, WAITING failed
        messages are properly scheduled to retry them.
        """

        # Create a backoff event for bounce@simulator.amazonses.com
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )

        email_1 = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )

        email_1.send()

        email_2 = EmailMessage(
            "This is the subject 2",
            "Body goes here 2",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )

        email_2.send()

        email_3 = EmailMessage(
            "This is the subject 3",
            "Body goes here 3",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )

        email_3.send()

        # Messages are not sent
        self.assertEqual(len(mail.outbox), 0)

        # Retrieve stored email and compare content
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 3)
        self.assertEqual(
            stored_email[0].to, ["bounce@simulator.amazonses.com"]
        )

        # Messages are queued, one in ENQUEUED status and two in WAITING.
        mock_send_email.assert_called()
        failed_email = FailedEmail.objects.filter(status=STATUS_TYPES.ENQUEUED)
        self.assertEqual(failed_email.count(), 1)
        self.assertEqual(failed_email[0].status, STATUS_TYPES.ENQUEUED)
        self.assertEqual(
            failed_email[0].message_id, stored_email[0].message_id
        )
        failed_email = FailedEmail.objects.filter(status=STATUS_TYPES.WAITING)
        self.assertEqual(failed_email.count(), 2)

        # Trigger a delivery event
        self.send_signal(
            self.delivery_asset, "delivery", signals.delivery_received
        )

        # After the delivery notification the failed messages under WAITING status
        # were scheduled, now under ENQUEUED_DELIVERY status
        failed_email = FailedEmail.objects.filter(status=STATUS_TYPES.ENQUEUED)
        self.assertEqual(failed_email.count(), 1)

        failed_email = FailedEmail.objects.filter(
            status=STATUS_TYPES.ENQUEUED_DELIVERY
        )
        self.assertEqual(failed_email.count(), 2)

    @mock.patch(
        "cl.users.email_handlers.send_failed_email",
        side_effect=mock_send_failed_email,
    )
    def test_delete_failed_task_objects(self, mock_send_email) -> None:
        """This test checks if delete_failed_tasks_objects function works
        properly. We shouldn't eliminate objects whose next_retry_date is ahead
        but the ones that are behind (those whose tasks have failed)
        """

        # Send a message and update its message_id
        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )
        email.send()
        # Retrieve stored email and update message_id for testing
        stored_email = EmailSent.objects.all()[0]
        stored_email.message_id = "5e9b3e8e-93c8-497f-abd4-00f6ddd566f0"
        stored_email.save()

        # Create a backoff event for bounce@simulator.amazonses.com and
        # Message ID: 5e9b3e8e-93c8-497f-abd4-00f6ddd566f0
        self.send_signal(
            self.soft_bounce_with_id_asset, "bounce", signals.bounce_received
        )

        # Here we should have an ENQUEUE FailedEmail object.
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 1)
        self.assertEqual(failed_email[0].status, STATUS_TYPES.ENQUEUED)

        # Update next_retry_date to expire waiting time, simulating is going to
        # expire soon.
        BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        ).update(next_retry_date=now() + timedelta(minutes=1))

        # The recipient is under a backoff event waiting period, so if we try
        # to send two more messages they are going to fail and create two
        # WAITING FailedEmail objects.
        email_1 = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )

        email_1.send()

        email_2 = EmailMessage(
            "This is the subject 2",
            "Body goes here 2",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )

        email_2.send()
        failed_email = FailedEmail.objects.filter(status=STATUS_TYPES.WAITING)
        self.assertEqual(failed_email.count(), 2)

        # Trigger two delivery notifications to confirm that ENQUEUED_DELIVERY
        # failed messages are not deleted.
        self.send_signal(
            self.delivery_asset, "delivery", signals.delivery_received
        )
        self.send_signal(
            self.delivery_asset, "delivery", signals.delivery_received
        )
        # We should have 3 FailedEmail objects now.
        failed_email = FailedEmail.objects.filter(status=STATUS_TYPES.ENQUEUED)
        self.assertEqual(failed_email.count(), 1)
        failed_email = FailedEmail.objects.filter(
            status=STATUS_TYPES.ENQUEUED_DELIVERY
        )
        self.assertEqual(failed_email.count(), 2)

        # Now simulate that the celery tasks of previous FailedEmail objects
        # failed, set that they failed 35 minutes ago.
        FailedEmail.objects.all().update(
            next_retry_date=now() - timedelta(minutes=35)
        )
        # Trigger a new delivery notification
        self.send_signal(
            self.delivery_asset, "delivery", signals.delivery_received
        )
        # Failed objects are eliminated.
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 0)

    @mock.patch(
        "cl.users.email_handlers.send_failed_email",
        side_effect=mock_send_failed_email,
    )
    def test_retry_datetime(self, mock_send_email) -> None:
        """This test checks that retry times are properly computed."""

        # Send a message
        email = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )
        email.send()
        # Retrieve stored email and update message_id for testing
        stored_email = EmailSent.objects.all()[0]
        stored_email.message_id = "5e9b3e8e-93c8-497f-abd4-00f6ddd566f0"
        stored_email.save()

        # Create a backoff event for bounce@simulator.amazonses.com and
        # Message ID: 5e9b3e8e-93c8-497f-abd4-00f6ddd566f0
        self.send_signal(
            self.soft_bounce_with_id_asset, "bounce", signals.bounce_received
        )

        # Now we have one ENQUEUE FailedEmail object
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 1)
        self.assertEqual(failed_email[0].status, STATUS_TYPES.ENQUEUED)

        backoff = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )

        # ENQUEUE FailedEmail object should be scheduled for one minute after
        # the backoff event expires
        self.assertEqual(
            failed_email[0].next_retry_date,
            backoff[0].next_retry_date + timedelta(milliseconds=60_000),
        )

        # Send 3 more messages that are going to be enqueued
        email_1 = EmailMessage(
            "This is the subject",
            "Body goes here",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )
        email_1.send()

        email_2 = EmailMessage(
            "This is the subject 2",
            "Body goes here 2",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )
        email_2.send()

        email_3 = EmailMessage(
            "This is the subject 2",
            "Body goes here 2",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )
        email_3.send()

        failed_email = FailedEmail.objects.filter(status=STATUS_TYPES.WAITING)
        self.assertEqual(failed_email.count(), 3)
        now_time = now()
        # Trigger a delivery notification.
        self.send_signal(
            self.delivery_asset, "delivery", signals.delivery_received
        )

        # WAITING FailedEmail objects were scheduled with
        # ENQUEUED_DELIVERY status
        failed_email = FailedEmail.objects.filter(
            status=STATUS_TYPES.ENQUEUED_DELIVERY
        ).order_by("next_retry_date")
        self.assertEqual(failed_email.count(), 3)

        # Failed messages after a delivery notification should be scheduled to
        # send one message per minute, one after the other.
        expected_datetime_1 = now_time + timedelta(milliseconds=60_000)
        expected_datetime_2 = now_time + timedelta(milliseconds=120_000)
        expected_datetime_3 = now_time + timedelta(milliseconds=180_000)

        self.assertEqual(
            failed_email[0].next_retry_date.strftime("%Y-%m-%d %H:%M:%S"),
            expected_datetime_1.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.assertEqual(
            failed_email[1].next_retry_date.strftime("%Y-%m-%d %H:%M:%S"),
            expected_datetime_2.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.assertEqual(
            failed_email[2].next_retry_date.strftime("%Y-%m-%d %H:%M:%S"),
            expected_datetime_3.strftime("%Y-%m-%d %H:%M:%S"),
        )


class EmailBrokenTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_dir = Path(settings.INSTALL_ROOT) / "cl" / "users" / "test_assets"
        with (
            open(
                test_dir / "hard_bounce.json", encoding="utf-8"
            ) as hard_bounce,
            open(test_dir / "complaint.json", encoding="utf-8") as complaint,
            open(test_dir / "delivery.json", encoding="utf-8") as delivery,
            open(
                test_dir / "mail_box_full_soft_bounce.json", encoding="utf-8"
            ) as mail_box_full_soft_bounce,
            open(
                test_dir / "no_email_hard_bounce.json", encoding="utf-8"
            ) as no_email_hard_bounce,
            open(
                test_dir / "msg_large_bounce.json", encoding="utf-8"
            ) as msg_large_bounce,
        ):
            cls.hard_bounce_asset = json.load(hard_bounce)
            cls.complaint_asset = json.load(complaint)
            cls.delivery_asset = json.load(delivery)
            cls.no_email_hard_bounce_asset = json.load(no_email_hard_bounce)
            cls.mail_box_full_soft_bounce_asset = json.load(
                mail_box_full_soft_bounce
            )
            cls.msg_large_bounce_asset = json.load(msg_large_bounce)
        cls.user = UserFactory()

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
        signal_kwargs[f"{event_name}_obj"] = event_obj
        signal.send(**signal_kwargs)

    def test_multiple_bounce_subtypes(self) -> None:
        """This test checks if we can assign properly the bounce subtype for
        EmailFlag and BackoffEvent objects
        """

        # Trigger a hard bounce notification event
        self.send_signal(
            self.no_email_hard_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )
        # The bounce subtype should be NOEMAIL
        self.assertEqual(
            email_ban[0].event_sub_type, EMAIL_NOTIFICATIONS.NO_EMAIL
        )

        # Trigger a soft bounce notification event
        self.send_signal(
            self.mail_box_full_soft_bounce_asset,
            "bounce",
            signals.bounce_received,
        )
        backoff_event = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        # The bounce subtype should be MAILBOXFULL
        self.assertEqual(
            backoff_event[0].notification_subtype,
            EMAIL_NOTIFICATIONS.MAILBOX_FULL,
        )

    def test_broken_email_address_banner(self) -> None:
        """This test checks if soft and hard bounces events properly trigger a
        broken email address banner, a Permanent broken email address banner
        overrides a previous Transient broken banner.
        """

        path = reverse("show_results")
        # An anonymous user should never see the broken email banner.
        r = self.client.get(path)
        self.assertEqual(r.context.get("email_msg"), None)

        user = self.user
        user.email = "bounce@simulator.amazonses.com"
        user.password = make_password("password")
        user.save()
        # Authenticate user
        login = self.client.login(username=user.username, password="password")
        r = self.client.get(path)

        # The user's email has no problems, no banner showed
        self.assertEqual(r.context.get("email_msg"), None)

        # Trigger a small_email_only flag
        self.send_signal(
            self.msg_large_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )
        self.assertEqual(email_ban.count(), 0)
        r = self.client.get(path)
        # An small_email_only EmailFlag object shouldn't trigger a broken
        # email banner
        self.assertEqual(r.context.get("email_msg"), None)

        # Trigger a soft bounce notification event
        self.send_signal(
            self.mail_box_full_soft_bounce_asset,
            "bounce",
            signals.bounce_received,
        )
        backoff_event = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        self.assertEqual(backoff_event.count(), 1)
        r = self.client.get(path)

        # A mail_box_full soft bounce event should trigger a Transient broken
        # email banner, we have a msg and no email_banned_date
        self.assertEqual(r.context.get("email_banned_date"), None)
        self.assertNotEqual(r.context.get("email_msg"), None)

        # Trigger a hard bounce notification event
        self.send_signal(
            self.hard_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )
        self.assertEqual(email_ban.count(), 1)
        r = self.client.get(path)
        # A hard bounce event should trigger a Permanent broken
        # email banner, we have a msg and email_banned_date
        self.assertNotEqual(r.context.get("email_msg"), None)
        self.assertNotEqual(r.context.get("email_banned_date"), None)

    def test_broken_email_banner_complaint(self) -> None:
        """This test checks if a complaint notification properly triggers a
        Permanent broken email banner.
        """

        path = reverse("show_results")
        user = self.user
        user.email = "complaint@simulator.amazonses.com"
        user.password = make_password("password")
        user.save()
        login = self.client.login(username=user.username, password="password")
        r = self.client.get(path)
        self.assertEqual(r.context.get("email_msg"), None)

        # Trigger a complaint notification event
        self.send_signal(
            self.complaint_asset, "complaint", signals.complaint_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="complaint@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )
        self.assertEqual(email_ban.count(), 1)
        r = self.client.get(path)
        # A complaint event should trigger a Permanent broken
        # email banner, we have a msg and email_banned_date
        self.assertNotEqual(r.context.get("email_msg"), None)
        self.assertNotEqual(r.context.get("email_banned_date"), None)

    def test_broken_email_address_banner_first_permanent(self) -> None:
        """This test checks if a Permanent broken email event comes first than
        Transient broken email event, Permanent banner will be prioritized,
        also checks if users change their email address the email broken banner
        should dissapear.
        """

        path = reverse("show_results")
        user = self.user
        user.email = "bounce@simulator.amazonses.com"
        user.password = make_password("password")
        user.save()
        # Authenticate user
        login = self.client.login(username=user.username, password="password")
        r = self.client.get(path)
        # The user's email has no problems, no banner showed
        self.assertEqual(r.context.get("email_msg"), None)

        # Trigger a hard bounce notification event
        self.send_signal(
            self.hard_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            object_type=OBJECT_TYPES.BAN,
        )
        self.assertEqual(email_ban.count(), 1)
        r = self.client.get(path)
        # A hard bounce event should trigger a Permanent broken
        # email banner, we have a msg and email_banned_date
        self.assertNotEqual(r.context.get("email_msg"), None)
        self.assertNotEqual(r.context.get("email_banned_date"), None)

        # Trigger a soft bounce notification event
        self.send_signal(
            self.mail_box_full_soft_bounce_asset,
            "bounce",
            signals.bounce_received,
        )
        backoff_event = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        self.assertEqual(backoff_event.count(), 1)
        r = self.client.get(path)
        # A backoff event is created but the Permanent broken email banner is
        # prioritized
        self.assertNotEqual(r.context.get("email_msg"), None)
        self.assertNotEqual(r.context.get("email_banned_date"), None)

        # Simulate user changes their email address to solve the Permanent
        # email error.
        user.email = "new@simulator.amazonses.com"
        user.save()
        login = self.client.login(username=user.username, password="password")

        r = self.client.get(path)
        # The broken email banner is gone
        self.assertEqual(r.context.get("email_msg"), None)

    def test_broken_email_banner_delivery(self) -> None:
        """This test checks if a delivery notification properly deactivate a
        Transient broken email banner.
        """

        path = reverse("show_results")
        user = self.user
        user.email = "bounce@simulator.amazonses.com"
        user.password = make_password("password")
        user.save()
        login = self.client.login(username=user.username, password="password")
        r = self.client.get(path)
        self.assertEqual(r.context.get("email_msg"), None)

        # Trigger a soft bounce notification event
        self.send_signal(
            self.mail_box_full_soft_bounce_asset,
            "bounce",
            signals.bounce_received,
        )
        backoff_event = BackoffEvent.objects.filter(
            email_address="bounce@simulator.amazonses.com",
        )
        self.assertEqual(backoff_event.count(), 1)
        r = self.client.get(path)

        # A mail_box_full soft bounce event should trigger a Transient broken
        # email banner, we have a msg and no email_banned_date
        self.assertEqual(r.context.get("email_banned_date"), None)
        self.assertNotEqual(r.context.get("email_msg"), None)

        # Trigger a delivery event
        self.send_signal(
            self.delivery_asset, "delivery", signals.delivery_received
        )
        # Delivery event eliminates the backoff event
        self.assertEqual(backoff_event.count(), 0)

        r = self.client.get(path)
        # The broken email banner is gone
        self.assertEqual(r.context.get("email_msg"), None)
