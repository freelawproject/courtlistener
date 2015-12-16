# coding=utf-8
from datetime import timedelta
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.urlresolvers import reverse
from django.test import LiveServerTestCase
from django.utils.timezone import now
from django.utils.http import urlsafe_base64_encode
from selenium import webdriver

from cl.users.models import UserProfile


class UserTest(LiveServerTestCase):
    fixtures = ['authtest_data.json']

    def test_creating_a_new_user(self):
        """Can we register a new user in the front end?"""
        params = {
            'username': 'pan',
            'email': 'pan@courtlistener.com',
            'password1': 'a',
            'password2': 'a',
            'first_name': 'dora',
            'last_name': '☠☠☠☠☠☠☠☠☠☠☠',
            'skip_me_if_alive': '',
        }
        response = self.client.post(
            '{host}{path}'.format(
                host=self.live_server_url,
                path=reverse('register'),
            ),
            params,
            follow=True,
        )
        self.assertRedirects(
            response,
            '{host}{path}?next=/'.format(
                host='http://testserver',
                path=reverse('register_success')
            ),
            host=self.live_server_url,
        )

    def test_signing_in(self):
        """Can we create a user on the backend then sign them in"""
        params = {
            'username': 'pandora',
            'password': 'password',
        }
        r = self.client.post(reverse('sign-in'), params, follow=True)
        self.assertRedirects(r, 'http://testserver/')

    def test_confirming_an_email_address(self):
        """Tests whether we can confirm the case where an email is associated
        with a single account.
        """
        # Update the expiration since the fixture has one some time ago.
        u = UserProfile.objects.get(pk=2)
        u.key_expires = now() + timedelta(days=2)
        u.save()

        r = self.client.get(reverse(
            'email_confirm',
            args=['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
        ))
        self.assertEqual(200, r.status_code,
                         msg="Did not get 200 code when activating account. "
                             "Instead got %s" % r.status_code)
        self.assertIn('has been confirmed', r.content,
                      msg="Test string not found in response.content")

    def test_confirming_an_email_when_it_is_associated_with_multiple_accounts(self):
        # Test the trickier case when an email is associated with many accounts
        UserProfile.objects.filter(pk__in=(3, 4,))\
            .update(key_expires=now() + timedelta(days=2))
        r = self.client.get(reverse(
            'email_confirm',
            args=['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaab'],
        ))
        self.assertIn('has been confirmed', r.content,
                      msg="Test string not found in response.content")
        self.assertEqual(200, r.status_code,
                         msg="Did not get 200 code when activating account. "
                             "Instead got %s" % r.status_code)
        ups = UserProfile.objects.filter(pk__in=(3, 4,))
        for up in ups:
            self.assertTrue(up.email_confirmed)


class LiveUserTest(LiveServerTestCase):
    fixtures = ['authtest_data.json']

    @classmethod
    def setUpClass(cls):
        cls.selenium = webdriver.PhantomJS(
            executable_path='/usr/local/phantomjs/phantomjs',
            service_log_path='/var/log/courtlistener/django.log',
        )
        super(LiveUserTest, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super(LiveUserTest, cls).tearDownClass()

    def test_reset_password_using_the_HTML(self):
        """Can we use the HTML form to send a reset email?

        This test checks that the email goes out and that the status code
        returned is valid.
        """
        self.selenium.get('{host}{path}'.format(
            host=self.live_server_url,
            path=reverse('password_reset'),
        ))
        email_input = self.selenium.find_element_by_name("email")
        email_input.send_keys('pandora@courtlistener.com')
        email_input.submit()

        #self.selenium.save_screenshot('/home/mlissner/phantom.png')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            self.selenium.current_url,
            '{host}{path}'.format(
                host=self.live_server_url,
                path=reverse('password_reset_done'),
            )
        )

    def test_set_password_using_the_HTML(self):
        """Can we reset our password after generating a confirmation link?"""
        # Generate a token and use it to visit a generated reset URL
        up = UserProfile.objects.get(pk=1)
        token = default_token_generator.make_token(up.user)
        url = '{host}{path}'.format(
            host=self.live_server_url,
            path=reverse('confirm_password', kwargs={
                'uidb64': urlsafe_base64_encode(str(up.user.pk)),
                'token': token,
            }),
        )
        self.selenium.get(url)
        #self.selenium.save_screenshot('/home/mlissner/phantom.png')

        self.assertIn(
            "Enter New Password",
            self.selenium.page_source
        )

        # Next, change the user's password and submit the form.
        pwd1 = self.selenium.find_element_by_name('new_password1')
        pwd1.send_keys('password')
        pwd2 = self.selenium.find_element_by_name('new_password2')
        pwd2.send_keys('password')
        pwd2.submit()

        self.assertEqual(
            self.selenium.current_url,
            '{host}{path}'.format(
                host=self.live_server_url,
                path=reverse('password_reset_complete'),
            )
        )
