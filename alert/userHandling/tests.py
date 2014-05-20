# coding=utf-8
from datetime import timedelta
from django.test import TestCase
from django.utils.timezone import now
from alert.userHandling.models import UserProfile


class UserTest(TestCase):
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
        response = self.client.post('/register/', params, follow=True)
        self.assertRedirects(response, 'http://testserver/register/success/?next=/')

    def test_signing_in(self):
        """Can we create a user on the backend then sign them into the front end?"""
        params = {
            'username': 'pandora',
            'password': 'password',
        }
        response = self.client.post('/sign-in/', params, follow=True)
        self.assertRedirects(response, 'http://testserver/')

    def test_confirming_an_email_address(self):
        """Tests whether we can confirm the case where an email is associated with a single account."""
        # Update the expiration since the fixture has one some time ago.
        u = UserProfile.objects.get(pk=2)
        u.key_expires = now() + timedelta(days=2)
        u.save()

        response = self.client.get('/email/confirm/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/')
        self.assertEqual(200, response.status_code,
                         msg="Did not get 200 code when activating account. Instead got %s" % response.status_code)
        self.assertIn('has been confirmed', response.content,
                      msg="Test string not found in response.content")

    def test_confirming_an_email_when_it_is_associated_with_multiple_accounts(self):
        """Tests the trickier case when an email is associated with many accounts."""
        UserProfile.objects.filter(pk__in=(3, 4,)).update(key_expires=now() + timedelta(days=2))
        response = self.client.get('/email/confirm/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaab/')
        self.assertIn('has been confirmed', response.content,
                      msg="Test string not found in response.content")
        self.assertEqual(200, response.status_code,
                         msg="Did not get 200 code when activating account. Instead got %s" % response.status_code)
        ups = UserProfile.objects.filter(pk__in=(3, 4,))
        for up in ups:
            self.assertTrue(up.email_confirmed)

