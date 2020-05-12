from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.timezone import now
from timeout_decorator import timeout_decorator

from cl.alerts.models import Alert, DocketAlert
from cl.alerts.tasks import send_docket_alert, update_docket_and_send_alert
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
        self.assertIn("successfully", r.content)
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
        self.assertIn("error creating your alert", r.content)
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
            court_id="cand",
            pacer_case_id="186730",
            docket_number="06-cv-07294",
            case_name="Foley v. Bates",
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

        # Create a new docket without any entries
        self.docket2 = Docket.objects.create(
            source=Docket.RECAP,
            court_id="dcd",
            pacer_case_id="191424",
            docket_number="17-cv-02534",
            case_name="ENGLISH v. TRUMP",
        )
        # Add an alert for it
        DocketAlert.objects.create(docket=self.docket2, user_id=1001)
        self.old = datetime(2018, 7, 17, 23, 55, 59, 100)
        self.new = datetime(2018, 7, 18, 23, 55, 59, 100)

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

    def test_triggering_pacer_docket_alert(self):
        """Does the alert trigger for pacer date_last_filing?"""
        update_docket_and_send_alert(self.docket2, self.old, False)
        # Does the alert go out? It should.
        if (
            settings.PACER_USERNAME
        ):  # hack to make tests work even without credentials
            self.assertEqual(len(mail.outbox), 1)

    def test_nothing_happens_for_timers_after_pacer_docket_date(self):
        """Do we avoid sending alerts for timers after pacer date_last_filing?"""
        update_docket_and_send_alert(self.docket2, self.new, False)
        # Do zero emails go out? None should.
        self.assertEqual(len(mail.outbox), 0)

    def test_nothing_happens_for_timers_after_de_creation(self):
        """Do we avoid sending alerts for timers after the de was created?"""
        send_docket_alert(self.docket.pk, self.after)

        # Do zero emails go out? None should.
        self.assertEqual(len(mail.outbox), 0)


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
        self.browser.find_element_by_id("username").send_keys("pandora")
        self.browser.find_element_by_id("password").send_keys("password")
        self.browser.find_element_by_id("password").submit()

        # And gets redirected to the SERP where they see a notice about their
        # alert being edited.
        self.assert_text_in_node("editing your alert", "body")
