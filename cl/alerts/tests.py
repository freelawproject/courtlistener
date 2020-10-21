from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from django.test import Client, TestCase
from django.utils.timezone import now
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator

from cl.alerts.management.commands.handle_old_docket_alerts import (
    build_user_report,
)
from cl.alerts.models import Alert, DocketAlert
from cl.alerts.tasks import send_docket_alert
from cl.search.models import Docket, DocketEntry, RECAPDocument
from cl.tests.base import BaseSeleniumTest, SELENIUM_TIMEOUT


class AlertTest(TestCase):
    fixtures = ["test_court.json", "authtest_data.json"]

    def setUp(self):
        # Set up some handy variables
        self.alert_params = {
            "query": "q=asdf",
            "name": "dummy alert",
            "rate": "dly",
        }
        self.alert = Alert.objects.create(user_id=1001, **self.alert_params)

    def tearDown(self):
        Alert.objects.all().delete()

    def test_create_alert(self):
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

    def test_fail_gracefully(self):
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

    def test_new_alert_gets_secret_key(self):
        """When you create a new alert, does it get a secret key?"""
        self.assertTrue(self.alert.secret_key)

    def test_are_alerts_disabled_when_the_link_is_visited(self):
        self.assertEqual(self.alert.rate, self.alert_params["rate"])
        self.client.get(reverse("disable_alert", args=[self.alert.secret_key]))
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.rate, "off")

    def test_are_alerts_enabled_when_the_link_is_visited(self):
        self.assertEqual(self.alert.rate, self.alert_params["rate"])
        self.alert.rate = "off"
        new_rate = "wly"
        path = reverse("enable_alert", args=[self.alert.secret_key])
        self.client.get("%s?rate=%s" % (path, new_rate))
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.rate, new_rate)


class DocketAlertTest(TestCase):
    """Do docket alerts work properly?"""

    fixtures = ["test_court.json", "authtest_data.json"]

    def setUp(self):
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
        DocketAlert.objects.create(docket=self.docket, user_id=1001)

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

    def tearDown(self):
        Docket.objects.all().delete()
        DocketAlert.objects.all().delete()
        DocketEntry.objects.all().delete()
        # Clear the outbox
        mail.outbox = []

    def test_triggering_docket_alert(self):
        """Does the alert trigger when it should?"""
        send_docket_alert(self.docket.pk, self.before)

        # Does the alert go out? It should.
        self.assertEqual(len(mail.outbox), 1)

    def test_nothing_happens_for_timers_after_de_creation(self):
        """Do we avoid sending alerts for timers after the de was created?"""
        send_docket_alert(self.docket.pk, self.after)

        # Do zero emails go out? None should.
        self.assertEqual(len(mail.outbox), 0)


class DisableDocketAlertTest(TestCase):
    """Do old docket alerts get disabled or alerted properly?"""

    fixtures = ["test_court.json", "authtest_data.json"]

    def setUp(self):
        self.now = now()

        # Create a terminated docket
        self.docket = Docket.objects.create(
            source=Docket.RECAP,
            court_id="scotus",
            date_terminated="2020-01-01",
            pacer_case_id="asdf",
            docket_number="12-cv-02354",
            case_name="Vargas v. Wilkins",
        )

        # Add an alert for it
        self.user = User.objects.get(pk=1001)
        self.alert = DocketAlert.objects.create(
            docket=self.docket, user=self.user
        )

    def tearDown(self):
        Docket.objects.all().delete()
        DocketAlert.objects.all().delete()

    def backdate_alert(self):
        self.alert.date_created = self.now - timedelta(days=365)
        self.alert.save()

    def test_alert_created_recently_termination_year_ago(self):
        self.docket.date_terminated = now() - timedelta(days=365)
        self.docket.save()

        report = build_user_report(self.user)
        # This alert was recent (the test created it a few seconds ago),
        # so no actions should be taken
        self.assertEqual(
            report.total_count(),
            0,
            msg="Got dockets when we shouldn't have gotten any: %s"
            % report.__dict__,
        )

    def test_old_alert_recent_termination(self):
        """Flag it if alert is old and item was terminated 90-97 days ago"""
        self.backdate_alert()
        for i in range(90, 97):
            new_date_terminated = now() - timedelta(days=i)
            print("Trying a date_terminated of %s" % new_date_terminated)
            self.docket.date_terminated = new_date_terminated
            self.docket.save()
            report = build_user_report(self.user, delete=True)
            self.assertEqual(report.ninety_ago, [self.docket])


class AlertSeleniumTest(BaseSeleniumTest):
    fixtures = ["test_court.json", "authtest_data.json"]

    def setUp(self):
        # Set up some handy variables
        self.client = Client()
        self.alert_params = {
            "query": "q=asdf",
            "name": "dummy alert",
            "rate": "dly",
        }
        super(AlertSeleniumTest, self).setUp()

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_edit_alert(self):
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
