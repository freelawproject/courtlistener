import json
from collections import defaultdict
from datetime import datetime, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import time_machine
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import AsyncClient, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import now
from lxml import html
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_404_NOT_FOUND,
)
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator
from waffle.testutils import override_switch

from cl.alerts.factories import AlertFactory, DocketAlertWithParentsFactory
from cl.alerts.management.commands.cl_send_scheduled_alerts import (
    DAYS_TO_DELETE,
    get_cut_off_date,
)
from cl.alerts.management.commands.handle_old_docket_alerts import (
    build_user_report,
)
from cl.alerts.models import (
    SCHEDULED_ALERT_HIT_STATUS,
    SEARCH_TYPES,
    Alert,
    DocketAlert,
    RealTimeQueue,
    ScheduledAlertHit,
)
from cl.alerts.tasks import (
    get_docket_notes_and_tags_by_user,
    send_alert_and_webhook,
)
from cl.alerts.utils import InvalidDateError, percolate_document
from cl.api.factories import WebhookFactory
from cl.api.models import (
    WEBHOOK_EVENT_STATUS,
    Webhook,
    WebhookEvent,
    WebhookEventType,
)
from cl.audio.factories import AudioWithParentsFactory
from cl.audio.models import Audio
from cl.donate.factories import DonationFactory
from cl.donate.models import Donation
from cl.favorites.factories import NoteFactory, UserTagFactory
from cl.lib.test_helpers import EmptySolrTestCase, SimpleUserDataMixin
from cl.search.documents import AudioDocument, AudioPercolator
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    OpinionWithParentsFactory,
)
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    Court,
    Docket,
    DocketEntry,
    Opinion,
    RECAPDocument,
)
from cl.search.tasks import add_items_to_solr
from cl.stats.models import Stat
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import APITestCase, ESIndexTestCase, TestCase
from cl.tests.utils import MockResponse, make_client
from cl.users.factories import UserFactory, UserProfileWithParentsFactory


class AlertTest(SimpleUserDataMixin, TestCase):
    fixtures = ["test_court.json"]

    def setUp(self) -> None:
        # Set up some handy variables
        self.alert_params = {
            "query": "q=asdf",
            "name": "dummy alert",
            "rate": "dly",
        }
        self.alert = Alert.objects.create(user_id=1001, **self.alert_params)

    def tearDown(self) -> None:
        Alert.objects.all().delete()

    async def test_create_alert(self) -> None:
        """Can we create an alert by sending a post?"""
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )
        r = await self.async_client.post(
            reverse("show_results"), self.alert_params, follow=True
        )
        self.assertEqual(r.redirect_chain[0][1], 302)
        self.assertIn("successfully", r.content.decode())
        await self.async_client.alogout()

    async def test_fail_gracefully(self) -> None:
        """Do we fail gracefully when an invalid alert form is sent?"""
        # Use a copy to shield other tests from changes.
        bad_alert_params = self.alert_params.copy()
        # Break the form
        bad_alert_params.pop("query", None)
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )
        r = await self.async_client.post("/", bad_alert_params, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("error creating your alert", r.content.decode())
        await self.async_client.alogout()

    def test_new_alert_gets_secret_key(self) -> None:
        """When you create a new alert, does it get a secret key?"""
        self.assertTrue(self.alert.secret_key)

    async def test_are_alerts_disabled_when_the_link_is_visited(self) -> None:
        self.assertEqual(self.alert.rate, self.alert_params["rate"])
        await self.async_client.get(
            reverse("disable_alert", args=[self.alert.secret_key])
        )
        await self.alert.arefresh_from_db()
        self.assertEqual(self.alert.rate, "off")

    async def test_are_alerts_enabled_when_the_link_is_visited(self) -> None:
        self.assertEqual(self.alert.rate, self.alert_params["rate"])
        self.alert.rate = "off"
        new_rate = "wly"
        path = reverse("enable_alert", args=[self.alert.secret_key])
        await self.async_client.get(f"{path}?rate={new_rate}")
        await self.alert.arefresh_from_db()
        self.assertEqual(self.alert.rate, new_rate)


class DocketAlertTest(TestCase):
    """Do docket alerts work properly?"""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = UserFactory()
        cls.court = Court.objects.get(id="scotus")

        # Create a DOCKET_ALERT webhook
        cls.webhook = WebhookFactory(
            user=cls.user,
            event_type=WebhookEventType.DOCKET_ALERT,
            url="https://example.com/",
            enabled=True,
        )

    def setUp(self) -> None:
        self.before = now()
        # Create a new docket
        self.docket = Docket.objects.create(
            source=Docket.RECAP,
            court_id="scotus",
            pacer_case_id="asdf",
            docket_number="12-cv-02354",
            case_name="Vargas v. Wilkins",
        )

        # Add an alert for it
        DocketAlert.objects.create(docket=self.docket, user=self.user)

        # Add a new docket entry to it
        de = DocketEntry.objects.create(docket=self.docket, entry_number=1)
        RECAPDocument.objects.create(
            docket_entry=de,
            document_type=RECAPDocument.PACER_DOCUMENT,
            document_number=1,
            pacer_doc_id="232322332",
            is_available=False,
        )
        self.after = now()

    def tearDown(self) -> None:
        Docket.objects.all().delete()
        DocketAlert.objects.all().delete()
        DocketEntry.objects.all().delete()

    def test_triggering_docket_alert(self) -> None:
        """Does the alert trigger when it should?"""
        send_alert_and_webhook(self.docket.pk, self.before)

        # Does the alert go out? It should.
        self.assertEqual(len(mail.outbox), 1)

    def test_nothing_happens_for_timers_after_de_creation(self) -> None:
        """Do we avoid sending alerts for timers after the de was created?"""
        send_alert_and_webhook(self.docket.pk, self.after)

        # Do zero emails go out? None should.
        self.assertEqual(len(mail.outbox), 0)

    @mock.patch(
        "cl.api.webhooks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse(200, mock_raw=True),
    )
    def test_triggering_docket_webhook(self, mock_post) -> None:
        """Does the docket alert trigger the DocketAlert Webhook?"""
        send_alert_and_webhook(self.docket.pk, self.before)
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)

        # Does the webhook was triggered?
        self.assertEqual(webhook_triggered.count(), 1)
        content = webhook_triggered.first().content
        # Compare the content of the webhook to the recap document
        pacer_doc_id = content["payload"]["results"][0]["recap_documents"][0][
            "pacer_doc_id"
        ]
        self.assertEqual("232322332", pacer_doc_id)
        self.assertEqual(
            webhook_triggered.first().event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )


class DisableDocketAlertTest(TestCase):
    """Do old docket alerts get disabled or alerted properly?"""

    fixtures = ["test_court.json"]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.alert = DocketAlertWithParentsFactory(
            docket__source=Docket.RECAP,
            docket__date_terminated="2020-01-01",
        )

    def backdate_alert(self) -> None:
        DocketAlert.objects.filter(pk=self.alert.pk).update(
            date_modified=now() - timedelta(days=365)
        )

    def test_alert_created_recently_termination_year_ago(self) -> None:
        self.alert.docket.date_terminated = now() - timedelta(days=365)
        self.alert.docket.save()

        report = build_user_report(self.alert.user)
        # This alert was recent (the test created it a few seconds ago),
        # so no actions should be taken
        self.assertEqual(
            report.total_count(),
            0,
            msg=f"Got dockets when we shouldn't have gotten any: {report.__dict__}",
        )

    def test_old_alert_recent_termination(self) -> None:
        """Flag it if alert is old and item was terminated 90-97 days ago"""
        self.backdate_alert()
        for i in range(90, 97):
            new_date_terminated = now() - timedelta(days=i)
            print(f"Trying a date_terminated of {new_date_terminated}")
            self.alert.docket.date_terminated = new_date_terminated
            self.alert.docket.save()
            report = build_user_report(self.alert.user, delete=True)
            self.assertEqual(report.old_dockets, [self.alert.docket])


class UnlimitedAlertsTest(TestCase):
    def test_create_one_alert(self) -> None:
        """Can a user create an alert?"""
        up = UserProfileWithParentsFactory()
        self.assertTrue(
            up.can_make_another_alert,
            msg="User with no alerts cannot make its first alert.",
        )

        # Make another alert, and see if the user can still make yet another
        _ = DocketAlertWithParentsFactory(
            user=up.user,
            docket__source=Docket.RECAP,
            docket__date_terminated="2020-01-01",
        )

        self.assertTrue(
            up.can_make_another_alert,
            msg="User with one alert cannot make another.",
        )

    @override_settings(MAX_FREE_DOCKET_ALERTS=0)
    def test_email_grantlist(self) -> None:
        """Do you get unlimited alerts by email address?"""
        up = UserProfileWithParentsFactory(user__email="juno@free.law")
        self.assertFalse(
            up.unlimited_docket_alerts,
            msg="User has unlimited alerts, but shouldn't.",
        )
        self.assertFalse(
            up.email_grants_unlimited_docket_alerts,
            msg="Grantlist allowed even though email should not be on list.",
        )
        self.assertFalse(
            up.is_monthly_donor,
            msg="User is marked as monthly donor, but isn't.",
        )
        self.assertFalse(
            up.can_make_another_alert,
            msg="Was able to make alerts even though the max free "
            "alerts was overridden to zero.",
        )
        with self.settings(UNLIMITED_DOCKET_ALERT_EMAIL_DOMAINS=["free.law"]):
            self.assertTrue(
                up.email_grants_unlimited_docket_alerts,
                msg="Grantlist denied even though email should be allowed. ",
            )
            self.assertTrue(
                up.can_make_another_alert,
                msg="Unable to make an alert even though user's email is "
                "granted unlimited docket alerts",
            )


class AlertSeleniumTest(BaseSeleniumTest):
    fixtures = ["test_court.json"]

    def setUp(self) -> None:
        # Set up some handy variables
        self.async_client = AsyncClient()
        self.alert_params = {
            "query": "q=asdf",
            "name": "dummy alert",
            "rate": "dly",
        }
        UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )
        super().setUp()

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_edit_alert(self) -> None:
        """Can we edit the alert and see the message about it being edited?"""
        user = User.objects.get(username="pandora")
        alert = Alert(
            user=user,
            name=self.alert_params["name"],
            query=self.alert_params["query"],
            rate=self.alert_params["rate"],
        )
        alert.save()

        # Pan tries to edit their alert
        url = "{url}{path}?{q}&edit_alert={pk}".format(
            url=self.live_server_url,
            path=reverse("show_results"),
            q=alert.query,
            pk=alert.pk,
        )
        self.browser.get(url)

        # But winds up at the sign in form
        self.assertIn(reverse("sign-in"), self.browser.current_url)

        # So Pan signs in.
        self.browser.find_element(By.ID, "username").send_keys("pandora")
        self.browser.find_element(By.ID, "password").send_keys("password")
        self.browser.find_element(By.ID, "password").submit()

        # And gets redirected to the SERP where they see a notice about their
        # alert being edited.
        self.assert_text_in_node("editing your alert", "body")


class AlertAPITests(APITestCase):
    """Check that API CRUD operations are working well for search alerts."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user_1 = UserFactory()
        cls.user_2 = UserFactory()

    def setUp(self) -> None:
        self.alert_path = reverse("alert-list", kwargs={"version": "v3"})
        self.client = make_client(self.user_1.pk)
        self.client_2 = make_client(self.user_2.pk)

    def tearDown(cls):
        Alert.objects.all().delete()

    def make_an_alert(
        self,
        client,
        alert_name="testing_name",
        alert_query="q=testing_query&",
        alert_rate="dly",
    ):
        data = {
            "name": alert_name,
            "query": alert_query,
            "rate": alert_rate,
        }
        return client.post(self.alert_path, data, format="json")

    def test_make_an_alert(self) -> None:
        """Can we make an alert?"""

        # Make a simple search alert
        search_alert = Alert.objects.all()
        response = self.make_an_alert(self.client)
        self.assertEqual(search_alert.count(), 1)
        self.assertEqual(response.status_code, HTTP_201_CREATED)

    def test_list_users_alerts(self) -> None:
        """Can we list user's own alerts?"""

        # Make two alerts for user_1
        self.make_an_alert(self.client, alert_name="alert_1")
        self.make_an_alert(self.client, alert_name="alert_2")

        # Make one alert for user_2
        self.make_an_alert(self.client_2, alert_name="alert_3")

        # Get the alerts for user_1, should be 2
        response = self.client.get(self.alert_path)
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(response.json()["count"], 2)

        # Get the alerts for user_2, should be 1
        response_2 = self.client_2.get(self.alert_path)
        self.assertEqual(response_2.status_code, HTTP_200_OK)
        self.assertEqual(response_2.json()["count"], 1)

    def test_delete_alert(self) -> None:
        """Can we delete an alert?
        Avoid users from deleting other users' alerts.
        """

        # Make two alerts for user_1
        alert_1 = self.make_an_alert(self.client, alert_name="alert_1")
        alert_2 = self.make_an_alert(self.client, alert_name="alert_2")

        search_alert = Alert.objects.all()
        self.assertEqual(search_alert.count(), 2)

        alert_1_path_detail = reverse(
            "alert-detail",
            kwargs={"pk": alert_1.json()["id"], "version": "v3"},
        )

        # Delete the alert for user_1
        response = self.client.delete(alert_1_path_detail)
        self.assertEqual(response.status_code, HTTP_204_NO_CONTENT)
        self.assertEqual(search_alert.count(), 1)

        alert_2_path_detail = reverse(
            "alert-detail",
            kwargs={"pk": alert_2.json()["id"], "version": "v3"},
        )

        # user_2 tries to delete a user_1 alert, it should fail
        response = self.client_2.delete(alert_2_path_detail)
        self.assertEqual(response.status_code, HTTP_404_NOT_FOUND)
        self.assertEqual(search_alert.count(), 1)

    def test_alert_detail(self) -> None:
        """Can we get the details of an alert?
        Avoid users from getting other users' alerts.
        """

        # Make one alerts for user_1
        alert_1 = self.make_an_alert(self.client, alert_name="alert_1")
        search_alert = Alert.objects.all()
        self.assertEqual(search_alert.count(), 1)
        alert_1_path_detail = reverse(
            "alert-detail",
            kwargs={"pk": alert_1.json()["id"], "version": "v3"},
        )

        # Get the alert detail for user_1
        response = self.client.get(alert_1_path_detail)
        self.assertEqual(response.status_code, HTTP_200_OK)

        # user_2 tries to get user_1 alert, it should fail
        response = self.client_2.get(alert_1_path_detail)
        self.assertEqual(response.status_code, HTTP_404_NOT_FOUND)

    def test_alert_update(self) -> None:
        """Can we update an alert?"""

        # Make one alerts for user_1
        alert_1 = self.make_an_alert(self.client, alert_name="alert_1")
        search_alert = Alert.objects.all()
        self.assertEqual(search_alert.count(), 1)
        alert_1_path_detail = reverse(
            "alert-detail",
            kwargs={"pk": alert_1.json()["id"], "version": "v3"},
        )

        # Update the alert
        data_updated = {
            "name": "alert_1_updated",
            "query": alert_1.json()["query"],
            "rate": alert_1.json()["rate"],
        }
        response = self.client.put(alert_1_path_detail, data_updated)

        # Check that the alert was updated
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(response.json()["name"], "alert_1_updated")
        self.assertEqual(response.json()["id"], alert_1.json()["id"])


class SearchAlertsWebhooksTest(ESIndexTestCase, EmptySolrTestCase):
    """Test Search Alerts Webhooks"""

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("alerts.Alert")
        cls.user_profile = UserProfileWithParentsFactory()
        cls.user_profile_1 = UserProfileWithParentsFactory()
        cls.donation = DonationFactory(
            donor=cls.user_profile.user,
            amount=20,
            status=Donation.PROCESSED,
            send_annual_reminder=True,
        )
        cls.webhook_enabled = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.SEARCH_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        cls.webhook_enabled_1 = WebhookFactory(
            user=cls.user_profile_1.user,
            event_type=WebhookEventType.SEARCH_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        cls.search_alert = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert O",
            query="type=o&stat_Non-Precedential=on",
        )
        cls.search_alert_rt = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert O rt",
            query="type=o&stat_Non-Precedential=on",
        )
        cls.search_alert_rt_1 = AlertFactory(
            user=cls.user_profile_1.user,
            rate=Alert.REAL_TIME,
            name="Test Alert O rt",
            query="type=o&stat_Non-Precedential=on",
        )
        cls.search_alert_oa = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert OA",
            query="type=oa",
        )
        cls.search_alert_o_wly = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.WEEKLY,
            name="Test Alert O wly",
            query="type=o&stat_Non-Precedential=on",
        )
        cls.search_alert_o_mly = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.MONTHLY,
            name="Test Alert O mly",
            query="type=o&stat_Non-Precedential=on",
        )

        cls.user_profile_2 = UserProfileWithParentsFactory()
        cls.webhook_disabled = WebhookFactory(
            user=cls.user_profile_2.user,
            event_type=WebhookEventType.SEARCH_ALERT,
            url="https://example.com/",
            enabled=False,
        )
        cls.search_alert_2 = AlertFactory(
            user=cls.user_profile_2.user,
            rate=Alert.DAILY,
            name="Test Alert O Disabled",
            query="type=o&stat_Non-Precedential=on",
        )
        cls.mock_date = now().replace(day=15, hour=0)
        with time_machine.travel(
            cls.mock_date, tick=False
        ), cls.captureOnCommitCallbacks(execute=True):
            cls.dly_opinion = OpinionWithParentsFactory.create(
                cluster__precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
                cluster__date_filed=now() - timedelta(hours=5),
            )
            with mock.patch(
                "cl.scrapers.tasks.microservice",
                side_effect=lambda *args, **kwargs: MockResponse(200, b"10"),
            ), mock.patch(
                "cl.lib.es_signal_processor.allow_es_audio_indexing",
                side_effect=lambda x, y: True,
            ):
                cls.dly_oral_argument = AudioWithParentsFactory.create(
                    case_name="Dly Test OA",
                    docket__date_argued=now() - timedelta(hours=5),
                )

            cls.wly_opinion = OpinionWithParentsFactory.create(
                cluster__precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
                cluster__date_filed=now() - timedelta(days=2),
            )
            cls.mly_opinion = OpinionWithParentsFactory.create(
                cluster__precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
                cluster__date_filed=now() - timedelta(days=25),
            )

    def setUp(self) -> None:
        super().setUp()
        obj_types = {
            "audio.Audio": Audio,
            "search.Opinion": Opinion,
        }
        for obj_name, obj_type in obj_types.items():
            ids = obj_type.objects.all().values_list("pk", flat=True)
            add_items_to_solr(ids, obj_name, force_commit=True)

    def test_send_search_alert_webhooks(self):
        """Can we send search alert webhooks for Opinions and Oral Arguments
        independently?
        """

        webhooks_enabled = Webhook.objects.filter(enabled=True)
        self.assertEqual(len(webhooks_enabled), 2)
        search_alerts = Alert.objects.all()
        self.assertEqual(len(search_alerts), 7)

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            with time_machine.travel(self.mock_date, tick=False):
                # Send Solr Alerts (Except OA)
                call_command("cl_send_alerts", rate="dly")
                # Send ES Alerts (Only OA for now)
                call_command("cl_send_scheduled_alerts", rate="dly")

        # Three search alerts should be sent:
        # Two opinion alerts to user_profile and one to user_profile_2 (Solr)
        # One oral argument alert to user_profile (ES)
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(mail.outbox[0].to[0], self.user_profile.user.email)
        self.assertIn("daily opinion alert", mail.outbox[0].body)
        self.assertEqual(mail.outbox[1].to[0], self.user_profile_2.user.email)
        self.assertIn("daily opinion alert", mail.outbox[1].body)
        self.assertEqual(mail.outbox[2].to[0], self.user_profile.user.email)
        self.assertIn("daily oral argument alert ", mail.outbox[2].body)

        # Two webhook events should be sent, both of them to user_profile user
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 2)

        alert_data = {
            self.search_alert.pk: {
                "alert": self.search_alert,
                "result": self.dly_opinion.cluster,
            },
            self.search_alert_oa.pk: {
                "alert": self.search_alert_oa,
                "result": self.dly_oral_argument,
            },
        }

        for webhook_sent in webhook_events:
            self.assertEqual(
                webhook_sent.event_status,
                WEBHOOK_EVENT_STATUS.SUCCESSFUL,
            )
            self.assertEqual(
                webhook_sent.webhook.user,
                self.user_profile.user,
            )
            content = webhook_sent.content
            # Check if the webhook event payload is correct.
            self.assertEqual(
                content["webhook"]["event_type"],
                WebhookEventType.SEARCH_ALERT,
            )

            alert_data_compare = alert_data[content["payload"]["alert"]["id"]]
            self.assertEqual(
                content["payload"]["alert"]["name"],
                alert_data_compare["alert"].name,
            )
            self.assertEqual(
                content["payload"]["alert"]["query"],
                alert_data_compare["alert"].query,
            )
            self.assertEqual(
                content["payload"]["alert"]["rate"],
                alert_data_compare["alert"].rate,
            )
            self.assertEqual(
                content["payload"]["results"][0]["caseName"],
                alert_data_compare["result"].case_name,
            )

    def test_send_search_alert_webhooks_rates(self):
        """Can we send search alert webhooks for different alert rates?"""
        with time_machine.travel(
            self.mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            # Get ready the RT opinion for the test.
            rt_opinion = OpinionWithParentsFactory.create(
                cluster__precedential_status=PRECEDENTIAL_STATUS.UNPUBLISHED,
                cluster__date_filed=now(),
            )
            RealTimeQueue.objects.create(
                item_type=SEARCH_TYPES.OPINION, item_pk=rt_opinion.pk
            )
            add_items_to_solr(
                [
                    rt_opinion.pk,
                ],
                "search.Opinion",
                force_commit=True,
            )

        webhooks_enabled = Webhook.objects.filter(enabled=True)
        self.assertEqual(len(webhooks_enabled), 2)
        search_alerts = Alert.objects.all()
        self.assertEqual(len(search_alerts), 7)

        # (rate, events expected, number of search results expected per event)
        # The number of expected results increases with every iteration since
        # daily events include results created for the RT test, weekly results
        # include results from RT and Daily tests, and so on...
        rates = [
            (Alert.REAL_TIME, 2, 1),  # 2 expected webhook events, 1 Opinion RT
            # Alert (search_alert_rt) + 1 OA Daily Alert, triggered by ES.
            (Alert.DAILY, 1, 2),
            (Alert.WEEKLY, 1, 3),
            (Alert.MONTHLY, 1, 4),
        ]
        for rate, events, results in rates:
            with mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ):
                # Monthly alerts cannot be run on the 29th, 30th or 31st.
                with time_machine.travel(self.mock_date, tick=False):
                    # Send Solr Alerts (Except OA)
                    call_command("cl_send_alerts", rate=rate)
                    # Send ES Alerts (Only OA for now)
                    call_command("cl_send_scheduled_alerts", rate=rate)

            webhook_events = WebhookEvent.objects.all()
            self.assertEqual(len(webhook_events), events)

            for webhook_sent in webhook_events:
                self.assertEqual(
                    webhook_sent.event_status,
                    WEBHOOK_EVENT_STATUS.SUCCESSFUL,
                )
                self.assertEqual(
                    webhook_sent.webhook.user,
                    self.user_profile.user,
                )
                content = webhook_sent.content
                # Check if the webhook event payload is correct.
                self.assertEqual(
                    content["webhook"]["event_type"],
                    WebhookEventType.SEARCH_ALERT,
                )
                alert_to_compare = Alert.objects.get(
                    pk=content["payload"]["alert"]["id"]
                )
                self.assertEqual(
                    content["payload"]["alert"]["name"],
                    alert_to_compare.name,
                )
                self.assertEqual(
                    content["payload"]["alert"]["query"],
                    alert_to_compare.query,
                )

                # The oral argument webhook is sent independently not grouped
                # with opinions webhooks results.
                if content["payload"]["alert"]["query"] == "type=oa":
                    self.assertEqual(
                        len(content["payload"]["results"]),
                        1,
                    )
                    self.assertEqual(
                        content["payload"]["alert"]["rate"],
                        Alert.DAILY,
                    )
                else:
                    self.assertEqual(
                        len(content["payload"]["results"]),
                        results,
                    )
                    self.assertEqual(
                        content["payload"]["alert"]["rate"],
                        rate,
                    )
            webhook_events.delete()


class DocketAlertAPITests(APITestCase):
    """Check that API CRUD operations are working well for docket alerts."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user_1 = UserFactory()
        cls.user_2 = UserFactory()

        cls.court = Court.objects.get(id="scotus")
        cls.docket = DocketFactory(
            case_name="BARTON v. State Board for Rodgers Educator Certification",
            docket_number_core="0600078",
            docket_number="No. 06-11-00078-CV",
            court=cls.court,
        )
        cls.docket_1 = DocketFactory(
            case_name="Young v. State",
            docket_number_core="7101462",
            docket_number="No. 07-11-1462-CR",
            court=cls.court,
        )

    def setUp(self) -> None:
        self.docket_alert_path = reverse(
            "docket-alert-list", kwargs={"version": "v3"}
        )
        self.client = make_client(self.user_1.pk)
        self.client_2 = make_client(self.user_2.pk)

    def tearDown(cls):
        DocketAlert.objects.all().delete()

    def make_a_docket_alert(
        self,
        client,
        docket_pk=None,
    ):
        docket_id = self.docket.id
        if docket_pk:
            docket_id = docket_pk

        data = {
            "docket": docket_id,
        }
        return client.post(self.docket_alert_path, data, format="json")

    def test_make_a_docket_alert(self) -> None:
        """Can we make a docket alert?"""

        # Make a simple docket alert
        docket_alert = DocketAlert.objects.all()
        ten_days_ahead = now() + timedelta(days=10)
        with time_machine.travel(ten_days_ahead, tick=False):
            response = self.make_a_docket_alert(self.client)
        self.assertEqual(docket_alert[0].date_modified, ten_days_ahead)
        self.assertEqual(docket_alert.count(), 1)
        self.assertEqual(response.status_code, HTTP_201_CREATED)

    def test_list_users_docket_alerts(self) -> None:
        """Can we list user's own alerts?"""

        # Make two docket alerts for user_1
        self.make_a_docket_alert(self.client)
        self.make_a_docket_alert(self.client, docket_pk=self.docket_1.id)

        # Make one docket alert for user_2
        self.make_a_docket_alert(self.client_2)

        # Get the docket alerts for user_1, should be 2
        response = self.client.get(self.docket_alert_path)
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(response.json()["count"], 2)

        # Get the docket alerts for user_2, should be 1
        response_2 = self.client_2.get(self.docket_alert_path)
        self.assertEqual(response_2.status_code, HTTP_200_OK)
        self.assertEqual(response_2.json()["count"], 1)

    def test_delete_docket_alert(self) -> None:
        """Can we delete an docket alert?
        Avoid users from deleting other users' docket alerts.
        """

        # Make two docket alerts for user_1
        docket_alert_1 = self.make_a_docket_alert(self.client)
        docket_alert_2 = self.make_a_docket_alert(
            self.client, docket_pk=self.docket_1.id
        )

        docket_alert = DocketAlert.objects.all()
        self.assertEqual(docket_alert.count(), 2)

        docket_alert_1_path_detail = reverse(
            "docket-alert-detail",
            kwargs={"pk": docket_alert_1.json()["id"], "version": "v3"},
        )

        # Delete the docket_alert for user_1
        response = self.client.delete(docket_alert_1_path_detail)
        self.assertEqual(response.status_code, HTTP_204_NO_CONTENT)
        self.assertEqual(docket_alert.count(), 1)

        docket_alert_2_path_detail = reverse(
            "docket-alert-detail",
            kwargs={"pk": docket_alert_2.json()["id"], "version": "v3"},
        )

        # user_2 tries to delete a user_1 docket alert, it should fail
        response = self.client_2.delete(docket_alert_2_path_detail)
        self.assertEqual(response.status_code, HTTP_404_NOT_FOUND)
        self.assertEqual(docket_alert.count(), 1)

    def test_docket_alert_detail(self) -> None:
        """Can we get the details of a docket alert?
        Avoid users from getting other users' docket alerts.
        """

        # Make one docket alert for user_1
        docket_alert_1 = self.make_a_docket_alert(self.client)
        docket_alert = DocketAlert.objects.all()
        self.assertEqual(docket_alert.count(), 1)
        docket_alert_1_path_detail = reverse(
            "docket-alert-detail",
            kwargs={"pk": docket_alert_1.json()["id"], "version": "v3"},
        )

        # Get the docket alert detail for user_1
        response = self.client.get(docket_alert_1_path_detail)
        self.assertEqual(response.status_code, HTTP_200_OK)

        # user_2 tries to get user_1 docket alert, it should fail
        response = self.client_2.get(docket_alert_1_path_detail)
        self.assertEqual(response.status_code, HTTP_404_NOT_FOUND)

    def test_docket_alert_update(self) -> None:
        """Can we update a docket alert?"""

        # Make one alerts for user_1
        docket_alert_1 = self.make_a_docket_alert(self.client)
        docket_alert = DocketAlert.objects.all()
        self.assertEqual(docket_alert.count(), 1)
        self.assertEqual(docket_alert[0].alert_type, DocketAlert.SUBSCRIPTION)
        docket_alert_1_path_detail = reverse(
            "docket-alert-detail",
            kwargs={"pk": docket_alert_1.json()["id"], "version": "v3"},
        )

        # Update the docket alert
        data_updated = {
            "docket": self.docket.pk,
            "alert_type": DocketAlert.UNSUBSCRIPTION,
        }

        ten_days_ahead = now() + timedelta(days=10)
        with time_machine.travel(ten_days_ahead, tick=False):
            response = self.client.put(
                docket_alert_1_path_detail, data_updated
            )

        # Confirm date_modified is updated on put method
        self.assertEqual(docket_alert[0].date_modified, ten_days_ahead)

        # Check that the alert was updated
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(
            response.json()["alert_type"], DocketAlert.UNSUBSCRIPTION
        )
        self.assertEqual(response.json()["id"], docket_alert_1.json()["id"])

    def test_docket_alert_patch(self) -> None:
        """Can we update a docket alert?"""

        # Make one alerts for user_1
        docket_alert_1 = self.make_a_docket_alert(self.client)
        docket_alert = DocketAlert.objects.all()
        self.assertEqual(docket_alert.count(), 1)
        self.assertEqual(docket_alert[0].alert_type, DocketAlert.SUBSCRIPTION)
        docket_alert_1_path_detail = reverse(
            "docket-alert-detail",
            kwargs={"pk": docket_alert_1.json()["id"], "version": "v3"},
        )

        # Update the docket alert
        data_updated = {
            "alert_type": DocketAlert.UNSUBSCRIPTION,
        }

        ten_days_ahead = now() + timedelta(days=10)
        with time_machine.travel(ten_days_ahead, tick=False):
            response = self.client.patch(
                docket_alert_1_path_detail, data_updated
            )

        # Confirm date_modified is updated on patch method
        self.assertEqual(docket_alert[0].date_modified, ten_days_ahead)

        # Check that the alert was updated
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertEqual(
            response.json()["alert_type"], DocketAlert.UNSUBSCRIPTION
        )
        self.assertEqual(response.json()["id"], docket_alert_1.json()["id"])

        # Patch docket alert
        data_updated = {"docket": self.docket_1.pk}
        eleven_days_ahead = now() + timedelta(days=11)
        with time_machine.travel(eleven_days_ahead, tick=False):
            response = self.client.patch(
                docket_alert_1_path_detail, data_updated
            )

        # date_modified is updated on patch method when updating any other field
        self.assertEqual(docket_alert[0].date_modified, eleven_days_ahead)


class OldDocketAlertsReportToggleTest(TestCase):
    """Do old docket alerts date_modified is properly updated when toggling the
    alert and correctly reported by OldAlertReport?"""

    @classmethod
    def setUpTestData(cls):
        cls.user_profile = UserProfileWithParentsFactory()
        test_user = cls.user_profile.user
        test_user.password = make_password("password")
        test_user.save()

    def test_disable_docket_alerts_without_deleting_them(self):
        """Can we disable docket alerts that should be disabled only by
        changing their alert_type to "Unsubscription"?
        """

        # Create an old unsubscription docket alert from a case terminated long
        # time ago.
        one_year_ago = now() - timedelta(days=365)
        with time_machine.travel(one_year_ago, tick=False):
            DocketAlertWithParentsFactory(
                docket__source=Docket.RECAP,
                docket__date_terminated="2020-01-01",
                user=self.user_profile.user,
                alert_type=DocketAlert.UNSUBSCRIPTION,
            )

        docket_alerts = DocketAlert.objects.all()
        active_docket_alerts = DocketAlert.objects.filter(
            alert_type=DocketAlert.SUBSCRIPTION
        )

        self.assertEqual(docket_alerts.count(), 1)
        self.assertEqual(active_docket_alerts.count(), 0)

        # Run the report, since the docket alert is "Unsubscription" no action
        # should be taken.
        report = build_user_report(self.user_profile.user, delete=True)
        self.assertEqual(report.total_count(), 0)

        # Create an old subscription docket alert from a case terminated long
        # time ago.
        with time_machine.travel(one_year_ago, tick=False):
            DocketAlertWithParentsFactory(
                docket__source=Docket.RECAP,
                docket__date_terminated="2020-01-02",
                user=self.user_profile.user,
                alert_type=DocketAlert.SUBSCRIPTION,
            )

        self.assertEqual(docket_alerts.count(), 2)
        self.assertEqual(active_docket_alerts.count(), 1)

        # Run the report, now the old subscription docket alert should be
        # disabled changing its alert_type to "Unsubscription", not deleting it
        report = build_user_report(self.user_profile.user, delete=True)
        self.assertEqual(len(report.disabled_dockets), 1)
        self.assertEqual(report.total_count(), 1)
        self.assertEqual(active_docket_alerts.count(), 0)
        self.assertEqual(docket_alerts.count(), 2)

        # Run the report again, no new alerts to warn or disable.
        report = build_user_report(self.user_profile.user, delete=True)
        self.assertEqual(report.total_count(), 0)

    def test_old_docket_alert_report_timeline(self):
        """Can we properly warn and disable docket alerts based on their age
        considering their date_modified is updated when the alert_type change?
        """

        # Create today a subscription docket alert from a case terminated long
        # time ago.
        da = DocketAlertWithParentsFactory(
            docket__source=Docket.RECAP,
            docket__date_terminated="2020-01-01",
            docket__date_last_filing=None,
            user=self.user_profile.user,
            alert_type=DocketAlert.SUBSCRIPTION,
            date_last_hit=None,
        )
        docket_alerts = DocketAlert.objects.all()
        active_docket_alerts = DocketAlert.objects.filter(
            alert_type=DocketAlert.SUBSCRIPTION
        )

        # Run the report
        report = build_user_report(self.user_profile.user, delete=True)
        # After calling the report no warning should go out since it was just
        # created.
        self.assertEqual(report.total_count(), 0)
        self.assertEqual(docket_alerts.count(), 1)
        self.assertEqual(active_docket_alerts.count(), 1)

        # Simulate user disabling docket alert 60 days in the future.
        plus_sixty_days = now() + timedelta(days=60)
        with time_machine.travel(plus_sixty_days, tick=False):
            # User disabled Docket alert manually.
            da.alert_type = DocketAlert.UNSUBSCRIPTION
            da.save()

        da.refresh_from_db()
        # The alert_type and date_modified is updated.
        self.assertEqual(da.alert_type, DocketAlert.UNSUBSCRIPTION)
        self.assertEqual(da.date_modified, plus_sixty_days)

        # Simulate user re-enabling docket alert 85 days in the future.
        plus_eighty_five_days = now() + timedelta(days=85)
        with time_machine.travel(plus_eighty_five_days, tick=False):
            # User re-enable Docket alert manually.
            da.alert_type = DocketAlert.SUBSCRIPTION
            da.save()

        da.refresh_from_db()
        # The alert_type and date_modified is updated.
        self.assertEqual(da.alert_type, DocketAlert.SUBSCRIPTION)
        self.assertEqual(da.date_modified, plus_eighty_five_days)

        # Report is run 95 days in the future, 10 days since docket alert was
        # re-enabled
        plus_ninety_five_days = now() + timedelta(days=95)
        with time_machine.travel(plus_ninety_five_days, tick=False):
            report = build_user_report(self.user_profile.user, delete=True)

        # After run the report 95 days in the future no warning should go out
        # since the docket alert was re-enabled 10 days ago.
        self.assertEqual(report.total_count(), 0)
        self.assertEqual(active_docket_alerts.count(), 1)

        # Report is run 268 days in the future, 183 days since docket alert was
        # re-enabled
        plus_two_hundred_sixty_eight_days = now() + timedelta(days=268)
        with time_machine.travel(
            plus_two_hundred_sixty_eight_days, tick=False
        ):
            report = build_user_report(self.user_profile.user, delete=True)

        # After run the report 268 days in the future a warning should go out
        # but no alert should be disabled since the docket alert was re-enabled
        # 183 days ago.
        self.assertEqual(report.total_count(), 1)
        self.assertEqual(len(report.very_old_alerts), 1)
        self.assertEqual(active_docket_alerts.count(), 1)

        # Report is run 272 days in the future, 187 days since docket alert was
        # re-enabled
        plus_two_hundred_sixty_eight_days = now() + timedelta(days=272)
        with time_machine.travel(
            plus_two_hundred_sixty_eight_days, tick=False
        ):
            report = build_user_report(self.user_profile.user, delete=True)

        # After run the report 272 days in the future a warning should go out
        # but no alert should be disabled since the docket alert was re-enabled
        # 187 days ago.
        self.assertEqual(report.total_count(), 1)
        self.assertEqual(len(report.disabled_alerts), 1)
        self.assertEqual(active_docket_alerts.count(), 0)

    async def test_toggle_docket_alert_date_update(self):
        """Does the docket alert toggle view properly update docket alerts
        date_modified when toggling the alert_type?
        """

        # A docket alert is created today for a case terminated on 2020-01-01
        da = await sync_to_async(DocketAlertWithParentsFactory)(
            docket__source=Docket.RECAP,
            docket__date_terminated="2020-01-01",
            docket__date_last_filing=None,
            user=self.user_profile.user,
            alert_type=DocketAlert.SUBSCRIPTION,
            date_last_hit=None,
        )

        self.assertTrue(
            await self.async_client.alogin(
                username=self.user_profile.user.username, password="password"
            )
        )
        post_data = {"id": da.docket.pk}
        header = {"X_REQUESTED_WITH": "XMLHttpRequest"}

        # Send an AJAX request to toggle_docket_alert view and confirm the
        # is disabled and the date_modified updated.
        sixty_days_ahead = now() + timedelta(days=60)
        with time_machine.travel(sixty_days_ahead, tick=False):
            await self.async_client.post(
                reverse("toggle_docket_alert"),
                data=post_data,
                follow=True,
                **header,
            )
        await da.arefresh_from_db()
        self.assertEqual(da.alert_type, DocketAlert.UNSUBSCRIPTION)
        self.assertEqual(da.date_modified, sixty_days_ahead)

        # Send an AJAX request to toggle_docket_alert view and confirm the
        # is enabled and the date_modified updated.
        eighty_five_days_ahead = now() + timedelta(days=85)
        with time_machine.travel(eighty_five_days_ahead, tick=False):
            await self.async_client.post(
                reverse("toggle_docket_alert"),
                data=post_data,
                follow=True,
                **header,
            )
        await da.arefresh_from_db()
        self.assertEqual(da.alert_type, DocketAlert.SUBSCRIPTION)
        self.assertEqual(da.date_modified, eighty_five_days_ahead)


class OldDocketAlertsWebhooksTest(TestCase):
    """Test Old Docket Alerts Webhooks"""

    @classmethod
    def setUpTestData(cls):
        cls.user_profile = UserProfileWithParentsFactory()
        cls.webhook_enabled = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.OLD_DOCKET_ALERTS_REPORT,
            url="https://example.com/",
            enabled=True,
        )
        cls.disabled_docket_alert = DocketAlertWithParentsFactory(
            docket__source=Docket.RECAP,
            docket__date_terminated="2020-01-01",
            user=cls.user_profile.user,
        )
        cls.old_docket_alert = DocketAlertWithParentsFactory(
            docket__source=Docket.RECAP,
            docket__date_terminated=now() - timedelta(days=92),
            user=cls.user_profile.user,
        )
        cls.very_old_docket_alert = DocketAlertWithParentsFactory(
            docket__source=Docket.RECAP,
            docket__date_terminated=now() - timedelta(days=182),
            user=cls.user_profile.user,
        )

        cls.user_profile_2 = UserProfileWithParentsFactory()
        cls.webhook_disabled = WebhookFactory(
            user=cls.user_profile_2.user,
            event_type=WebhookEventType.OLD_DOCKET_ALERTS_REPORT,
            url="https://example.com/",
            enabled=False,
        )
        cls.disabled_docket_alert_2 = DocketAlertWithParentsFactory(
            docket__source=Docket.RECAP,
            docket__date_terminated="2020-01-01",
            user=cls.user_profile_2.user,
        )

    def test_send_old_docket_alerts_webhook(self):
        """Can we send webhook events for old and disabled docket alerts?"""

        docket_alerts = DocketAlert.objects.all()
        active_docket_alerts = DocketAlert.objects.filter(
            alert_type=DocketAlert.SUBSCRIPTION
        )
        # Update docket alerts date_modified to simulate an old alert.
        docket_alerts.update(date_modified=now() - timedelta(days=365))
        self.assertEqual(docket_alerts.count(), 4)
        self.assertEqual(active_docket_alerts.count(), 4)

        # Run handle_old_docket_alerts command, mocking webhook request.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            call_command(
                "handle_old_docket_alerts",
                delete_old_alerts=True,
                send_alerts=True,
            )

        # Two emails should go out, one for user_profile and one for
        # user_profile_2
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(active_docket_alerts.count(), 2)

        webhook_events = WebhookEvent.objects.all()
        # Only one webhook event should be triggered for user_profile since
        # user_profile_2 webhook endpoint is disabled.
        self.assertEqual(len(webhook_events), 1)
        self.assertEqual(
            webhook_events[0].event_status,
            WEBHOOK_EVENT_STATUS.SUCCESSFUL,
        )
        self.assertEqual(
            webhook_events[0].webhook.user,
            self.user_profile.user,
        )
        content = webhook_events[0].content

        # Compare the webhook event payload.
        self.assertEqual(
            content["webhook"]["event_type"],
            WebhookEventType.OLD_DOCKET_ALERTS_REPORT,
        )
        # Disabled alerts
        self.assertEqual(len(content["payload"]["disabled_alerts"]), 1)
        self.assertEqual(
            content["payload"]["disabled_alerts"][0]["id"],
            self.disabled_docket_alert.pk,
        )
        self.assertEqual(
            content["payload"]["disabled_alerts"][0]["alert_type"],
            DocketAlert.UNSUBSCRIPTION,
        )
        self.assertEqual(
            content["payload"]["disabled_alerts"][0]["docket"],
            self.disabled_docket_alert.docket.pk,
        )

        # Old alerts for webhook (Very old alerts in report)
        self.assertEqual(len(content["payload"]["old_alerts"]), 1)
        self.assertEqual(
            content["payload"]["old_alerts"][0]["id"],
            self.very_old_docket_alert.pk,
        )
        self.assertEqual(
            content["payload"]["old_alerts"][0]["alert_type"],
            DocketAlert.SUBSCRIPTION,
        )
        self.assertEqual(
            content["payload"]["old_alerts"][0]["docket"],
            self.very_old_docket_alert.docket.pk,
        )

        # Run command again
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            call_command(
                "handle_old_docket_alerts",
                delete_old_alerts=True,
                send_alerts=True,
            )

        # One more email should go out for old and very old alerts.
        # No disabled alert.
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(active_docket_alerts.count(), 2)

    def test_send_old_docket_alerts_webhook_only_warn(self):
        """Can we send webhook events that only warn about old docket alerts?"""

        docket_alerts = DocketAlert.objects.all()
        active_docket_alerts = DocketAlert.objects.filter(
            alert_type=DocketAlert.SUBSCRIPTION
        )
        # Update docket alerts date_modified to simulate an old alert.
        docket_alerts.update(date_modified=now() - timedelta(days=365))
        self.assertEqual(docket_alerts.count(), 4)
        self.assertEqual(active_docket_alerts.count(), 4)

        # Run handle_old_docket_alerts command with delete_old_alerts=False,
        # mocking webhook request.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            call_command(
                "handle_old_docket_alerts",
                delete_old_alerts=False,
                send_alerts=True,
            )

        # Two emails should go out, one for user_profile and one for
        # user_profile_2
        self.assertEqual(len(mail.outbox), 2)

        # Only one webhook event should be triggered for user_profile since
        # user_profile_2 webhook endpoint is disabled.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 1)

        self.assertEqual(
            webhook_events[0].webhook.user,
            self.user_profile.user,
        )
        content = webhook_events[0].content
        # Compare the webhook event payload
        self.assertEqual(
            content["webhook"]["event_type"],
            WebhookEventType.OLD_DOCKET_ALERTS_REPORT,
        )
        # No disabled alerts since delete_old_alerts=False
        self.assertEqual(len(content["payload"]["disabled_alerts"]), 0)

        # Old alerts for webhook (Very old alerts in report)
        # Two old alerts, the alert that should have been disabled now is
        # within old alerts
        self.assertEqual(len(content["payload"]["old_alerts"]), 2)

        old_index = 1
        disabled_index = 0
        if (
            content["payload"]["old_alerts"][0]["id"]
            == self.very_old_docket_alert.pk
        ):
            old_index = 0
            disabled_index = 1

        self.assertEqual(
            content["payload"]["old_alerts"][old_index]["docket"],
            self.very_old_docket_alert.docket.pk,
        )
        self.assertEqual(
            content["payload"]["old_alerts"][disabled_index]["docket"],
            self.disabled_docket_alert.docket.pk,
        )


class DocketAlertGetNotesTagsTests(TestCase):
    """Can we return notes and tags for a docket alert properly?"""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user_1 = UserFactory()
        cls.user_2 = UserFactory()
        cls.court = Court.objects.get(id="scotus")
        cls.docket_1 = DocketFactory(
            court=cls.court,
        )
        cls.docket_2 = DocketFactory(
            court=cls.court,
        )
        cls.docket_3 = DocketFactory(
            court=cls.court,
        )
        cls.note_docket_1_user_1 = NoteFactory(
            user=cls.user_1,
            docket_id=cls.docket_1,
            notes="Note 1 Test",
        )
        cls.note_docket_2_user_1 = NoteFactory(
            user=cls.user_1,
            docket_id=cls.docket_2,
            notes="",
        )
        cls.note_docket_1_user_2 = NoteFactory(
            user=cls.user_2,
            docket_id=cls.docket_1,
            notes="Note 2 Test",
        )

        cls.orphan_tag_user_1 = UserTagFactory(user=cls.user_1, name="orphan")
        cls.tag_1_user_1 = UserTagFactory(user=cls.user_1, name="tag_1_user_1")
        cls.tag_2_user_1 = UserTagFactory(user=cls.user_1, name="tag_2_user_1")
        cls.tag_1_user_1.dockets.add(cls.docket_1.pk)
        cls.tag_2_user_1.dockets.add(cls.docket_1.pk, cls.docket_2)

        cls.tag_1_user_2 = UserTagFactory(user=cls.user_2, name="tag_1_user_2")
        cls.tag_1_user_2.dockets.add(cls.docket_1.pk, cls.docket_2)

    def test_get_docket_notes_and_tags_by_user(self) -> None:
        """Can we properly get the user notes and tags for a docket?"""

        (
            notes_docket_1_user_1,
            tags_docket_1_user_1,
        ) = get_docket_notes_and_tags_by_user(self.docket_1.pk, self.user_1.pk)
        self.assertEqual(notes_docket_1_user_1, "Note 1 Test")
        self.assertEqual(
            tags_docket_1_user_1, [self.tag_1_user_1, self.tag_2_user_1]
        )

        (
            notes_docket_1_user_2,
            tags_docket_1_user_2,
        ) = get_docket_notes_and_tags_by_user(self.docket_1.pk, self.user_2.pk)
        self.assertEqual(notes_docket_1_user_2, "Note 2 Test")
        self.assertEqual(tags_docket_1_user_2, [self.tag_1_user_2])

        (
            notes_docket_2_user_1,
            tags_docket_2_user_1,
        ) = get_docket_notes_and_tags_by_user(self.docket_2.pk, self.user_1.pk)
        self.assertEqual(notes_docket_2_user_1, None)
        self.assertEqual(tags_docket_2_user_1, [self.tag_2_user_1])

        (
            notes_docket_2_user_2,
            tags_docket_2_user_2,
        ) = get_docket_notes_and_tags_by_user(self.docket_2.pk, self.user_2.pk)
        self.assertEqual(notes_docket_2_user_2, None)
        self.assertEqual(tags_docket_2_user_2, [self.tag_1_user_2])

        (
            notes_docket_3_user_1,
            tags_docket_3_user_1,
        ) = get_docket_notes_and_tags_by_user(self.docket_3.pk, self.user_1.pk)
        self.assertEqual(notes_docket_3_user_1, None)
        self.assertEqual(tags_docket_3_user_1, [])


@override_switch("oa-es-alerts-active", active=True)
@mock.patch(
    "cl.lib.es_signal_processor.allow_es_audio_indexing",
    side_effect=lambda x, y: True,
)
class SearchAlertsOAESTests(ESIndexTestCase, TestCase):
    """Test ES Search Alerts"""

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("audio.Audio")
        cls.rebuild_index("alerts.Alert")
        cls.court_1 = CourtFactory(
            id="cabc",
            full_name="Testing Supreme Court",
            jurisdiction="FB",
            citation_string="Bankr. C.D. Cal.",
        )
        cls.user_profile = UserProfileWithParentsFactory()
        cls.donation = DonationFactory(
            donor=cls.user_profile.user,
            amount=20,
            status=Donation.PROCESSED,
            send_annual_reminder=True,
        )
        cls.user_profile_2 = UserProfileWithParentsFactory()
        cls.donation = DonationFactory(
            donor=cls.user_profile_2.user,
            amount=20,
            status=Donation.PROCESSED,
            send_annual_reminder=True,
        )
        cls.webhook_enabled = WebhookFactory(
            user=cls.user_profile.user,
            event_type=WebhookEventType.SEARCH_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        cls.search_alert = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert OA",
            query="q=RT+Test+OA+19-5735&type=oa",
        )
        cls.search_alert_2 = AlertFactory(
            user=cls.user_profile_2.user,
            rate=Alert.REAL_TIME,
            name="Test Alert OA 2",
            query="q=RT+Test+OA&type=oa",
        )
        cls.search_alert_3 = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert OA Daily",
            query="q=Test+OA&type=oa",
        )
        cls.search_alert_4 = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert OA Daily 2",
            query="q=DLY+Test+V2+19-5741&type=oa",
        )
        cls.search_alert_5 = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.WEEKLY,
            name="Test Alert OA Weekly",
            query="q=Test+OA&type=oa",
        )
        cls.search_alert_6 = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.MONTHLY,
            name="Test Alert OA Monthly",
            query="q=Test+OA&type=oa",
        )

    @classmethod
    def tearDownClass(cls):
        Alert.objects.all().delete()
        Audio.objects.all().delete()
        super().tearDownClass()

    def test_alert_frequency_estimation(self, mock_abort_audio):
        """Test alert frequency ES API endpoint."""

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Frequency Test OA",
        }
        r = self.client.get(
            reverse(
                "alert_frequency", kwargs={"version": "3", "day_count": "100"}
            ),
            search_params,
        )
        self.assertEqual(r.json()["count"], 0)

        mock_date = now().replace(day=1, hour=5)
        with time_machine.travel(
            mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            # When the Audio object is created it should trigger an alert.
            rt_oral_argument = AudioWithParentsFactory.create(
                case_name="Frequency Test OA",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5735",
            )

        r = self.client.get(
            reverse(
                "alert_frequency", kwargs={"version": "3", "day_count": "100"}
            ),
            search_params,
        )
        self.assertEqual(r.json()["count"], 1)
        rt_oral_argument.delete()

    def test_send_oa_search_alert_webhooks(self, mock_abort_audio):
        """Can we send RT OA search alerts?"""

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            mock_date = now().replace(day=1, hour=5)
            with time_machine.travel(
                mock_date, tick=False
            ), self.captureOnCommitCallbacks(execute=True):
                # When the Audio object is created it should trigger an alert.
                transcript_response = {
                    "response": {
                        "results": [
                            {
                                "alternatives": [
                                    {
                                        "transcript": "RT Test OA transcript.",
                                        "confidence": 0.85,
                                    },
                                ]
                            },
                        ]
                    }
                }
                json_transcript = json.dumps(transcript_response)
                rt_oral_argument = AudioWithParentsFactory.create(
                    case_name="RT Test OA",
                    docket__court=self.court_1,
                    docket__date_argued=now().date(),
                    docket__docket_number="19-5735",
                    stt_status=Audio.STT_COMPLETE,
                    judges="John Smith",
                    stt_google_response=json_transcript,
                )

        # Confirm Alert date_last_hit is updated.
        self.search_alert.refresh_from_db()
        self.search_alert_2.refresh_from_db()
        self.assertEqual(self.search_alert.date_last_hit, mock_date)
        self.assertEqual(self.search_alert_2.date_last_hit, mock_date)

        webhooks_enabled = Webhook.objects.filter(enabled=True)
        self.assertEqual(len(webhooks_enabled), 1)
        # Two OA search alert emails should be sent, one for user_profile and
        # one for user_profile_2
        self.assertEqual(len(mail.outbox), 2)
        text_content = mail.outbox[0].body
        self.assertIn(rt_oral_argument.case_name, text_content)
        # Highlighting tags are not set in text version
        self.assertNotIn("<strong>", text_content)

        # Extract HTML version.
        html_content = None
        for content, content_type in mail.outbox[0].alternatives:
            if content_type == "text/html":
                html_content = content
                break

        # Case name is not highlighted in email alert.
        self.assertIn(rt_oral_argument.case_name, html_content)
        # Highlighting tags are set for other fields.
        self.assertIn("<strong>19-5735</strong>", html_content)
        self.assertIn("<strong>RT</strong>", html_content)

        # Confirm that order_by is overridden in the 'View Full Results' URL by
        # dateArgued+desc.
        view_results_url = html.fromstring(str(html_content)).xpath(
            '//a[text()="View Full Results / Edit this Alert"]/@href'
        )
        self.assertIn("order_by=dateArgued+desc", view_results_url[0])

        # The right alert type template is used.
        self.assertIn("oral argument", html_content)

        # 4 webhook events should be sent to user_profile.
        # rt_oral_argument should trigger: search_alert, search_alert_3,
        # search_alert_5 and search_alert_6.
        # search_alert_2 is omitted since it's related user doesn't have a
        # search alert webhook enabled.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 4)

        # Compare webhook content.
        content = webhook_events[0].content
        self.assertEqual(
            content["payload"]["alert"]["query"], self.search_alert.query
        )
        self.assertEqual(content["payload"]["alert"]["rate"], "rt")
        self.assertEqual(
            len(content["payload"]["results"]),
            1,
        )
        self.assertEqual(
            content["payload"]["results"][0]["caseName"],
            rt_oral_argument.case_name,
        )
        self.assertEqual(
            content["payload"]["results"][0]["court"],
            rt_oral_argument.docket.court.full_name,
        )
        self.assertEqual(
            content["payload"]["results"][0]["source"],
            rt_oral_argument.source,
        )
        webhook_events.delete()
        rt_oral_argument.delete()

    def test_send_alert_on_document_creation(self, mock_abort_audio):
        """Avoid sending Search Alerts on document updates."""
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            # When the Audio object is created it should trigger an alert.
            rt_oral_argument = AudioWithParentsFactory.create(
                case_name="RT Test OA",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5735",
            )

        # Two OA search alert emails should be sent, one for user_profile and
        # one for user_profile_2
        self.assertEqual(len(mail.outbox), 2)
        text_content = mail.outbox[0].body
        self.assertIn(rt_oral_argument.case_name, text_content)

        # 4 webhook events should be sent to user_profile.
        # rt_oral_argument should trigger: search_alert, search_alert_3,
        # search_alert_5 and search_alert_6.
        # search_alert_2 is omitted since it's related user doesn't have a
        # search alert webhook enabled.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 4)

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            # Audio object is updated.
            rt_oral_argument.sha1 = "12345"
            rt_oral_argument.save()

        # New alerts shouldn't be sent. Since document was just updated.
        self.assertEqual(len(mail.outbox), 2)
        text_content = mail.outbox[0].body
        self.assertIn(rt_oral_argument.case_name, text_content)

        # No new webhook events should be triggered.
        # Since document was just updated.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 4)
        rt_oral_argument.delete()

    def test_es_alert_update_and_delete(self, mock_abort_audio):
        """Can we update and delete an alert, and expect these changes to be
        properly reflected in Elasticsearch?"""

        # Create a new alert.
        search_alert_1 = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert OA",
            query="type=oa&docket_number=19-1010",
        )

        # Confirm it was properly indexed in ES.
        search_alert_1_id = search_alert_1.pk
        doc = AudioPercolator.get(id=search_alert_1_id)
        response_str = str(doc.to_dict())
        self.assertIn("'query': '19-1010'", response_str)
        self.assertIn("'rate': 'rt'", response_str)

        # Update Alert
        search_alert_1.query = "type=oa&docket_number=19-1020"
        search_alert_1.rate = "dly"
        search_alert_1.save()

        doc = AudioPercolator.get(id=search_alert_1_id)
        response_str = str(doc.to_dict())

        # Confirm changes in ES.
        self.assertIn("'query': '19-1020'", response_str)
        self.assertIn("'rate': 'dly'", response_str)

        # Delete Alert
        search_alert_1.delete()

        s = AudioPercolator.search().query("match_all")
        response = s.execute()
        response_str = str(response.to_dict())

        # Confirm whether the alert was also deleted in Elasticsearch.
        self.assertNotIn(f"'_id': '{search_alert_1_id}'", response_str)

    def send_alerts_by_rate_and_confirm_assertions(
        self,
        rate,
        document,
        search_alert,
        mock_date,
        stat_count,
        alert_count,
        previous_date=None,
    ):
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            with time_machine.travel(mock_date, tick=False):
                # Call dly command
                call_command("cl_send_scheduled_alerts", rate=rate)

        # Confirm Stat object is properly updated.
        stat_object = Stat.objects.filter(date_logged=mock_date)
        self.assertEqual(stat_object[0].name, f"alerts.sent.{rate}")
        self.assertEqual(stat_object[0].count, stat_count)

        # Confirm Alert date_last_hit is updated.
        search_alert.refresh_from_db()

        # One OA search alert email should be sent
        self.assertEqual(len(mail.outbox), alert_count)
        text_content = mail.outbox[alert_count - 1].body
        self.assertIn(document.case_name, text_content)

        # The right alert type template is used.
        self.assertIn("oral argument", text_content)

        # Extract HTML version.
        html_content = None
        for content, content_type in mail.outbox[alert_count - 1].alternatives:
            if content_type == "text/html":
                html_content = content
                break

        # Confirm that order_by is overridden in the 'View Full Results'
        # URL by dateArgued+desc.
        view_results_url = html.fromstring(str(html_content)).xpath(
            '//a[text()="View Full Results / Edit this Alert"]/@href'
        )

        parsed_url = urlparse(view_results_url[0])
        params = parse_qs(parsed_url.query)
        self.assertEqual("dateArgued desc", params["order_by"][0])

        if previous_date:
            self.assertEqual(search_alert.date_last_hit, previous_date)
        else:
            self.assertEqual(search_alert.date_last_hit, mock_date)

            # Confirm that argued_after is properly set in the
            # 'View Full Results' URL.
            cut_off_date = get_cut_off_date(rate, mock_date.date())
            date_in_query = datetime.strptime(
                params["argued_after"][0], "%m/%d/%Y"
            ).date()
            self.assertEqual(cut_off_date, date_in_query)

        # Confirm stored alerts instances status is set to SENT.
        scheduled_hits = ScheduledAlertHit.objects.filter(alert__rate=rate)
        for scheduled_hit in scheduled_hits:
            self.assertEqual(
                scheduled_hit.hit_status, SCHEDULED_ALERT_HIT_STATUS.SENT
            )

    def test_send_alert_multiple_alert_rates(self, mock_abort_audio):
        """Confirm dly, wly and mly alerts are properly stored and sent
        according to their periodicity.
        """
        with self.captureOnCommitCallbacks(execute=True):
            dly_oral_argument = AudioWithParentsFactory.create(
                case_name="DLY Test OA",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5739",
            )
        # When a new document is created, and it triggers a dly, wly or mly
        # It's stored to send it later.
        scheduled_alerts = ScheduledAlertHit.objects.filter(
            alert__rate=Alert.DAILY
        )
        self.assertEqual(scheduled_alerts.count(), 1)
        # At this stage no alerts or webhooks should go out.
        self.assertEqual(len(mail.outbox), 0)

        # 3 webhook events should be triggered in RT regardless of alert rate
        # or user donations.
        # dly_oral_argument document should trigger 3 webhooks: search_alert_3,
        # search_alert_5 and search_alert_6.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 3)

        # Send dly alerts and check assertions.
        mock_date = timezone.localtime(timezone.now()).replace(day=1, hour=0)
        self.send_alerts_by_rate_and_confirm_assertions(
            Alert.DAILY,
            dly_oral_argument,
            self.search_alert_3,
            mock_date,
            stat_count=1,
            alert_count=1,
        )

        # Daily command is executed the next day again, it shouldn't send more
        # alerts. Since previous alerts have already been sent.
        current_date = timezone.localtime(timezone.now()).replace(
            day=2, hour=0
        )
        self.send_alerts_by_rate_and_confirm_assertions(
            Alert.DAILY,
            dly_oral_argument,
            self.search_alert_3,
            current_date,
            stat_count=0,
            alert_count=1,
            previous_date=mock_date,
        )
        # Create an additional document that should be included in wly and mly
        # Alerts.
        with self.captureOnCommitCallbacks(execute=True):
            wly_oral_argument = AudioWithParentsFactory.create(
                case_name="WLY Test OA",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5741",
            )
        # Send wly alerts and check assertions.
        current_date = timezone.localtime(timezone.now()).replace(
            day=7, hour=0
        )
        self.send_alerts_by_rate_and_confirm_assertions(
            Alert.WEEKLY,
            dly_oral_argument,
            self.search_alert_5,
            current_date,
            stat_count=1,
            alert_count=2,
        )
        # Create an additional document that should be included mly Alert.
        with self.captureOnCommitCallbacks(execute=True):
            mly_oral_argument = AudioWithParentsFactory.create(
                case_name="MLY Test OA",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5742",
            )
        # Send mly alerts on a day after 28th, it must fail.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            mock_date = now().replace(day=30, hour=0)
            with time_machine.travel(mock_date, tick=False):
                # Call mly command
                with self.assertRaises(InvalidDateError):
                    call_command("cl_send_scheduled_alerts", rate="mly")

        # Send mly alerts.
        current_date = timezone.localtime(timezone.now()).replace(
            day=28, hour=0
        )
        self.send_alerts_by_rate_and_confirm_assertions(
            Alert.MONTHLY,
            dly_oral_argument,
            self.search_alert_6,
            current_date,
            stat_count=1,
            alert_count=3,
        )
        # Remove tests objects.
        dly_oral_argument.delete()
        wly_oral_argument.delete()
        mly_oral_argument.delete()

    @mock.patch(
        "cl.alerts.management.commands.cl_send_scheduled_alerts.logger"
    )
    def test_group_alerts_and_hits(self, mock_logger, mock_abort_audio):
        """"""
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            # When the Audio object is created it should trigger an alert.
            rt_oral_argument_1 = AudioWithParentsFactory.create(
                case_name="DLY Test OA",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5739",
            )
            # When the Audio object is created it should trigger an alert.
            rt_oral_argument_2 = AudioWithParentsFactory.create(
                case_name="DLY Test OA 2",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5740",
            )
            # When the Audio object is created it should trigger an alert.
            rt_oral_argument_3 = AudioWithParentsFactory.create(
                case_name="DLY Test V2",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5741",
            )

        # No emails should be sent in RT, since all the alerts triggered by the
        # OA documents added are not RT.
        self.assertEqual(len(mail.outbox), 0)

        # 7 webhook events should be triggered in RT:
        # rt_oral_argument_1 should trigger 3: search_alert_3, search_alert_5
        # and search_alert_6.
        # rt_oral_argument_2 should trigger 3: search_alert_3, search_alert_5
        # and search_alert_6.
        # rt_oral_argument_3 should trigger 1: search_alert_4
        # One webhook event should be sent to user_profile
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(
            len(webhook_events), 7, msg="Unexpected number of" "webhooks sent."
        )

        # 7 webhook event should be sent to user_profile for 4 different
        # alerts
        webhook_events = WebhookEvent.objects.all()
        triggered_alerts_expected = [
            self.search_alert_3.pk,
            self.search_alert_4.pk,
            self.search_alert_5.pk,
            self.search_alert_6.pk,
        ]
        for webhook_content in webhook_events:
            content = webhook_content.content["payload"]
            if content["alert"]["id"] in triggered_alerts_expected:
                self.assertEqual(len(content["results"]), 1)
            else:
                self.assertTrue(False, "Search Alert webhooks failed.")

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            # Call command dly
            call_command("cl_send_scheduled_alerts", rate="dly")

        # One OA search alert email should be sent.
        mock_logger.info.assert_called_with("Sent 1 dly email alerts.")
        self.assertEqual(len(mail.outbox), 1)
        text_content = mail.outbox[0].body

        # The right alert type template is used.
        self.assertIn("oral argument", text_content)

        # The alert email should contain 3 hits.
        self.assertIn(rt_oral_argument_1.case_name, text_content)
        self.assertIn(rt_oral_argument_2.case_name, text_content)
        self.assertIn(rt_oral_argument_3.case_name, text_content)

        # Grouped  below two alerts.
        self.assertIn(self.search_alert_3.name, text_content)
        self.assertIn(self.search_alert_4.name, text_content)

        # Extract HTML version.
        html_content = None
        for content, content_type in mail.outbox[0].alternatives:
            if content_type == "text/html":
                html_content = content
                break

        # Highlights are properly set in scheduled alerts.
        self.assertIn("<strong>19-5741</strong>", html_content)

        rt_oral_argument_1.delete()
        rt_oral_argument_2.delete()
        rt_oral_argument_3.delete()

    @override_settings(ELASTICSEARCH_PAGINATION_BATCH_SIZE=5)
    def test_send_multiple_rt_alerts(self, mock_abort_audio):
        """Confirm all RT alerts are properly sent if the percolator response
        contains more than ELASTICSEARCH_PAGINATION_BATCH_SIZE results. So additional
        requests are performed in order to retrieve all the available results.
        """

        donations = Donation.objects.all()
        self.assertEqual(donations.count(), 2)
        self.assertEqual(len(mail.outbox), 0)
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 0)

        # Create 10 additional Alerts for different users.
        alerts_created = []
        for i in range(10):
            user_profile = UserProfileWithParentsFactory.create()

            if i != 1:
                # Avoid creating a donation for one User in order to test this
                # RT Alert is not sent.
                DonationFactory.create(
                    amount=20,
                    donor=user_profile.user,
                    status=Donation.PROCESSED,
                    send_annual_reminder=True,
                )
            WebhookFactory(
                user=user_profile.user,
                event_type=WebhookEventType.SEARCH_ALERT,
                url="https://example.com/",
                enabled=True,
            )
            alert = AlertFactory.create(
                user=user_profile.user,
                rate=Alert.REAL_TIME,
                name=f"Test Alert RT {i}",
                query="q=RT+Test+OA&type=oa",
            )
            alerts_created.append(alert)

        webhooks = Webhook.objects.all()
        self.assertEqual(len(webhooks), 11)
        donations = Donation.objects.all()
        self.assertEqual(len(donations), 11)
        total_rt_alerts = Alert.objects.filter(rate=Alert.REAL_TIME)
        # 2 created in setUpTestData + 10
        self.assertEqual(total_rt_alerts.count(), 12)

        # Clear the outbox
        mail.outbox = []

        # Trigger RT alerts adding a document that matches the alerts.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            rt_oral_argument = AudioWithParentsFactory.create(
                case_name="RT Test OA",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5735",
            )

        # 11 OA search alert emails should be sent, one for each user that
        # had donated enough.
        self.assertEqual(len(mail.outbox), 11)
        text_content = mail.outbox[0].body
        self.assertIn(rt_oral_argument.case_name, text_content)

        # 14 webhook events should be sent to users with a Webhook active.
        # rt_oral_argument should trigger: search_alert, search_alert_3,
        # search_alert_5 and search_alert_6.
        # And 10 additional new alerts created in this test.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 14)
        content = webhook_events[0].content["payload"]
        self.assertEqual(len(content["results"]), 1)

        # Confirm Stat object is properly created and updated.
        stats_objects = Stat.objects.all()
        self.assertEqual(stats_objects.count(), 1)
        self.assertEqual(stats_objects[0].name, "alerts.sent.rt")
        self.assertEqual(stats_objects[0].count, 11)

        # Remove test instances.
        rt_oral_argument.delete()
        for alert in alerts_created:
            alert.delete()

    @override_settings(ELASTICSEARCH_PAGINATION_BATCH_SIZE=5)
    def test_batched_alerts_match_documents_ingestion(self, mock_abort_audio):
        """Confirm that batched alerts are properly stored according to
        document ingestion when percolated in real time.
        """

        # Create a set of 11 users, webhooks and Alerts.
        alerts_created = []
        audios_created = []
        for i in range(10):
            user_profile = UserProfileWithParentsFactory.create()
            WebhookFactory(
                user=user_profile.user,
                event_type=WebhookEventType.SEARCH_ALERT,
                url="https://example.com/",
                enabled=True,
            )
            alert = AlertFactory.create(
                user=user_profile.user,
                rate=Alert.DAILY,
                name=f"Test Alert OA {i}",
                query="q=OA&+19-5735&type=oa",
            )
            alerts_created.append(alert)
            # Create a new document that triggers each existing alert created
            # at this stage.
            with mock.patch(
                "cl.api.webhooks.requests.post",
                side_effect=lambda *args, **kwargs: MockResponse(
                    200, mock_raw=True
                ),
            ), self.captureOnCommitCallbacks(execute=True):
                audio = AudioWithParentsFactory.create(
                    case_name="Test OA",
                    docket__court=self.court_1,
                    docket__date_argued=now().date(),
                    docket__docket_number="19-5735",
                )
                audios_created.append(audio)

        # Clear the outbox
        mail.outbox = []
        self.assertEqual(len(mail.outbox), 0)

        # Webhooks for all alert rates and users are sent in real time.
        webhook_events = WebhookEvent.objects.all()
        webhook_events_rate = defaultdict(list)
        for event in webhook_events:
            content = event.content["payload"]
            alert_rate = content["alert"]["rate"]
            webhook_events_rate[alert_rate].append(event)

        # Total webhooks triggered.
        self.assertEqual(len(webhook_events), 85)

        # 65 DLY webhooks,the last alert created should trigger 10 hits and
        # this number is reduced by 1 in each subsequent iteration. The first
        # alert should only trigger one webhook since it was the only document
        # that triggered the alert at that stage.
        # Total DLY webhooks sum of: [10, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
        self.assertEqual(len(webhook_events_rate[Alert.DAILY]), 65)
        # 10 WLY webhooks, one for each document created.
        self.assertEqual(len(webhook_events_rate[Alert.WEEKLY]), 10)
        # 10 MLY webhooks, one for each document created.
        self.assertEqual(len(webhook_events_rate[Alert.MONTHLY]), 10)

        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            # Call dly command
            call_command("cl_send_scheduled_alerts", rate="dly")

        # 11 email Alerts should be sent.
        self.assertEqual(len(mail.outbox), 11)

        # Remove test instances.
        for audio in audios_created:
            audio.delete()
        for alert in alerts_created:
            alert.delete()

    @override_settings(ELASTICSEARCH_PAGINATION_BATCH_SIZE=5)
    def test_percolate_document_in_batches(self, mock_abort_audio):
        """Confirm when getting alerts in batches and an alert previously
        retrieved is updated during this process. It's not returned again.
        """

        alerts_created = []
        for i in range(6):
            user_profile = UserProfileWithParentsFactory.create()
            alert = AlertFactory.create(
                user=user_profile.user,
                rate=Alert.REAL_TIME,
                name=f"Test Alert RT {i}",
                query="q=Lorem+Ipsum+20-5739&type=oa",
            )
            alerts_created.append(alert)

        # Save a document to percolate it later.
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            rt_oral_argument = AudioWithParentsFactory.create(
                case_name="Lorem Ipsum",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="20-5739",
            )

        # Percolate the document. First batch.
        document_index = AudioDocument._index._name
        percolator_response = percolate_document(
            str(rt_oral_argument.pk), document_index
        )

        ids_in_results = [result.id for result in percolator_response.hits]

        # Update the first in the previous batch.
        alert_to_modify = alerts_created[0]
        alert_to_modify.rate = "dly"
        alert_to_modify.save()

        # Percolate the next page.
        search_after = percolator_response.hits[-1].meta.sort
        percolator_response = percolate_document(
            str(rt_oral_argument.pk), document_index, search_after=search_after
        )

        # The document updated shouldn't be retrieved again.
        # Since documents are ordered by asc date_created instead of timestamp.
        for result in percolator_response.hits:
            self.assertNotIn(result.id, ids_in_results)
            ids_in_results.append(result.id)

    def test_avoid_sending_or_scheduling_disabled_alerts(
        self, mock_abort_audio
    ):
        """Can we avoid sending or_scheduling disabled search alerts?."""

        rt_alert_disabled = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.OFF,
            name="Test Alert OA Daily",
            query="q=Disabled+Alert&type=oa",
        )
        dly_alert_disabled = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.OFF,
            name="Test Alert OA Daily",
            query="q=Disabled+Alert&type=oa",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ):
            # When the Audio object is created it should trigger an alert.
            oral_argument = AudioWithParentsFactory.create(
                case_name="Disabled+Alert",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5735",
            )

        # No RT Alert emails should be sent.
        self.assertEqual(len(mail.outbox), 0)
        # No Webhooks should be sent.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(len(webhook_events), 0)

        # No Scheduled Alerts should be created.
        schedule_alerts = ScheduledAlertHit.objects.all()
        self.assertEqual(schedule_alerts.count(), 0)

        rt_alert_disabled.delete()
        dly_alert_disabled.delete()
        oral_argument.delete()

    def test_avoid_re_sending_scheduled_sent_alerts(self, mock_abort_audio):
        """Can we prevent re-sending scheduled alerts that have already been
        sent?"""

        dly_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert OA Daily",
            query="q=Scheduled+Alert&type=oa",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            # When the Audio object is created it should trigger an alert.
            oral_argument = AudioWithParentsFactory.create(
                case_name="Scheduled+Alert",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5735",
            )

        # No RT Alert emails should be sent for the DLY alert.
        self.assertEqual(len(mail.outbox), 0)
        # 1 Webhook event should be sent in RT.
        webhook_events = WebhookEvent.objects.all()
        self.assertEqual(webhook_events.count(), 1)

        # 1 Scheduled Alert should be created in SCHEDULED status.
        all_alert_hits = ScheduledAlertHit.objects.all()
        self.assertEqual(all_alert_hits.count(), 1)
        self.assertEqual(
            all_alert_hits[0].hit_status, SCHEDULED_ALERT_HIT_STATUS.SCHEDULED
        )

        # Send dly alerts and check assertions.
        mock_date = now().replace(day=1, hour=0)
        with time_machine.travel(mock_date, tick=False):
            # Call dly command
            call_command("cl_send_scheduled_alerts", rate=Alert.DAILY)

        # 1 Alert email should be sent.
        self.assertEqual(len(mail.outbox), 1)
        # No additional Webhook event should be sent.
        self.assertEqual(webhook_events.count(), 1)
        # 1 Scheduled Alert should be now in SENT status.
        self.assertEqual(all_alert_hits.count(), 1)
        self.assertEqual(
            all_alert_hits[0].hit_status, SCHEDULED_ALERT_HIT_STATUS.SENT
        )

        # Create a new Audio Document which will schedule a new DLY Alert hit.
        mock_date = now() + timedelta(days=DAYS_TO_DELETE - 5)
        with time_machine.travel(
            mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            oral_argument_2 = AudioWithParentsFactory.create(
                case_name="Scheduled+Alert",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5735",
            )

        # No additional Alert email should be sent.
        self.assertEqual(len(mail.outbox), 1)
        # 1 additional Webhook event should be sent.
        self.assertEqual(webhook_events.count(), 2)
        # 2 Scheduled Alert, one in Scheduled status and one in Sent status.
        schedule_alerts = ScheduledAlertHit.objects.filter(
            hit_status=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED
        )
        self.assertEqual(schedule_alerts.count(), 1)
        scheduled_alert_pk = schedule_alerts[0].pk
        sent_alerts = ScheduledAlertHit.objects.filter(
            hit_status=SCHEDULED_ALERT_HIT_STATUS.SENT
        )
        self.assertEqual(sent_alerts.count(), 1)

        # Send dly alerts after DAYS_TO_DELETE and check assertions.
        mock_date = now() + timedelta(days=DAYS_TO_DELETE + 1)
        with time_machine.travel(mock_date, tick=False):
            # Call dly command
            call_command("cl_send_scheduled_alerts", rate=Alert.DAILY)

        # 1 additional Alert email should be sent.
        self.assertEqual(len(mail.outbox), 2)
        # No additional Webhook event should be sent.
        self.assertEqual(webhook_events.count(), 2)
        # The Old Scheduled Alert Hit should be deleted and the most recent one
        # is now in SENT status.
        self.assertEqual(all_alert_hits.count(), 1)
        self.assertEqual(
            all_alert_hits[0].hit_status, SCHEDULED_ALERT_HIT_STATUS.SENT
        )
        self.assertEqual(all_alert_hits[0].pk, scheduled_alert_pk)

        # Create a MONTHLY Alert
        dly_alert_2 = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.MONTHLY,
            name="Test Alert OA MONTHLY",
            query="q=Monthly+Hit&type=oa",
        )
        with mock.patch(
            "cl.api.webhooks.requests.post",
            side_effect=lambda *args, **kwargs: MockResponse(
                200, mock_raw=True
            ),
        ), self.captureOnCommitCallbacks(execute=True):
            # Schedule the MONTHLY Alert hit.
            oral_argument_3 = AudioWithParentsFactory.create(
                case_name="Monthly+Hit",
                docket__court=self.court_1,
                docket__date_argued=now().date(),
                docket__docket_number="19-5735",
            )

        # Now we should have 1 scheduled Alert hit and 1 sent Alert hit.
        self.assertEqual(all_alert_hits.count(), 2)
        schedule_alerts = ScheduledAlertHit.objects.filter(
            hit_status=SCHEDULED_ALERT_HIT_STATUS.SCHEDULED
        )
        self.assertEqual(schedule_alerts.count(), 1)
        sent_alerts = ScheduledAlertHit.objects.filter(
            hit_status=SCHEDULED_ALERT_HIT_STATUS.SENT
        )
        self.assertEqual(sent_alerts.count(), 1)

        # Send dly alerts after DAYS_TO_DELETE and check assertions.
        mock_date = now() + timedelta(days=2 * DAYS_TO_DELETE + 1)
        with time_machine.travel(mock_date, tick=False):
            # Call dly command
            call_command("cl_send_scheduled_alerts", rate=Alert.DAILY)

        # After 2*DAYS_TO_DELETE also scheduled Alerts hits are removed.
        self.assertEqual(all_alert_hits.count(), 0)

        dly_alert.delete()
        dly_alert_2.delete()
        oral_argument.delete()
        oral_argument_2.delete()
        oral_argument_3.delete()

    @override_settings(SCHEDULED_ALERT_HITS_LIMIT=3)
    def test_scheduled_hits_limit(self, mock_abort_audio):
        """Confirm we only store the max number of alert hits set in settings."""

        alert_1 = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert OA Daily 1",
            query="q=USA+vs+Bank+&type=oa",
        )
        alert_2 = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert OA Daily 2",
            query="q=Texas+vs+Corp&type=oa",
        )
        alert_3 = AlertFactory(
            user=self.user_profile_2.user,
            rate=Alert.DAILY,
            name="Test Alert OA Daily 3",
            query="q=Texas+vs+Corp&type=oa",
        )

        oa_created = []
        for i in range(4):
            with self.captureOnCommitCallbacks(execute=True):
                oral_argument = AudioWithParentsFactory.create(
                    case_name="USA vs Bank",
                    docket__court=self.court_1,
                    docket__date_argued=now().date(),
                    docket__docket_number="19-5735",
                )
                oa_created.append(oral_argument)

                if i in (1, 2):
                    # Only schedule two hits for this one.
                    oral_argument_2 = AudioWithParentsFactory.create(
                        case_name="Texas vs Corp",
                        docket__court=self.court_1,
                        docket__date_argued=now().date(),
                        docket__docket_number="20-5030",
                    )
                    oa_created.append(oral_argument_2)

        # Call dly command
        call_command("cl_send_scheduled_alerts", rate=Alert.DAILY)

        # Two emails should be sent, one for user_profile and one for user_profile_2
        self.assertEqual(len(mail.outbox), 2)

        # Confirm emails contains the hits+ count.
        self.assertIn(
            f"had {settings.SCHEDULED_ALERT_HITS_LIMIT}+ hits",
            mail.outbox[0].body,
        )
        # No "+" if hits do not reach the SCHEDULED_ALERT_HITS_LIMIT.
        self.assertIn(
            "had 2 hits",
            mail.outbox[1].body,
        )

        # Confirm each email contains the max number of hits for each alert.
        self.assertEqual(
            mail.outbox[0].body.count("USA vs Bank"),
            settings.SCHEDULED_ALERT_HITS_LIMIT,
        )
        self.assertEqual(
            mail.outbox[0].body.count("Texas vs Corp"),
            2,
        )
        self.assertEqual(
            mail.outbox[1].body.count("Texas vs Corp"),
            2,
        )

        for oa in oa_created:
            oa.delete()

        alert_1.delete()
        alert_2.delete()
        alert_3.delete()


@override_settings(ELASTICSEARCH_DISABLED=True)
class SearchAlertsIndexingCommandTests(ESIndexTestCase, TestCase):
    """Test the cl_index_search_alerts command"""

    @classmethod
    def setUpTestData(cls):
        cls.user_profile = UserProfileWithParentsFactory()
        cls.user_profile_2 = UserProfileWithParentsFactory()
        cls.search_alert = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert OA",
            query="q=RT+Test+OA&type=oa",
        )
        cls.search_alert_2 = AlertFactory(
            user=cls.user_profile_2.user,
            rate=Alert.REAL_TIME,
            name="Test Alert OA 2",
            query="q=RT+Test+OA&type=oa",
        )
        cls.search_alert_3 = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert OA Daily",
            query="q=Test+OA&type=oa",
        )
        cls.search_alert_4 = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.WEEKLY,
            name="Test Alert OA Weekly",
            query="q=Test+OA&type=oa",
        )
        cls.search_alert_5 = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.MONTHLY,
            name="Test Alert OA Monthly",
            query="q=Test+OA&type=oa",
        )
        cls.search_alert_6 = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.MONTHLY,
            name="Test Alert O RT",
            query="q=Test+Opinion Alert",
        )
        cls.search_alert_7 = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.REAL_TIME,
            name="Test Alert R",
            query="q=Test+O&type=r",
        )
        cls.search_alert_8 = AlertFactory(
            user=cls.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert R",
            query="q=Test+O&type=r",
        )

    def tearDown(self) -> None:
        self.delete_index("alerts.Alert")
        self.create_index("alerts.Alert")

    @override_settings(ELASTICSEARCH_PAGINATION_BATCH_SIZE=20)
    @mock.patch("cl.alerts.management.commands.cl_index_search_alerts.logger")
    def test_cl_index_search_alerts_command(self, mock_logger):
        """Confirm the command only index the right Alerts into the ES."""
        s = AudioPercolator.search().query("match_all")
        response = s.execute()
        response_dict = response.to_dict()
        self.assertEqual(response_dict["hits"]["total"]["value"], 0)

        # Call cl_index_search_alerts command.
        call_command(
            "cl_index_search_alerts",
            pk_offset=0,
            alert_type=SEARCH_TYPES.ORAL_ARGUMENT,
        )

        s = AudioPercolator.search().query("match_all")
        response = s.execute()
        response_dict = response.to_dict()
        # Only OA Alerts should be indexed.
        self.assertEqual(response_dict["hits"]["total"]["value"], 5)

        pks_alerts_compare = [
            self.search_alert.pk,
            self.search_alert_2.pk,
            self.search_alert_3.pk,
            self.search_alert_4.pk,
            self.search_alert_5.pk,
        ]
        for alert_pk in pks_alerts_compare:
            self.assertTrue(
                AudioPercolator.exists(id=alert_pk),
                msg=f"Alert id: {alert_pk} was not indexed.",
            )

        # Call cl_index_search_alerts command for a not supported query type:
        call_command(
            "cl_index_search_alerts",
            pk_offset=0,
            alert_type=SEARCH_TYPES.RECAP,
        )

        mock_logger.info.assert_called_with(
            f"'{SEARCH_TYPES.RECAP}' Alert type indexing is not supported yet."
        )

    @mock.patch("cl.alerts.management.commands.cl_index_search_alerts.logger")
    def test_index_from_pk_offset(self, mock_logger):
        """Confirm elements with pk lt pk_offset are omitted from  indexing."""

        # Call cl_index_search_alerts command.
        call_command(
            "cl_index_search_alerts",
            pk_offset=self.search_alert_3.pk,
            alert_type=SEARCH_TYPES.ORAL_ARGUMENT,
        )

        s = AudioPercolator.search().query("match_all")
        response = s.execute()
        response_dict = response.to_dict()
        # Only 3 elements should be indexed.
        self.assertEqual(response_dict["hits"]["total"]["value"], 3)

        pks_alerts_compare = [
            self.search_alert_3.pk,
            self.search_alert_4.pk,
            self.search_alert_5.pk,
        ]
        for alert_pk in pks_alerts_compare:
            self.assertTrue(
                AudioPercolator.exists(id=alert_pk),
                msg=f"Alert id: {alert_pk} was not indexed.",
            )

    def test_avoid_indexing_no_valid_alert_query(self):
        """Confirm invalid alert queries are not indexed."""

        not_valid_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert OA Daily 2",
            query="q=DLY+Test+V2&type=oa&argued_after=1",
        )
        valid_alert = AlertFactory(
            user=self.user_profile.user,
            rate=Alert.DAILY,
            name="Test Alert OA Daily 2",
            query="q=DLY+Test+V2&type=oa",
        )
        # Call cl_index_search_alerts command.
        call_command(
            "cl_index_search_alerts",
            pk_offset=not_valid_alert.pk,
            alert_type=SEARCH_TYPES.ORAL_ARGUMENT,
        )

        s = AudioPercolator.search().query("match_all")
        response = s.execute()
        response_dict = response.to_dict()
        # Only 1 element should be indexed (valid_alert).
        self.assertEqual(response_dict["hits"]["total"]["value"], 1)
        self.assertTrue(
            AudioPercolator.exists(id=valid_alert.pk),
            msg=f"Alert id: {valid_alert.pk} was not indexed.",
        )
