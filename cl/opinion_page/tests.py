from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase, override_settings
from django.test.client import Client

from cl.lib import sunburnt
from cl.lib.test_helpers import SitemapTest
from cl.sitemap import opinion_solr_params


class ViewDocumentTest(TestCase):
    fixtures = ['test_objects_search.json', 'judge_judy.json']

    def test_simple_url_check_for_document(self):
        """Does the page load properly?"""
        response = self.client.get('/opinion/1/asdf/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('33 state 1', response.content)


class CitationRedirectorTest(TestCase):
    """Tests to make sure that the basic citation redirector is working."""
    fixtures = ['test_objects_search.json', 'judge_judy.json']

    def _200_status(self, r):
        self.assertEqual(
            r.status_code,
            200,
            msg="Didn't get a 200 status code. Got {code} "
                "instead.".format(
                    code=r.status_code,
                ))

    def test_with_and_without_a_citation(self):
        """Make sure that the url paths are working properly."""
        r = self.client.get(reverse('citation_redirector'))
        self._200_status(r)

        citation = {'reporter': 'F.2d', 'volume': '56', 'page': '9'}

        # Are we redirected to the correct place when we use GET or POST?
        r = self.client.get(
            reverse('citation_redirector', kwargs=citation),
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], 302)

        r = self.client.post(
            reverse('citation_redirector'),
            citation,
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], 302)


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


@override_settings(
    SOLR_OPINION_URL=settings.SOLR_OPINION_TEST_URL,
    SOLR_AUDIO_URL=settings.SOLR_AUDIO_TEST_URL,
)
class OpinionSitemapTest(SitemapTest):
    def __init__(self, *args, **kwargs):
        super(OpinionSitemapTest, self).__init__(*args, ** kwargs)
        self.sitemap_url = reverse('opinion_sitemap')

    def get_expected_item_count(self):
        # OpinionsSitemap uses the solr index to generate the page, so the only
        # accurate count comes from the index itself which will also be based on
        # the fixtures.
        conn = sunburnt.SolrInterface(settings.SOLR_OPINION_URL, mode='r')
        opinion_solr_params['rows'] = 1000

        search_results_object = conn.raw_query(**opinion_solr_params).execute()

        # the underlying SitemapTest relies on counting url elements in the xml
        # response...this logic mimics the creation of the xml, so we at least
        # know what we *should* get getting for a count if the SiteMapTest's
        # HTTP client-based test gets an HTTP 200
        count = 0
        for result in search_results_object:
            if result.get('local_path'):
                count += 3
            else:
                count += 2
        return count

    def test_does_the_sitemap_have_content(self):
        # Class attributes are set, just run the test in super.
        self.expected_item_count = self.get_expected_item_count()
        super(OpinionSitemapTest, self).does_the_sitemap_have_content()
