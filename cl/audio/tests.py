from cl.lib.test_helpers import IndexedSolrTestCase, SitemapTest
from lxml import etree


class PodcastTest(IndexedSolrTestCase):
    def test_do_jurisdiction_podcasts_have_good_content(self):
        """Can we simply load a jurisdiction podcast page?"""
        response = self.client.get('/podcast/court/test/')
        self.assertEqual(200, response.status_code,
                         msg="Did not get 200 OK status code for podcasts.")
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ('//channel/title', 1),
            ('//channel/link', 1),
            ('//channel/description', 1),
            ('//channel/item', 3),
            ('//channel/item/title', 3),
            ('//channel/item/enclosure/@url', 3),
        )
        for test, count in node_tests:
            node_count = len(xml_tree.xpath(test))
            self.assertEqual(
                node_count,
                count,
                msg="Did not find %s node(s) with XPath query: %s. "
                    "Instead found: %s" % (count, test, node_count)
            )

    def test_do_search_podcasts_have_content(self):
        """Can we make a search podcast?

        Search podcasts are a subclass of theh Jurisdiction podcasts, so a
        simple test is all that's needed here.
        """
        response = self.client.get('/podcast/search/?q=court:test&type=oa')
        self.assertEqual(200, response.status_code,
                         msg="Did not get a 200 OK status code.")
        xml_tree = etree.fromstring(response.content)
        node_count = len(xml_tree.xpath('//channel/item'))
        expected_item_count = 3
        self.assertEqual(
            node_count,
            expected_item_count,
            msg="Did not get %s node(s) during search podcast generation. "
                "Instead found: %s" % (
                    expected_item_count,
                    node_count,
                )
        )


class AudioSitemapTest(SitemapTest):
    def __init__(self, *args, **kwargs):
        super(AudioSitemapTest, self).__init__(*args, **kwargs)
        # We expect 2X the number of items in the fixture b/c there are nodes
        # for the mp3 file and for the page on CourtListener.
        self.expected_item_count = 6
        self.sitemap_url = '/sitemap-oral-arguments.xml'

    def test_does_the_sitemap_have_content(self):
        super(AudioSitemapTest, self).does_the_sitemap_have_content()
