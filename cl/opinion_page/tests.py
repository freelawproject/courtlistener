from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase, override_settings
from rest_framework.status import HTTP_200_OK, HTTP_404_NOT_FOUND, \
    HTTP_302_FOUND

from cl.lib import sunburnt
from cl.lib.test_helpers import SitemapTest
from cl.sitemap import make_sitemap_solr_params


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

    def assertStatus(self, r, status):
        self.assertEqual(
            r.status_code,
            status,
            msg="Didn't get a {expected} status code. Got {got} "
                "instead.".format(expected=status, got=r.status_code)
        )

    def test_with_and_without_a_citation(self):
        """Make sure that the url paths are working properly."""
        r = self.client.get(reverse('citation_redirector'))
        self.assertStatus(r, HTTP_200_OK)

        citation = {'reporter': 'F.2d', 'volume': '56', 'page': '9'}

        # Are we redirected to the correct place when we use GET or POST?
        r = self.client.get(
            reverse('citation_redirector', kwargs=citation),
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)

        r = self.client.post(
            reverse('citation_redirector'),
            citation,
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)

    def test_unknown_citation(self):
        """Do we get a 404 message if we don't know the citation?"""
        r = self.client.get(
            reverse('citation_redirector', kwargs={
                'reporter': 'bad-reporter',
                'volume': '1',
                'page': '1',
            }),
        )
        self.assertStatus(r, HTTP_404_NOT_FOUND)

    def test_long_numbers(self):
        """Do really long WL citations work?"""
        r = self.client.get(
            reverse('citation_redirector', kwargs={
                'reporter': 'WL',
                'volume': '2012',
                'page': '2995064'
            }),
        )
        self.assertStatus(r, HTTP_404_NOT_FOUND)


class ViewRecapDocketTest(TestCase):
    fixtures = ['test_objects_search.json', 'judge_judy.json']

    def test_regular_docket_url(self):
        """Can we load a regular docket sheet?"""
        r = self.client.get(reverse('view_docket', args=[1, 'case-name']))
        self.assertEqual(r.status_code, HTTP_200_OK)

    def test_recap_docket_url(self):
        """Can we redirect to a regular docket URL from a recap/uscourts.*
        URL?
        """
        r = self.client.get(reverse('redirect_docket_recap', kwargs={
            'court': 'test',
            'pacer_case_id': '666666',
        }), follow=True)
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)


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
        params = make_sitemap_solr_params('dateFiled asc', 'o_sitemap')
        params['rows'] = 1000

        r = conn.raw_query(**params).execute()

        # the underlying SitemapTest relies on counting url elements in the xml
        # response...this logic mimics the creation of the xml, so we at least
        # know what we *should* get getting for a count if the SiteMapTest's
        # HTTP client-based test gets an HTTP 200
        count = 0
        for result in r:
            if result.get('local_path'):
                count += 2
            else:
                count += 1
        return count

    def test_does_the_sitemap_have_content(self):
        # Class attributes are set, just run the test in super.
        self.expected_item_count = self.get_expected_item_count()
        super(OpinionSitemapTest, self).does_the_sitemap_have_content()
