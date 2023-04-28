import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import time_machine
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives, send_mail
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.timezone import now
from django_ses import signals
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator

from cl.alerts.factories import DocketAlertFactory
from cl.alerts.models import DocketAlert, DocketAlertEvent
from cl.api.factories import WebhookEventFactory, WebhookFactory
from cl.api.models import (
    Webhook,
    WebhookEvent,
    WebhookEventType,
    WebhookHistoryEvent,
)
from cl.favorites.factories import UserTagFactory
from cl.favorites.models import (
    DocketTag,
    DocketTagEvent,
    UserTag,
    UserTagEvent,
)
from cl.lib.test_helpers import SimpleUserDataMixin
from cl.search.factories import DocketFactory
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import APITestCase, LiveServerTestCase, TestCase
from cl.tests.utils import MockResponse as MockPostResponse
from cl.tests.utils import make_client
from cl.users.email_handlers import (
    add_bcc_random,
    get_email_body,
    normalize_addresses,
)
from cl.users.factories import (
    EmailSentFactory,
    UserFactory,
    UserProfileWithParentsFactory,
)
from cl.users.management.commands.cl_delete_old_emails import delete_old_emails
from cl.users.management.commands.cl_retry_failed_email import (
    handle_failing_emails,
)
from cl.users.management.commands.cl_welcome_new_users import (
    get_welcome_recipients,
)
from cl.users.models import (
    EMAIL_NOTIFICATIONS,
    FLAG_TYPES,
    STATUS_TYPES,
    EmailFlag,
    EmailSent,
    FailedEmail,
    UserProfile,
)
from cl.users.tasks import update_moosend_subscription


class UserTest(LiveServerTestCase):
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


class UserDataTest(LiveServerTestCase):
    def test_signing_in(self) -> None:
        """Can we create a user on the backend then sign them in"""
        params = {"username": "pandora", "password": "password"}
        UserProfileWithParentsFactory.create(
            user__username=params["username"],
            user__password=make_password(params["password"]),
        )
        r = self.client.post(reverse("sign-in"), params, follow=True)
        self.assertRedirects(r, "/")

    def test_confirming_an_email_address(self) -> None:
        """Tests whether we can confirm the case where an email is associated
        with a single account.
        """
        # Update the expiration since the fixture has one some time ago.
        up = UserProfileWithParentsFactory.create(email_confirmed=False)

        r = self.client.get(reverse("email_confirm", args=[up.activation_key]))
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
        ups = UserProfileWithParentsFactory.create_batch(
            3,
            activation_key="a" * 40,  # Note length has to be correct
            email_confirmed=False,
        )

        r = self.client.get(
            reverse("email_confirm", args=[ups[0].activation_key])
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
        ups = UserProfile.objects.filter(pk__in=[up.pk for up in ups])
        for up in ups:
            self.assertTrue(up.email_confirmed)

    def test_get_welcome_email_recipients(self) -> None:
        """This test verifies that we can get the welcome email recipients
        properly, users that signed up in the last 24 hours.
        """

        # Create a new user.
        UserProfileWithParentsFactory.create(email_confirmed=False)
        time_now = datetime.now()
        # Get last 24 hours signed-up users.
        recipients = get_welcome_recipients(time_now)
        # The newly created user should be returned.
        self.assertEqual(len(recipients), 1)

        # Simulate getting recipients for tomorrow.
        tomorrow = time_now + timedelta(days=1)
        recipients = get_welcome_recipients(tomorrow)
        # No recipients should be returned.
        self.assertEqual(len(recipients), 0)


class ProfileTest(SimpleUserDataMixin, TestCase):
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
        response = self.client.post(
            reverse("delete_account"),
            {"password": "password"},
            follow=True,
        )
        self.assertRedirects(
            response,
            reverse("delete_profile_done"),
        )

    def test_generate_recap_dot_email_addresses(self) -> None:
        # Test simple username
        u = User.objects.get(username="pandora")
        self.assertEqual(u.profile.recap_email, "pandora@recap.email")

        # Test with email address username
        up = UserProfileWithParentsFactory(user__username="pandora@gmail.com")
        self.assertEqual(up.recap_email, "pandora.gmail.com@recap.email")

        # Test username lowercasing
        up = UserProfileWithParentsFactory(user__username="Test.User")
        self.assertEqual(up.recap_email, "test.user@recap.email")

    def test_nuke_user_history_objects_assets_deleting_account(self) -> None:
        """Are user related history objects properly removed when deleting the
        user account?
        """

        user_1 = UserProfileWithParentsFactory()
        user_2 = UserProfileWithParentsFactory()
        docket = DocketFactory()
        docket_2 = DocketFactory()
        docket_alert = DocketAlertFactory(docket=docket, user=user_1.user)
        docket_alert_2 = DocketAlertFactory(docket=docket_2, user=user_1.user)
        docket_alert_3 = DocketAlertFactory(docket=docket_2, user=user_2.user)

        # Confirm docket alert objects are created.
        docket_alerts = DocketAlert.objects.all()
        self.assertEqual(docket_alerts.count(), 3)

        # Trigger a change for docket alert objects.
        docket_alert.alert_type = DocketAlert.UNSUBSCRIPTION
        docket_alert.save()
        docket_alert_2.alert_type = DocketAlert.UNSUBSCRIPTION
        docket_alert_2.save()
        docket_alert_3.alert_type = DocketAlert.UNSUBSCRIPTION
        docket_alert_3.save()

        docket_alert_events = DocketAlertEvent.objects.all()
        # More docket alert history objects should be created.
        self.assertEqual(docket_alert_events.count(), 3)

        # Delete user account.
        self.assertTrue(
            self.client.login(
                username=user_1.user.username, password="password"
            )
        )
        self.client.post(
            reverse("delete_account"),
            {"password": "password"},
            follow=True,
        )

        # Confirm that only history events objects related to the user deleted
        # are removed from the events table.
        self.assertEqual(docket_alerts.count(), 1)
        self.assertEqual(docket_alert_events.count(), 1)

    def test_nuke_user_tag_and_docket_tag_history_objects(self) -> None:
        """Are user_tag and docket_tag history objects properly removed when
        deleting the user account?  This is different from the previous test
        since docket_tag is no directly related to the user.
        """

        docket_1 = DocketFactory()
        docket_2 = DocketFactory()
        user_1 = UserProfileWithParentsFactory()
        user_2 = UserProfileWithParentsFactory()

        tag_1_user_1 = UserTagFactory(user=user_1.user, name="tag_1_user_1")
        tag_1_user_1.dockets.add(docket_1.pk)
        tag_1_user_2 = UserTagFactory(user=user_2.user, name="tag_1_user_2")
        tag_1_user_2.dockets.add(docket_1.pk)

        # Confirm user tags and docket tags are created.
        user_tags = UserTag.objects.all()
        docket_tags = DocketTag.objects.all()
        self.assertEqual(user_tags.count(), 2)
        self.assertEqual(docket_tags.count(), 2)

        # Confirm user tags and docket tags history objects are created.
        tag_1_user_1.name = "tag_1_user_1_1"
        tag_1_user_1.save()
        tag_1_user_2.name = "tag_1_user_2_2"
        tag_1_user_2.save()
        user_tag_events = UserTagEvent.objects.all()
        self.assertEqual(user_tag_events.count(), 2)

        tag_1_user_1.docket_tags.all().update(docket=docket_2)
        tag_1_user_2.docket_tags.all().update(docket=docket_2)
        docket_tag_events = DocketTagEvent.objects.all()
        self.assertEqual(docket_tag_events.count(), 2)

        # Delete user account.
        self.assertTrue(
            self.client.login(
                username=user_1.user.username, password="password"
            )
        )
        self.client.post(
            reverse("delete_account"),
            {"password": "password"},
            follow=True,
        )

        # Confirm that only history events objects related to the user deleted
        # are removed from the events table.
        self.assertEqual(user_tags.count(), 1)
        self.assertEqual(docket_tags.count(), 1)
        self.assertEqual(user_tag_events.count(), 1)
        self.assertEqual(docket_tag_events.count(), 1)
        self.assertEqual(user_tag_events[0].name, "tag_1_user_2")
        self.assertEqual(docket_tag_events[0].tag_id, tag_1_user_2.pk)


class DisposableEmailTest(SimpleUserDataMixin, TestCase):
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
    def setUp(self) -> None:
        self.up = UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
            user__email="pandora@courtlistener.com",
        )

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
        token = default_token_generator.make_token(self.up.user)
        url = "{host}{path}".format(
            host=self.live_server_url,
            path=reverse(
                "confirm_password",
                kwargs={
                    "uidb64": urlsafe_base64_encode(
                        str(self.up.user.pk).encode()
                    ),
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
    def setUpTestData(cls) -> None:
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
            open(
                test_dir / "suppressed_bounce.json", encoding="utf-8"
            ) as suppressed_bounce,
            open(test_dir / "no_bounce.json", encoding="utf-8") as no_bounce,
        ):
            cls.soft_bounce_asset = json.load(general_soft_bounce)
            cls.soft_bounce_msg_large_asset = json.load(msg_large_bounce)
            cls.soft_bounce_cnt_rejected_asset = json.load(cnt_rejected_bounce)
            cls.hard_bounce_asset = json.load(hard_bounce)
            cls.complaint_asset = json.load(complaint)
            cls.suppressed_asset = json.load(suppressed_bounce)
            cls.no_failed_bounce_asset = json.load(no_bounce)

    def send_signal(self, test_asset, event_name, signal) -> None:
        """Function to dispatch signal that mocks a SNS notification event
        :param test_asset: the json object that contains notification
        :param event_name: the signal event name
        :param signal: the signal corresponding to the event
        :return: None
        """
        # Prepare parameters
        message = json.loads(test_asset["Message"])
        mail_obj = message.get("mail")
        event_obj = message.get(event_name, {})

        # Send signal
        signal_kwargs = dict(
            sender=self,
            mail_obj=mail_obj,
            raw_message=test_asset,
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
    def test_soft_bounce_signal_failed(self, mock_soft_bounce) -> None:
        """This test checks if handle_soft_bounce function is called
        when a failed soft bounce event is received
        """
        # Trigger a soft bounce event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        # Check if handle_soft_bounce is called
        mock_soft_bounce.assert_called()

    @mock.patch("cl.users.signals.handle_soft_bounce")
    def test_soft_bounce_signal_not_failed(self, mock_soft_bounce) -> None:
        """This test checks if handle_soft_bounce function is not called
        when a not failed soft bounce event is received
        """
        # Trigger a soft bounce event for a no failed action
        self.send_signal(
            self.no_failed_bounce_asset, "bounce", signals.bounce_received
        )
        # Check if handle_soft_bounce is not called
        mock_soft_bounce.assert_not_called()

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
        warning_part_two = "bounce@simulator.amazonses.com, message_id: "
        mock_logging.warning.assert_called_with(
            f"{warning_part_one}{warning_part_two}"
        )

    def test_handle_soft_bounce_create_back_off(self) -> None:
        """This test checks if a back_off event is created for
        an email address if it doesn't exist previously when a
        backoff type soft bounce is received
        """
        email_backoff_exists = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        ).exists()

        self.assertEqual(email_backoff_exists, False)
        # Trigger a backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )

        email_backoff_exists = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
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
        email_backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
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

        email_backoff_event_after = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
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
        EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        ).update(next_retry_date=now() - timedelta(hours=3))

        email_backoff = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )
        # Store parameters after first backoff event
        retry_counter_before = email_backoff[0].retry_counter
        next_retry_date_before = email_backoff[0].next_retry_date
        # Trigger second backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_backoff_after = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
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
            flag_type=FLAG_TYPES.BAN,
        ).exists()
        # Check email address is not banned
        self.assertEqual(email_ban_exist, False)

        # Update next_retry_date to expire waiting time and retry_counter to
        # reach max_retry_counter
        backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )
        backoff_event.update(
            next_retry_date=now() - timedelta(hours=3), retry_counter=5
        )
        # Trigger second backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban_exist = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BAN,
        ).exists()
        # Check email address is now banned and backoff event deleted
        self.assertEqual(email_ban_exist, True)
        self.assertEqual(backoff_event.count(), 0)

        # Trigger another notification event to check
        # no new ban register is created
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BAN,
        )

        # Checks no new ban object is created for this email address
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].notification_subtype,
            EMAIL_NOTIFICATIONS.MAX_RETRY_REACHED,
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
        EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        ).update(next_retry_date=now() - timedelta(hours=3), retry_counter=4)

        email_backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )
        # Store parameter before backoff event is update
        retry_counter_before = email_backoff_event[0].retry_counter
        # Trigger second backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_backoff_event_after = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )

        # Store parameters after second backoff event update
        retry_counter_after = email_backoff_event_after[0].retry_counter
        next_retry_date_after = email_backoff_event_after[0].next_retry_date

        # Hours expected for the final backoff waiting period
        expected_waiting_period = 64

        # Obtain waiting period in hours after backoff notification
        waiting_period = next_retry_date_after - now()
        actual_waiting_period = round(waiting_period.total_seconds() / 3600)

        # Check retry counter is updated
        self.assertNotEqual(retry_counter_before, retry_counter_after)
        # Check expected waiting period equals to computed waiting period
        self.assertEqual(expected_waiting_period, actual_waiting_period)

    def test_restart_backoff_event_after_threshold_bounce(self) -> None:
        """This test checks if we properly delete or update a backoff event
        when a new bounce notification comes in. If the bounce event comes in
        before BACKOFF_THRESHOLD hours since the last retry, the backoff event
        is updated. Otherwise, the backoff event is restarted.
        """

        # Trigger first backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )

        email_backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )

        # Update next_retry_date to simulate the last retry was
        # backoff_threshold hours ago, update retry_counter to 4
        backoff_threshold = settings.BACKOFF_THRESHOLD + 1
        email_backoff_event.update(
            next_retry_date=now() - timedelta(hours=backoff_threshold),
            retry_counter=4,
        )

        # Trigger second backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_backoff_event_after = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )

        # Store parameters after second backoff event update
        retry_counter_after = email_backoff_event_after[0].retry_counter
        next_retry_date_after = email_backoff_event_after[0].next_retry_date

        # Backoff event is restarted
        # 2 Hours expected for the next backoff retry
        expected_waiting_period = 2

        # Obtain waiting period in hours after backoff notification
        waiting_period = next_retry_date_after - now()
        actual_waiting_period = round(waiting_period.total_seconds() / 3600)

        # Check retry counter is updated
        self.assertEqual(retry_counter_after, 0)
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
            flag_type=FLAG_TYPES.BAN,
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
            flag_type=FLAG_TYPES.BAN,
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
            flag_type=FLAG_TYPES.BAN,
        )

        # Checks email address is now banned
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].notification_subtype, EMAIL_NOTIFICATIONS.GENERAL
        )

        # Trigger another hard_bounce event
        self.send_signal(
            self.suppressed_asset,
            "bounce",
            signals.bounce_received,
        )

        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BAN,
        )

        # Check no additional email ban object is created
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].notification_subtype, EMAIL_NOTIFICATIONS.GENERAL
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
            flag_type=FLAG_TYPES.BAN,
        )

        # Checks email address is now banned
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].notification_subtype, EMAIL_NOTIFICATIONS.COMPLAINT
        )

        # Trigger another complaint event
        self.send_signal(
            self.complaint_asset, "complaint", signals.complaint_received
        )

        email_ban = EmailFlag.objects.filter(
            email_address="complaint@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BAN,
        )

        # Check no additional email ban object is created
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].notification_subtype, EMAIL_NOTIFICATIONS.COMPLAINT
        )

    @mock.patch(
        "cl.users.management.commands.cl_retry_failed_email.schedule_failed_email"
    )
    def test_check_recipient_deliverability(self, mock_schedule) -> None:
        """This test checks if schedule_failed_email function is called
        if recipient's deliverability is proven.
        """
        # Trigger soft bounce event to create backoff event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )
        email_backoff_exists = email_backoff_event.exists()
        # Check if backoff event was created
        self.assertEqual(email_backoff_exists, True)

        # Fake time, DELIVERABILITY_THRESHOLD hours after backoff event expires
        first_retry_future_time = 2 + settings.DELIVERABILITY_THRESHOLD
        fake_now_1 = now() + timedelta(hours=first_retry_future_time)
        with time_machine.travel(fake_now_1, tick=False):
            # Check recipient's deliverability 3 hours in the future
            # One hour after backoff event expires
            handle_failing_emails()

        # Check if schedule_failed_email is called
        mock_schedule.assert_called()
        # Backoff event checked field is set to True
        self.assertEqual(email_backoff_event[0].checked, fake_now_1)

        # Trigger a new soft bounce event to update the backoff event
        with time_machine.travel(fake_now_1, tick=False):
            self.send_signal(
                self.soft_bounce_asset, "bounce", signals.bounce_received
            )

        # Backoff event is updated, checked set to False.
        self.assertEqual(email_backoff_event[0].checked, None)
        self.assertEqual(email_backoff_event.count(), 1)
        self.assertEqual(email_backoff_event[0].retry_counter, 1)

        # Fake time DELIVERABILITY_THRESHOLD hours after backoff event expires
        second_retry_future_time = 4 + settings.DELIVERABILITY_THRESHOLD
        fake_now_2 = fake_now_1 + timedelta(hours=second_retry_future_time)
        with time_machine.travel(fake_now_2, tick=False):
            # Check recipient's deliverability
            handle_failing_emails()

        # Check if schedule_failed_email is called and backoff marked checked
        self.assertEqual(mock_schedule.call_count, 2)
        self.assertEqual(email_backoff_event[0].checked, fake_now_2)

    @mock.patch(
        "cl.users.management.commands.cl_retry_failed_email.schedule_failed_email"
    )
    def test_check_recipient_deliverability_fails(self, mock_schedule) -> None:
        """This test checks if the backoff event it's not deleted and
        schedule_failed_email function is not called if recipient's
        deliverability is not proven.
        """
        # Trigger soft bounce event to create backoff event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )
        email_backoff_exists = email_backoff_event.exists()
        # Check if backoff event was created
        self.assertEqual(email_backoff_exists, True)

        # Fake time DELIVERABILITY_THRESHOLD hours after backoff event expires
        first_retry_future_time = 2 + settings.DELIVERABILITY_THRESHOLD
        fake_now_1 = now() + timedelta(hours=first_retry_future_time)
        with time_machine.travel(fake_now_1, tick=False):
            # Trigger soft bounce event to update the backoff event
            self.send_signal(
                self.soft_bounce_asset, "bounce", signals.bounce_received
            )
        self.assertEqual(email_backoff_event[0].checked, None)

        # Fake time one hour before backoff event expires.
        second_retry_future_time = 3 + settings.DELIVERABILITY_THRESHOLD
        fake_now_2 = fake_now_1 + timedelta(hours=second_retry_future_time)
        with time_machine.travel(fake_now_2, tick=False):
            # Check recipient's deliverability, deliverability shouldn't be
            # proven.
            handle_failing_emails()

        email_backoff_exists = email_backoff_event.exists()
        # Check if backoff event was not deleted
        self.assertEqual(email_backoff_exists, True)

        # Check if schedule_failed_email is not called
        mock_schedule.assert_not_called()
        # Backoff event checked continue as False
        self.assertEqual(email_backoff_event[0].checked, None)

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
            flag_type=FLAG_TYPES.BAN,
        )

        # Checks email address is now banned due to a complaint
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].notification_subtype, EMAIL_NOTIFICATIONS.COMPLAINT
        )

        # Trigger a hard_bounce event
        self.send_signal(
            self.hard_bounce_asset,
            "bounce",
            signals.bounce_received,
        )

        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BAN,
        )

        # Checks email ban is updated with the hard bounce subtype
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].notification_subtype, EMAIL_NOTIFICATIONS.GENERAL
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
        message = json.loads(test_asset["Message"])
        mail_obj = message.get("mail")
        event_obj = message.get(event_name, {})

        # Send signal
        signal_kwargs = dict(
            sender=self,
            mail_obj=mail_obj,
            raw_message=test_asset,
        )
        signal_kwargs[f"{event_name}_obj"] = event_obj
        signal.send(**signal_kwargs)

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
        plaintext_body, html_body = get_email_body(message)

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
        plaintext_body, html_body = get_email_body(message)

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
        plaintext_body, html_body = get_email_body(message)

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
        plaintext_body, html_body = get_email_body(message)

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
        plaintext_body, html_body = get_email_body(message)

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
            flag_type=FLAG_TYPES.BAN,
        )

        # Checks email address is now banned
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].notification_subtype, EMAIL_NOTIFICATIONS.GENERAL
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

    def test_sending_email_within_back_off(self) -> None:
        """This test checks if an email address is under a backoff waiting
        period and we try to send it an email, the message is stored but
        not sent.
        """
        # Trigger first backoff notification event
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )
        email_backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
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

        plaintext_body, html_body = get_email_body(message)
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
        plaintext_body, html_body = get_email_body(message)

        # Confirm if normal email version is sent
        self.assertEqual(plaintext_body, "Body goes here")

        # Retrieve stored email and compare content
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
            flag_type=FLAG_TYPES.BAN,
        )
        # Checks email address is now banned
        self.assertEqual(email_ban.count(), 1)
        self.assertEqual(
            email_ban[0].notification_subtype, EMAIL_NOTIFICATIONS.GENERAL
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

    def test_sending_multiple_recipients_within_backoff(self) -> None:
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

    def test_sending_multiple_recipients_all_within_backoff(self) -> None:
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


class DeleteOldEmailsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.msg1 = EmailSentFactory()
        cls.msg2 = EmailSentFactory()
        cls.msg3 = EmailSentFactory()
        # Update date_created to simulate two emails are older than 15 days
        cls.msg1.date_created = now() - timedelta(days=16)
        cls.msg1.save()
        cls.msg2.date_created = now() - timedelta(days=16)
        cls.msg2.save()

    def test_delete_old_emails(self):
        """This test checks if delete_old_emails function works properly
        it should delete only emails older than the specified number of days.
        """

        stored_email = EmailSent.objects.all()
        # Before deleting emails there should be 3 stored emails
        self.assertEqual(stored_email.count(), 3)

        # Delete emails older than 15 days.
        older_than_days = 15
        deleted = delete_old_emails(older_than_days)
        self.assertEqual(deleted, 2)

        # After deleting there should be 1 stored email
        self.assertEqual(stored_email.count(), 1)


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
                test_dir / "soft_bounce_msg_id.json", encoding="utf-8"
            ) as soft_bounce_with_id,
        ):
            cls.soft_bounce_asset = json.load(soft_bounce)
            cls.soft_bounce_with_id_asset = json.load(soft_bounce_with_id)

    def send_signal(self, test_asset, event_name, signal) -> None:
        """Function to dispatch signal that mocks a SNS notification event
        :param test_asset: the json object that contains notification
        :param event_name: the signal event name
        :param signal: the signal corresponding to the event
        :return: None
        """
        # Prepare parameters
        message = json.loads(test_asset["Message"])
        mail_obj = message.get("mail")
        event_obj = message.get(event_name, {})

        # Send signal
        signal_kwargs = dict(
            sender=self,
            mail_obj=mail_obj,
            raw_message=test_asset,
        )
        signal_kwargs[f"{event_name}_obj"] = event_obj
        signal.send(**signal_kwargs)

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

        # Retrieve stored email, and it was linked to the CL user.
        stored_email = EmailSent.objects.all()
        self.assertEqual(stored_email.count(), 1)
        self.assertEqual(stored_email[0].user_id, user_email.id)

        # Update user email address
        user_email.email = "new_address@courtlistener.com"
        user_email.save()
        # Compose message from stored message and send.
        message = stored_email[0].convert_to_email_multipart()
        message.send()
        # Confirm if second email is sent
        self.assertEqual(len(mail.outbox), 2)

        message_sent = mail.outbox[1]
        message = message_sent.message()

        plaintext_body, html_body = get_email_body(message)

        # Compare second message sent with the original message content
        self.assertEqual(message_sent.subject, "This is the subject")
        self.assertEqual(plaintext_body, "Body goes here")
        self.assertEqual(html_body, "<p>Body goes here</p>")
        self.assertEqual(message_sent.from_email, "testing@courtlistener.com")
        self.assertEqual(message_sent.to, ["new_address@courtlistener.com"])
        self.assertEqual(message_sent.bcc, [])
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
        message = stored_email[0].convert_to_email_multipart()
        message.send()

        # Confirm if the second email is sent and compare its content.
        self.assertEqual(len(mail.outbox), 2)
        message_sent = mail.outbox[1]
        message = message_sent.message()
        plaintext_body, html_body = get_email_body(message)
        self.assertEqual(message_sent.subject, "This is the subject")
        self.assertEqual(plaintext_body, "Body goes here")
        self.assertEqual(message_sent.from_email, "testing@courtlistener.com")
        self.assertEqual(message_sent.to, ["anon_address@courtlistener.com"])

    def test_enqueue_email_backoff_event(self) -> None:
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
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 1)

        # The message should be enqueued as ENQUEUED status since there wasn't
        # a previous ENQUEUED message.
        self.assertEqual(failed_email[0].status, STATUS_TYPES.ENQUEUED)
        self.assertEqual(failed_email[0].stored_email.pk, stored_email[0].pk)

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
        self.assertEqual(stored_email.count(), 2)

        # Check the email is queued, now we have two FailedEmail objects.
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 2)

        # Confirm if the second FailedEmail object status is WAITING
        failed_email = FailedEmail.objects.filter(status=STATUS_TYPES.WAITING)
        self.assertEqual(failed_email[0].status, STATUS_TYPES.WAITING)
        self.assertEqual(failed_email[0].stored_email.pk, stored_email[1].pk)

    def test_enqueue_email_soft_bounce(self) -> None:
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

        email_2 = EmailMessage(
            "This is the subject 2",
            "Body goes here 2",
            "testing@courtlistener.com",
            ["bounce@simulator.amazonses.com"],
        )
        email_2.send()

        # Emails are sent
        self.assertEqual(len(mail.outbox), 2)
        # Retrieve the stored messages and update its message_id for testing
        stored_emails = list(EmailSent.objects.all())
        stored_emails[0].message_id = "5e9b3e8e-93c8-497f-abd4-00f6ddd566f0"
        stored_emails[0].save()

        stored_emails[1].message_id = "6e9b3e8f-93c8-497f-abd4-00f6ddd566f1"
        stored_emails[1].save()

        self.assertEqual(
            stored_emails[0].to, ["bounce@simulator.amazonses.com"]
        )
        self.assertEqual(
            str(stored_emails[0].message_id),
            "5e9b3e8e-93c8-497f-abd4-00f6ddd566f0",
        )
        self.assertEqual(
            str(stored_emails[1].message_id),
            "6e9b3e8f-93c8-497f-abd4-00f6ddd566f1",
        )

        # Create a backoff event for bounce@simulator.amazonses.com and
        # Message ID: 5e9b3e8e-93c8-497f-abd4-00f6ddd566f0
        self.send_signal(
            self.soft_bounce_with_id_asset, "bounce", signals.bounce_received
        )

        # Check the soft bounce message related is queued
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 1)

        self.assertEqual(failed_email[0].status, STATUS_TYPES.ENQUEUED)
        self.assertEqual(failed_email[0].stored_email.pk, stored_emails[0].pk)

        # Send another bounce notification for the same recipient
        # the related message has to be created as a WAITING status since we
        # have already an ENQUEUED message.
        # Message ID: 6e9b3e8f-93c8-497f-abd4-00f6ddd566f1
        self.send_signal(
            self.soft_bounce_asset, "bounce", signals.bounce_received
        )

        # Check the message is queued
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 2)

        failed_email = FailedEmail.objects.filter(status=STATUS_TYPES.WAITING)
        self.assertEqual(failed_email[0].status, STATUS_TYPES.WAITING)
        self.assertEqual(failed_email[0].stored_email.pk, stored_emails[1].pk)

    def test_enqueue_email_soft_bounce_duplicates(self) -> None:
        """This test checks if we receive a bounce event for the same message
        two or more times, we avoid duplicating FailedEmail objects.
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
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 1)

        self.assertEqual(failed_email[0].status, STATUS_TYPES.ENQUEUED)
        self.assertEqual(failed_email[0].stored_email.pk, stored_email.pk)

        # Send another bounce notification for the same recipient and same
        # message_id, the FailedEmail object shouldn't be duplicated
        self.send_signal(
            self.soft_bounce_with_id_asset, "bounce", signals.bounce_received
        )

        # If the message with the same ID has already been queued, avoid
        # creating one more FailedEmail object.
        failed_email = FailedEmail.objects.all()
        self.assertEqual(failed_email.count(), 1)

    def test_enqueue_email_after_check_deliverability(self) -> None:
        """This test checks if after a successful deliverability recipient's
        check WAITING failed messages are properly scheduled to be retried. And
        we can send it.
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
        failed_email_enqueued = FailedEmail.objects.filter(
            status=STATUS_TYPES.ENQUEUED
        )
        self.assertEqual(failed_email_enqueued.count(), 1)
        self.assertEqual(
            failed_email_enqueued[0].status, STATUS_TYPES.ENQUEUED
        )
        self.assertEqual(
            failed_email_enqueued[0].stored_email.pk, stored_email[0].pk
        )
        failed_email_waiting = FailedEmail.objects.filter(
            status=STATUS_TYPES.WAITING
        )
        self.assertEqual(failed_email_waiting.count(), 2)

        # Fake time 30 minutes after ENQUEUED FailedEmail was created
        fake_now_1 = now() + timedelta(minutes=30)
        with time_machine.travel(fake_now_1, tick=False):
            # Check recipient's deliverability and send failed emails
            handle_failing_emails()

        # After the deliverability check/send failed email, no new FailedEmail
        # is enqueued for delivery or sent since it's not time for it.
        self.assertEqual(failed_email_enqueued.count(), 1)
        self.assertEqual(failed_email_waiting.count(), 2)
        self.assertEqual(len(mail.outbox), 0)

        # Fake time, 1 hour before meeting the DELIVERABILITY_THRESHOLD time
        first_retry_future_time = 1 + settings.DELIVERABILITY_THRESHOLD
        fake_now_2 = now() + timedelta(hours=first_retry_future_time)
        with time_machine.travel(fake_now_2, tick=False):
            # Check recipient's deliverability and send failed emails
            handle_failing_emails()

        # After the deliverability check/send failed email, no new FailedEmail
        # are enqueued for delivery since it's not time for it. Only the
        # ENQUEUED FailedEmai is sent and marked as SUCCESSFUL.
        failed_email_successful = FailedEmail.objects.filter(
            status=STATUS_TYPES.SUCCESSFUL
        )
        # 1 FailedEmail now in SUCCESSFUL status
        self.assertEqual(failed_email_successful.count(), 1)
        # 1 FailedEmail is sent.
        self.assertEqual(len(mail.outbox), 1)
        # 2 FailedEmails continue in WAITING status
        self.assertEqual(failed_email_waiting.count(), 2)

        # Fake time, meeting the DELIVERABILITY_THRESHOLD time
        first_retry_future_time = 2 + settings.DELIVERABILITY_THRESHOLD
        fake_now_3 = now() + timedelta(hours=first_retry_future_time)
        with time_machine.travel(fake_now_3, tick=False):
            # Check recipient's deliverability and send failed emails
            handle_failing_emails()

        # After the deliverability check/send failed email, WAITING FailedEmail
        # are ENQUEUED_DELIVERY, sent them and marked as SUCCESSFUL.
        self.assertEqual(failed_email_successful.count(), 3)
        self.assertEqual(len(mail.outbox), 3)

    def test_retry_datetime(self) -> None:
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

        backoff = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
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

        # Fake time DELIVERABILITY_THRESHOLD hours after backoff event expires
        first_retry_future_time = 2 + settings.DELIVERABILITY_THRESHOLD
        fake_now_1 = now() + timedelta(hours=first_retry_future_time)
        with time_machine.travel(fake_now_1, tick=False):
            # Check recipient's deliverability and send failed emails
            handle_failing_emails()
            fake_now_time = now()

        # WAITING FailedEmail objects were scheduled with
        # ENQUEUED_DELIVERY status and then sent, now in SUCCESSFUL status
        failed_email = FailedEmail.objects.filter(
            status=STATUS_TYPES.SUCCESSFUL
        ).order_by("next_retry_date")
        self.assertEqual(failed_email.count(), 4)

        # Failed messages after a successful deliverability recipient's check
        # should be granted to be sent from now()
        expected_datetime = fake_now_time

        self.assertEqual(
            failed_email[1].next_retry_date.strftime("%Y-%m-%d %H:%M:%S"),
            expected_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.assertEqual(
            failed_email[2].next_retry_date.strftime("%Y-%m-%d %H:%M:%S"),
            expected_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.assertEqual(
            failed_email[3].next_retry_date.strftime("%Y-%m-%d %H:%M:%S"),
            expected_datetime.strftime("%Y-%m-%d %H:%M:%S"),
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
        message = json.loads(test_asset["Message"])
        mail_obj = message.get("mail")
        event_obj = message.get(event_name, {})

        # Send signal
        signal_kwargs = dict(
            sender=self,
            mail_obj=mail_obj,
            raw_message=test_asset,
        )
        signal_kwargs[f"{event_name}_obj"] = event_obj
        signal.send(**signal_kwargs)

    def test_multiple_bounce_subtypes(self) -> None:
        """This test checks if we can assign properly the bounce subtype for
        EmailFlag objects
        """

        # Trigger a hard bounce notification event
        self.send_signal(
            self.no_email_hard_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BAN,
        )
        # The bounce subtype should be NOEMAIL
        self.assertEqual(
            email_ban[0].notification_subtype, EMAIL_NOTIFICATIONS.NO_EMAIL
        )

        # Trigger a soft bounce notification event
        self.send_signal(
            self.mail_box_full_soft_bounce_asset,
            "bounce",
            signals.bounce_received,
        )
        backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
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
        self.assertEqual(r.context.get("EMAIL_BAN_REASON"), None)

        user = self.user
        user.email = "bounce@simulator.amazonses.com"
        user.password = make_password("password")
        user.save()
        # Authenticate user
        login = self.client.login(username=user.username, password="password")
        r = self.client.get(path)

        # The user's email has no problems, no banner showed
        self.assertEqual(r.context.get("EMAIL_BAN_REASON"), None)

        # Trigger a soft bounce notification event
        self.send_signal(
            self.mail_box_full_soft_bounce_asset,
            "bounce",
            signals.bounce_received,
        )
        backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )
        self.assertEqual(backoff_event.count(), 1)
        r = self.client.get(path)

        # A mail_box_full soft bounce event should trigger a Transient broken
        # email banner, we have a msg and no EMAIL_BAN_PERMANENT
        self.assertEqual(r.context.get("EMAIL_BAN_PERMANENT"), False)
        self.assertNotEqual(r.context.get("EMAIL_BAN_REASON"), None)

        # Trigger a hard bounce notification event
        self.send_signal(
            self.hard_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BAN,
        )
        self.assertEqual(email_ban.count(), 1)
        r = self.client.get(path)
        # A hard bounce event should trigger a Permanent broken
        # email banner, we have a msg and EMAIL_BAN_PERMANENT
        self.assertNotEqual(r.context.get("EMAIL_BAN_REASON"), None)
        self.assertEqual(r.context.get("EMAIL_BAN_PERMANENT"), True)

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
        self.assertEqual(r.context.get("EMAIL_BAN_REASON"), None)

        # Trigger a complaint notification event
        self.send_signal(
            self.complaint_asset, "complaint", signals.complaint_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="complaint@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BAN,
        )
        self.assertEqual(email_ban.count(), 1)
        r = self.client.get(path)
        # A complaint event should trigger a Permanent broken
        # email banner, we have a msg and EMAIL_BAN_PERMANENT
        self.assertNotEqual(r.context.get("EMAIL_BAN_REASON"), None)
        self.assertEqual(r.context.get("EMAIL_BAN_PERMANENT"), True)

    def test_broken_email_address_banner_first_permanent(self) -> None:
        """This test checks if a Permanent broken email event comes first than
        Transient broken email event, Permanent banner will be prioritized,
        also checks if users change their email address the email broken banner
        should disappear.
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
        self.assertEqual(r.context.get("EMAIL_BAN_REASON"), None)

        # Trigger a hard bounce notification event
        self.send_signal(
            self.hard_bounce_asset, "bounce", signals.bounce_received
        )
        email_ban = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BAN,
        )
        self.assertEqual(email_ban.count(), 1)
        r = self.client.get(path)
        # A hard bounce event should trigger a Permanent broken
        # email banner, we have a msg and EMAIL_BAN_PERMANENT
        self.assertNotEqual(r.context.get("EMAIL_BAN_REASON"), None)
        self.assertEqual(r.context.get("EMAIL_BAN_PERMANENT"), True)

        # Trigger a soft bounce notification event
        self.send_signal(
            self.mail_box_full_soft_bounce_asset,
            "bounce",
            signals.bounce_received,
        )
        backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )
        self.assertEqual(backoff_event.count(), 1)
        r = self.client.get(path)
        # A backoff event is created but the Permanent broken email banner is
        # prioritized
        self.assertNotEqual(r.context.get("EMAIL_BAN_REASON"), None)
        self.assertEqual(r.context.get("EMAIL_BAN_PERMANENT"), True)

        # Simulate user changes their email address to solve the Permanent
        # email error.
        user.email = "new@simulator.amazonses.com"
        user.save()
        login = self.client.login(username=user.username, password="password")

        r = self.client.get(path)
        # The broken email banner is gone
        self.assertEqual(r.context.get("EMAIL_BAN_REASON"), None)

    def test_broken_email_banner_backoff_expired(self) -> None:
        """This test checks if once a backoff event expires it deactivates the
        Transient broken email banner.
        """

        path = reverse("show_results")
        user = self.user
        user.email = "bounce@simulator.amazonses.com"
        user.password = make_password("password")
        user.save()
        self.client.login(username=user.username, password="password")
        r = self.client.get(path)
        self.assertEqual(r.context.get("EMAIL_BAN_REASON"), None)

        # Trigger a soft bounce notification event
        self.send_signal(
            self.mail_box_full_soft_bounce_asset,
            "bounce",
            signals.bounce_received,
        )
        backoff_event = EmailFlag.objects.filter(
            email_address="bounce@simulator.amazonses.com",
            flag_type=FLAG_TYPES.BACKOFF,
        )
        self.assertEqual(backoff_event.count(), 1)
        r = self.client.get(path)

        # A mail_box_full soft bounce event should trigger a Transient broken
        # email banner, we have a msg and no EMAIL_BAN_PERMANENT
        self.assertEqual(r.context.get("EMAIL_BAN_PERMANENT"), False)
        self.assertNotEqual(r.context.get("EMAIL_BAN_REASON"), None)

        # Update next_retry_date two hours behind to simulate backoff event is
        # expired
        backoff_event.update(next_retry_date=now() - timedelta(hours=2))

        r = self.client.get(path)
        # The broken email banner is gone
        self.assertEqual(r.context.get("EMAIL_BAN_REASON"), None)


class MockResponse:
    """
    A class to Mock API response
    """

    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data


class MoosendTest(TestCase):
    email = "testing@courtlistener.com"  # Test email address

    def mock_subscribe_valid(*args, **kwargs):
        data = {
            "Code": 0,
            "Error": None,
            "Context": {
                "ID": "38fb8eb6-cca5-43d5-b61b-2c36334ad7d0",
                "Name": None,
                "Mobile": None,
                "Email": "testing@courtlistener.com",
                "CreatedOn": "/Date(1655320447877)/",
                "UpdatedOn": None,
                "UnsubscribedOn": None,
                "UnsubscribedFromID": None,
                "SubscribeType": 1,
                "SubscribeMethod": 2,
                "CustomFields": [],
                "RemovedOn": None,
                "Tags": [],
            },
        }

        return MockResponse(data, 200)

    def mock_unsubscribe_valid(*args, **kwargs):
        data = {"Code": 0, "Error": None, "Context": None}
        return MockResponse(data, 200)

    @mock.patch(
        "cl.users.tasks.requests.post", side_effect=mock_subscribe_valid
    )
    def test_subscribe(self, mocked_post) -> None:
        """This test checks that moosend mailing list subscription is successful"""
        logger = logging.getLogger("cl.users.tasks")
        action = "subscribe"
        with mock.patch.object(logger, "info") as mock_info:
            update_moosend_subscription.delay(self.email, action)
            # It's implemented like this because logging library is optimized to use %s
            # formatting style, avoids call  __str__() method automatically, also logs
            # from update_moosend_subscription are in %s style
            mock_info.assert_called_once_with(
                "Successfully completed '%s' action on '%s' in moosend.",
                action,
                self.email,
            )

    @mock.patch(
        "cl.users.tasks.requests.post", side_effect=mock_unsubscribe_valid
    )
    def test_unsubscribe(self, mocked_post) -> None:
        """This test checks that moosend mailing list unsubscription is successful"""
        logger = logging.getLogger("cl.users.tasks")
        action = "unsubscribe"
        with mock.patch.object(logger, "info") as mock_info:
            update_moosend_subscription.delay(self.email, action)
            # It's implemented like this because logging library is optimized to use %s
            # formatting style, avoids call __str__() method automatically, also logs
            # from update_moosend_subscription are in %s style
            mock_info.assert_called_once_with(
                "Successfully completed '%s' action on '%s' in moosend.",
                action,
                self.email,
            )


class WebhooksHTMXTests(APITestCase):
    """Check that API CRUD operations are working well for search webhooks."""

    @classmethod
    def setUpTestData(cls):
        cls.user_1 = UserFactory()
        cls.user_2 = UserFactory()

    def setUp(self) -> None:
        self.webhook_path = reverse("webhooks-list")
        self.client = make_client(self.user_1.pk)
        self.client_2 = make_client(self.user_2.pk)

    def tearDown(cls):
        Webhook.objects.all().delete()

    def make_a_webhook(
        self,
        client,
        url="https://example.com",
        event_type=WebhookEventType.DOCKET_ALERT,
        enabled=True,
    ):
        data = {
            "url": url,
            "event_type": event_type,
            "enabled": enabled,
        }
        return client.post(self.webhook_path, data)

    def test_make_an_webhook(self) -> None:
        """Can we make a webhook?"""

        # Make a webhook
        webhooks = Webhook.objects.all()
        response = self.make_a_webhook(self.client)
        self.assertEqual(webhooks.count(), 1)
        self.assertEqual(response.status_code, HTTP_201_CREATED)

        # New or updated webhook notification for admins should go out
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]
        self.assertIn("A webhook was created", message_sent.subject)

    def test_make_an_http_webhook_fails(self) -> None:
        """Can we avoid creating an HTTP webhook endpoint?"""

        # Make a webhook
        webhooks = Webhook.objects.all()
        response = self.make_a_webhook(self.client, url="http://example.com")
        # No webhook should be created since we don't allow HTTP endpoints.
        self.assertEqual(webhooks.count(), 0)
        self.assertEqual(response.status_code, HTTP_200_OK)

    def test_list_users_webhooks(self) -> None:
        """Can we list user's own webhooks?"""

        # Make a webhook for user_1
        self.make_a_webhook(self.client)

        webhook_path_list = reverse(
            "webhooks-list",
            kwargs={"format": "html"},
        )
        # Get the webhooks for user_1
        response = self.client.get(webhook_path_list)
        self.assertEqual(response.status_code, HTTP_200_OK)

    def test_delete_webhook(self) -> None:
        """Can we delete a webhook?
        Avoid users from deleting other users' webhooks.
        """

        # Make two webhooks for user_1
        self.make_a_webhook(
            self.client, event_type=WebhookEventType.DOCKET_ALERT
        )
        self.make_a_webhook(
            self.client, event_type=WebhookEventType.SEARCH_ALERT
        )

        webhooks = Webhook.objects.all()
        self.assertEqual(webhooks.count(), 2)

        webhook_1_path_detail = reverse(
            "webhooks-detail",
            kwargs={"pk": webhooks[0].pk, "format": "json"},
        )

        # Delete the webhook for user_1
        response = self.client.delete(webhook_1_path_detail)
        self.assertEqual(response.status_code, HTTP_204_NO_CONTENT)
        self.assertEqual(webhooks.count(), 1)

        webhook_2_path_detail = reverse(
            "webhooks-detail",
            kwargs={"pk": webhooks[0].pk, "format": "json"},
        )

        # user_2 tries to delete a user_1 webhook, it should fail
        response = self.client_2.delete(webhook_2_path_detail)
        self.assertEqual(response.status_code, HTTP_404_NOT_FOUND)
        self.assertEqual(webhooks.count(), 1)

    def test_webhook_detail(self) -> None:
        """Can we get the details of a webhook?
        Avoid users from getting other users' webhooks.
        """

        # Make one webhook for user_1
        self.make_a_webhook(self.client)
        webhooks = Webhook.objects.all()
        self.assertEqual(webhooks.count(), 1)
        webhook_1_path_detail = reverse(
            "webhooks-detail",
            kwargs={"pk": webhooks[0].pk, "format": "html"},
        )

        # Get the webhook detail for user_1
        response = self.client.get(webhook_1_path_detail)
        self.assertEqual(response.status_code, HTTP_200_OK)

        # user_2 tries to get user_1 webhook, it should fail
        response = self.client_2.get(webhook_1_path_detail)
        self.assertEqual(response.status_code, HTTP_404_NOT_FOUND)

    def test_webhook_update(self) -> None:
        """Can we update a webhook?"""

        # Make one webhook for user_1
        self.make_a_webhook(self.client)
        webhooks = Webhook.objects.all()
        self.assertEqual(webhooks.count(), 1)

        # New or updated webhook notification for admins should go out
        self.assertEqual(len(mail.outbox), 1)
        message_sent = mail.outbox[0]
        self.assertIn("A webhook was created", message_sent.subject)

        webhook_1_path_detail = reverse(
            "webhooks-detail",
            kwargs={"pk": webhooks[0].pk, "format": "json"},
        )

        # Update the webhook
        data_updated = {
            "url": "https://example.com/updated",
            "event_type": webhooks[0].event_type,
            "enabled": webhooks[0].enabled,
        }
        response = self.client.put(webhook_1_path_detail, data_updated)

        # Check that the webhook was updated
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(webhooks[0].url, "https://example.com/updated")

        # New or updated webhook notification for admins should go out
        self.assertEqual(len(mail.outbox), 2)
        message_sent = mail.outbox[1]
        self.assertIn("A webhook was updated", message_sent.subject)

    def test_send_webhook_test(self) -> None:
        """Can we send a test webhook event?"""

        # Make one webhook for user_1
        self.make_a_webhook(self.client)
        webhooks = Webhook.objects.all()
        self.assertEqual(webhooks.count(), 1)

        webhook_1_path_test = reverse(
            "webhooks-test-webhook",
            kwargs={"pk": webhooks[0].pk, "format": "json"},
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockPostResponse(
                200, mock_raw=True
            ),
        ):
            response = self.client.post(webhook_1_path_test, {})
        # Compare the test webhook event data.
        self.assertEqual(response.status_code, HTTP_200_OK)
        webhook_event = WebhookEvent.objects.all().order_by("date_created")
        self.assertEqual(webhook_event[0].status_code, HTTP_200_OK)
        self.assertEqual(webhook_event[0].debug, True)
        self.assertEqual(
            webhook_event[0].content["payload"]["results"][0]["id"], 2208776613
        )

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockPostResponse(
                500, mock_raw=True
            ),
        ):
            response = self.client.post(webhook_1_path_test, {})
        # Compare the test webhook event data.
        self.assertEqual(len(webhook_event), 2)
        self.assertEqual(
            webhook_event[1].status_code, HTTP_500_INTERNAL_SERVER_ERROR
        )
        self.assertEqual(webhook_event[1].debug, True)
        self.assertEqual(
            webhook_event[1].content["payload"]["results"][0]["id"], 2208776613
        )
        # Webhook failure count shouldn't be increased by a webhook test event
        self.assertEqual(webhook_event[1].webhook.failure_count, 0)

    def test_list_webhook_events(self) -> None:
        """Can we list the user's webhook events?"""

        da_webhook = WebhookFactory(
            user=self.user_2,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        WebhookEventFactory(
            webhook=da_webhook,
        )

        webhook_event_path_list = reverse(
            "webhook_events-list",
            kwargs={"format": "html"},
        )

        webhooks = Webhook.objects.all()
        self.assertEqual(webhooks.count(), 1)

        # Get the webhooks for user_1
        response = self.client.get(webhook_event_path_list)
        self.assertEqual(response.status_code, HTTP_200_OK)
        # There shouldn't be results for user_1
        self.assertEqual(response.content, b"\n\n")

        sa_webhook = WebhookFactory(
            user=self.user_1,
            event_type=WebhookEventType.SEARCH_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        WebhookEventFactory(
            webhook=sa_webhook,
        )

        self.assertEqual(webhooks.count(), 2)

        # Get the webhooks for user_1
        response = self.client.get(webhook_event_path_list)
        self.assertEqual(response.status_code, HTTP_200_OK)
        # There should be results for user_1
        self.assertNotEqual(response.content, b"\n\n")
