from django.test import TestCase


class ContactTest(TestCase):
    fixtures = ['authtest_data.json']

    def test_multiple_requests_request(self):
        """ Is state persisted in the contact form?

        The contact form is abstracted in a way that it can have peculiar behavior when called multiple times. This test
        makes sure that that behavior does not regress.
        """
        self.client.login(username='pandora', password='password')
        self.client.get('/contact/')
        self.client.logout()

        # Now, as an anonymous user, we get the page again. If the bug is resolved, we should not see anything about
        # the previously logged-in user, pandora.
        r = self.client.get('/contact/')
        self.assertNotIn('pandora', r.content)

