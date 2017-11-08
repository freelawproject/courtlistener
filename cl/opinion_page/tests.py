from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase, override_settings
from rest_framework.status import HTTP_200_OK, HTTP_404_NOT_FOUND, \
    HTTP_302_FOUND

from cl.lib import sunburnt
from cl.lib.test_helpers import SitemapTest
from cl.sitemap import make_sitemap_solr_params
from cl.opinion_page.sankey import add_and_link_node


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


class TestSankeyDiagramUtils(TestCase):
    """Test that we can do the right things when generating Sankey diagrams"""

    def setUp(self):
        self.nodes = []
        self.links = []
        self.simple_party = {
            'type': 'party',
            'name': 'Mmmmm......pizza!',
            'id': 2,
        }
        self.simple_atty = {
            'type': 'attorney',
            'name': 'Bing Crosby',
            'id': 3,
        }

    def test_add_link_node_type_is_party(self):
        """When the type is party, do we simply add the node?"""
        add_and_link_node(self.nodes, self.links, None, self.simple_party)
        expected_node_count = 1
        expected_link_count = 0
        self.assertEqual(len(self.nodes), expected_node_count)
        self.assertEqual(len(self.links), expected_link_count)

    def test_add_atty_twice_only_adds_one_atty(self):
        """If we add the same attorney twice, does it get merged?"""
        party_location = add_and_link_node(self.nodes, self.links, None,
                                           self.simple_party)
        atty_location1 = add_and_link_node(self.nodes, self.links,
                                           party_location, self.simple_atty)
        expected_node_count = 2
        expected_link_count = 1
        self.assertEqual(len(self.nodes), expected_node_count)
        self.assertEqual(len(self.links), expected_link_count)

        # Add another party, but they have same atty
        self.simple_party.update({'name': 'taco'})
        party_location = add_and_link_node(self.nodes, self.links, None,
                                           self.simple_party)
        atty_location2 = add_and_link_node(self.nodes, self.links,
                                           party_location, self.simple_atty)
        expected_node_count = 3
        expected_link_count = 2
        self.assertEqual(atty_location1, atty_location2)
        self.assertEqual(len(self.nodes), expected_node_count)
        self.assertEqual(len(self.links), expected_link_count)


