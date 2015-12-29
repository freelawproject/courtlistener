# coding=utf-8
"""
Functional testing of courtlistener RSS feeds
"""
from cl.search.models import Court
from cl.tests.base import BaseSeleniumTest
import feedparser


class FeedsFunctionalTest(BaseSeleniumTest):
    """Tests the Feeds page and functionality"""

    fixtures = ['test_court.json', 'authtest_data.json',
        'judge_judy.json', 'test_objects_search.json',
        'functest_opinions.json', 'test_objects_audio.json']

    def test_can_get_to_feeds_from_homepage(self):
        """Can we get to the feeds/podcasts page from the homepage?"""
        self.browser.get(self.server_url)
        link = self.browser.find_element_by_link_text('Feeds & Podcasts')
        link.click()

        self.assertIn('Feeds & Podcasts', self.browser.title)
        self.assertIn('/feeds', self.browser.current_url)
        self.assert_text_in_body('Feeds & Podcasts')

    def test_feeds_page_shows_jurisdiction_links(self):
        """
        Does the feeds page show all the proper links for each jurisdiction?
        """

        courts = Court.objects.all()
        self.browser.get('%s/feeds' % (self.server_url,))
        self.assert_text_in_body('Jurisdiction Feeds for Opinions')

        for court in courts:
            link = self.browser.find_element_by_link_text(court.full_name)
            self.assertEqual(
                link.get_attribute('href'),
                '%s/feed/court/%s/' % (self.server_url, court.pk,)
            )
            link.click()
            self.assertIn(
                'feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en-us"',
                self.browser.page_source
            )
            self.browser.back()

    def test_all_jurisdiction_opinion_rss_feeds_usable_in_rss_reader(self):
        """
        Can the RSS feed for ALL jurisdictions render properly in an RSS reader?
        """
        f = feedparser.parse('%s/feed/court/all/' % (self.server_url,))
        self.assertEqual(
            u'CourtListener.com: All Opinions (High Volume)',
            f.feed.title
        )
        # Per https://pythonhosted.org/feedparser/bozo.html
        self.assertEqual(f.bozo, 0, 'Feed should be wellformed')

    def test_court_opinion_rss_feeds_usable_in_rss_reader(self):
        """
        Can the RSS feeds be properly used in an RSS Reader?
        """

        f = feedparser.parse('%s/feed/court/test/' % (self.server_url,))
        self.assertEqual(
            u'CourtListener.com: All opinions for the Testing Supreme Court',
            f.feed.title
        )
        # Per https://pythonhosted.org/feedparser/bozo.html
        self.assertEqual(f.bozo, 0, 'Feed should be wellformed')

    def test_opinion_rss_feeds_contain_valid_attachment_links(self):
        """
        For Opinions with stored PDFs, does the feed provide valid links
        to the CourtListener copy of the original PDF?
        """
        import requests
        f = feedparser.parse('%s/feed/court/test/' % (self.server_url,))
        for entry in f.entries:
            if entry.enclosures is not None:
                self.assertEqual(len(entry.enclosures), 1)
                print 'Enclosure for entry (%s):\n%s' \
                    % (entry.id, entry.enclosures[0].href)
                # Django returnes a 301 Moved Permanently so we must follow
                r = self.client.get(entry.enclosures[0].href, follow=True)
                self.assertEqual(r.status_code, 200)
