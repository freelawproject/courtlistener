from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import Client, TestCase

from cl.alerts.models import Alert
from cl.tests.base import BaseSeleniumTest


class AlertTest(TestCase):
    fixtures = ['test_court.json', 'authtest_data.json']

    def setUp(self):
        # Set up some handy variables
        self.client = Client()
        self.alert_params = {
            'query': 'q=asdf',
            'name': 'dummy alert',
            'rate': 'dly',
        }

    def test_create_alert(self):
        """Can we create an alert by sending a post?"""
        self.client.login(username='pandora', password='password')
        r = self.client.post(reverse('show_results'), self.alert_params, follow=True)
        self.assertEqual(r.redirect_chain[0][1], 302)
        self.assertIn('successfully', r.content)
        self.client.logout()

    def test_fail_gracefully(self):
        """Do we fail gracefully when an invalid alert form is sent?"""
        # Use a copy to shield other tests from changes.
        bad_alert_params = self.alert_params.copy()
        # Break the form
        bad_alert_params.pop('query', None)
        self.client.login(username='pandora', password='password')
        r = self.client.post('/', bad_alert_params, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('error creating your alert', r.content)
        self.client.logout()


class AlertSeleniumTest(BaseSeleniumTest):
    fixtures = ['test_court.json', 'authtest_data.json']

    def setUp(self):
        # Set up some handy variables
        self.client = Client()
        self.alert_params = {
            'query': 'q=asdf',
            'name': 'dummy alert',
            'rate': 'dly',
        }
        super(AlertSeleniumTest, self).setUp()

    def test_edit_alert(self):
        """Can we edit the alert and see the message about it being edited?"""
        user = User.objects.get(username='pandora')
        alert = Alert(
            user=user,
            name=self.alert_params['name'],
            query=self.alert_params['query'],
            rate=self.alert_params['rate'],
        )
        alert.save()

        # Pan tries to edit their alert
        self.browser.get(
            '{url}{path}?{q}&edit_alert={pk}'.format(
                url=self.server_url,
                path=reverse('show_results'),
                q=alert.query,
                pk=alert.pk,
            ))

        # But winds up at the sign in form
        self.assertIn(reverse('sign-in'), self.browser.current_url)

        # So Pan signs in.
        self.browser.find_element_by_id('username').send_keys('pandora')
        self.browser.find_element_by_id('password').send_keys('password' + '\n')

        # And gets redirected to the SERP where they see a notice about their
        # alert being edited.
        self.assert_text_in_body("editing your alert")
