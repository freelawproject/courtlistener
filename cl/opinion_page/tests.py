from django.test import TestCase
from django.test.client import Client


class ViewDocumentTest(TestCase):
    fixtures = ['test_objects_search.json', 'judge_judy.json']

    def test_simple_url_check_for_document(self):
        """Does the page load properly?"""
        response = self.client.get('/opinion/1/asdf/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('33 state 1', response.content)


class RedirectionTest(TestCase):
    """We have a number of redirections in place now. These tests make sure that
    those tests actually work.
    """

    fixtures = ['test_objects_search.json', 'judge_judy.json']

    def test_various_redirections(self):
        self.client = Client()
        old_urls = [
            # Opinion pages
            ('/ca3/a/asdf/', '/opinion/9/asdf/'),
            ('/ca3/a/asdf/authorities/', '/opinion/9/asdf/authorities/'),

            # Cited-by pages
            ('/opinion/9/asdf/cited-by/', '/?q=cites%3A9'),
            ('/ca3/a/asdf/cited-by/', '/?q=cites%3A9'),
            ('/feed/a/cited-by/', '/feed/search/?q=cites%3A9'),
            ('/feed/9/cited-by/', '/feed/search/?q=cites%3A9'),
        ]
        for target, destination in old_urls:
            print "Does %s redirect to %s" % (target, destination)
            r = self.client.get(target, follow=True)
            self.assertEquals(
                r.redirect_chain[0][0],
                'http://testserver%s' % destination,
            )
