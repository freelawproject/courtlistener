from alert.lib.test_helpers import SolrTestCase
from lxml import etree


class PodcastTest(SolrTestCase):
    def test_do_podcasts_have_good_content(self):
        """Can we simply load the podcast page?"""
        response = self.client.get('/podcast/court/test/')
        self.assertEqual(200, response.status_code,
                         msg="Did not get 200 OK status code for podcasts.")
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ('//channel/title', 1),
            ('//channel/link', 1),
            ('//channel/description', 1),
            ('//channel/item', 2),
            ('//channel/item/title', 2),
            ('//channel/item/enclosure/@url', 2),
        )
        for test, count in node_tests:
            node_count = len(xml_tree.xpath(test))
            self.assertEqual(
                node_count,
                count,
                msg="Did not find %s node(s) with XPath query: %s. "
                    "Instead found: %s" % (count, test, node_count)
            )
