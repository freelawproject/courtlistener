from datetime import timedelta
from unittest import mock

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils.timezone import now
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_404_NOT_FOUND,
)
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator

from cl.alerts.factories import DocketAlertWithParentsFactory
from cl.alerts.management.commands.handle_old_docket_alerts import (
    build_user_report,
)
from cl.alerts.models import Alert, DocketAlert
from cl.alerts.tasks import send_alert_and_webhook
from cl.api.factories import WebhookFactory
from cl.api.models import WebhookEvent, WebhookEventType
from cl.lib.test_helpers import SimpleUserDataMixin
from cl.search.models import Court, Docket, DocketEntry, RECAPDocument
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest
from cl.tests.cases import APITestCase, TestCase
from cl.tests.utils import make_client
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

    def test_create_alert(self) -> None:
        """Can we create an alert by sending a post?"""
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        r = self.client.post(
            reverse("show_results"), self.alert_params, follow=True
        )
        self.assertEqual(r.redirect_chain[0][1], 302)
        self.assertIn("successfully", r.content.decode())
        self.client.logout()

    def test_fail_gracefully(self) -> None:
        """Do we fail gracefully when an invalid alert form is sent?"""
        # Use a copy to shield other tests from changes.
        bad_alert_params = self.alert_params.copy()
        # Break the form
        bad_alert_params.pop("query", None)
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )
        r = self.client.post("/", bad_alert_params, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("error creating your alert", r.content.decode())
        self.client.logout()

    def test_new_alert_gets_secret_key(self) -> None:
        """When you create a new alert, does it get a secret key?"""
        self.assertTrue(self.alert.secret_key)

    def test_are_alerts_disabled_when_the_link_is_visited(self) -> None:
        self.assertEqual(self.alert.rate, self.alert_params["rate"])
        self.client.get(reverse("disable_alert", args=[self.alert.secret_key]))
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.rate, "off")

    def test_are_alerts_enabled_when_the_link_is_visited(self) -> None:
        self.assertEqual(self.alert.rate, self.alert_params["rate"])
        self.alert.rate = "off"
        new_rate = "wly"
        path = reverse("enable_alert", args=[self.alert.secret_key])
        self.client.get(f"{path}?rate={new_rate}")
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.rate, new_rate)


class MockResponse:
    """Mock a Request Response"""

    def __init__(self, text, status_code):
        self.text = text
        self.status_code = status_code


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
        "cl.alerts.tasks.requests.post",
        side_effect=lambda *args, **kwargs: MockResponse("Testing", 200),
    )
    def test_triggering_docket_webhook(self, mock_post) -> None:
        """Does the docket alert trigger the DocketAlert Webhook?"""
        send_alert_and_webhook(self.docket.pk, self.before)
        webhook_triggered = WebhookEvent.objects.filter(webhook=self.webhook)

        # Does the webhook was triggered?
        self.assertEqual(webhook_triggered.count(), 1)
        content = webhook_triggered.first().content
        # Compare the content of the webhook to the recap document
        pacer_doc_id = content["results"][0]["recap_documents"][0][
            "pacer_doc_id"
        ]
        self.assertEqual("232322332", pacer_doc_id)


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
        self.alert.date_created = now() - timedelta(days=365)
        self.alert.save()

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
            self.assertEqual(report.ninety_ago, [self.alert.docket])


class AlertSeleniumTest(BaseSeleniumTest):
    fixtures = ["test_court.json"]

    def setUp(self) -> None:
        # Set up some handy variables
        self.client = Client()
        self.alert_params = {
            "query": "q=asdf",
            "name": "dummy alert",
            "rate": "dly",
        }
        UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )
        super(AlertSeleniumTest, self).setUp()

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
