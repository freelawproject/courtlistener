from cl.lib.test_helpers import SitemapTest
from django.test import TestCase
from django.test.client import Client
from cl.lib import sunburnt
from django.conf import settings


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


class OpinionSitemapTest(SitemapTest):
    def __init__(self, *args, **kwargs):
        super(OpinionSitemapTest, self).__init__(*args, ** kwargs)
        self.sitemap_url = '/sitemap-opinions.xml'

    def test_does_the_sitemap_have_content(self):
        # OpinionsSitemap uses the solr index to generate the page, so
        # the only accurate count to exect comes from the index itself
        # which will also be based on the fixtures.
        conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
        params = {
            'q': '*:*',
            'rows': 1000,
            'start': 0,
            'fl': ','.join([
                'absolute_url',
                'dateFiled',
                'local_path',
                'citeCount',
                'timestamp',
            ]),
            'sort': 'dateFiled asc',
            'caller': 'opinion_sitemap_maker',
        }
        search_results_object = conn.raw_query(**params).execute()
        count = 0
        # the underlying SitemapTest relies on counting url elements in
        # the xml response...this logic mimics the creation of the xml,
        # so we at least know what we *should* get getting for a count
        # if the SiteMapTest's HTTP client-based test gets an HTTP 200
        for result in search_results_object:
            if result.get('local_path') and result.get('local_path') != '':
                count += 3
            else:
                count += 2

        self.expected_item_count = count
        super(OpinionSitemapTest, self).does_the_sitemap_have_content()
