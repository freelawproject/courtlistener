# coding=utf-8
"""
Functional testing of courtlistener RSS feeds
"""
import os

import feedparser
from django.conf import settings
from django.core.urlresolvers import reverse
from django.test.utils import override_settings

from cl.lib.storage import IncrementingFileSystemStorage
from cl.search.models import Court
from cl.tests.base import BaseSeleniumTest


@override_settings(
    MEDIA_ROOT=os.path.join(settings.INSTALL_ROOT, 'cl/assets/media/test/')
)
class FeedsFunctionalTest(BaseSeleniumTest):
    """Tests the Feeds page and functionality"""

    fixtures = ['test_court.json', 'judge_judy.json', 'functest_opinions.json',
                'functest_audio.json']

    @classmethod
    def setUpClass(cls):
        """
        Need to work around issue reported and fixed in Django project:
        https://code.djangoproject.com/ticket/26038

        Overwriting the current 1.8/1.9 logic on FileSystemStorage:
            def path(self, name):
                    return safe_join(self.location, name)

        """
        def patched_path(self, name):
            """ Patching Path method to use MEDIA_ROOT properly """
            return '%s%s' % (settings.MEDIA_ROOT, name,)

        IncrementingFileSystemStorage.path = patched_path
        super(FeedsFunctionalTest, cls).setUpClass()

    def test_can_get_to_feeds_from_homepage(self):
        """Can we get to the feeds/podcasts page from the homepage?"""
        self.browser.get(self.server_url)
        link = self.browser.find_element_by_link_text('Feeds & Podcasts')
        link.click()

        self.assertIn('Feeds', self.browser.title)
        self.assertIn('/feeds', self.browser.current_url)
        self.assert_text_in_body('Feeds')

    def test_feeds_page_shows_jurisdiction_links(self):
        """
        Does the feeds page show all the proper links for each jurisdiction?
        """
        courts = Court.objects.filter(
            in_use=True,
            has_opinion_scraper=True,
        )
        self.browser.get('%s%s' % (self.server_url, reverse('feeds_info')))
        self.assert_text_in_body('Jurisdiction Feeds for Opinions')

        for court in courts:
            link = self.browser.find_element_by_link_text(court.full_name)
            print "Testing link to %s..." % court.full_name,
            self.assertEqual(
                link.get_attribute('href'),
                '%s/feed/court/%s/' % (self.server_url, court.pk,)
            )
            link.click()
            print "clicked...",
            self.assertIn(
                'feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en-us"',
                self.browser.page_source
            )
            self.browser.back()
            print "✓"


    def test_all_jurisdiction_opinion_rss_feeds_usable_in_rss_reader(self):
        """
        Can the RSS feed for ALL jurisdictions render properly in an RSS reader?
        """
        f = feedparser.parse(
            '%s%s' % (self.server_url, reverse('all_jurisdictions_feed'))
        )
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
        url = '%s%s' % \
            (
                self.server_url,
                reverse('jurisdiction_feed', kwargs={'court': 'test'})
            )
        f = feedparser.parse(url)
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
        f = feedparser.parse(
            '%s%s' % (self.server_url, reverse('all_jurisdictions_feed'))
        )
        for entry in f.entries:
            if entry.enclosures is not None:
                self.assertEqual(len(entry.enclosures), 1)
                self.assertTrue(len(entry.enclosures[0].type) > 0)
                self.assertTrue(entry.enclosures[0].length > 1)
                r = self.client.get(entry.enclosures[0].href, follow=True)
                self.assertEqual(
                    r.status_code,
                    200,
                    'GET %s should result in HTTP 200' %
                    entry.enclosures[0].href
                )
                self.assertIn('attachment;', r['Content-Disposition'])

    def test_oral_argument_feeds_contain_valid_mp3_links(self):
        """
        For Oral Arguments, does the feed provide valid links to MP3 content?
        """
        f = feedparser.parse(
            '%s%s' % (self.server_url, reverse('all_jurisdictions_podcast'))
        )
        for entry in f.entries:
            if entry.enclosures is not None:
                self.assertEqual(len(entry.enclosures), 1)
                r = self.client.get(entry.enclosures[0].href, follow=True)
                self.assertEqual(
                    r.status_code,
                    200,
                    'GET %s should result in HTTP 200' %
                    entry.enclosures[0].href
                )
                self.assertEqual(r['Content-Type'], 'audio/mpeg')

    def test_search_based_opinion_feed(self):
        """
        Can a user perform a search via CL and use the RSS feed feature?
        """
        # Dora goes to CL and searches for Bonvini
        self.browser.get(self.server_url)
        self.browser.find_element_by_id('id_q').send_keys('bonvini\n')

        # She's brought to the SERP.
        self.assertIn('Search Results', self.browser.title)
        articles = self.browser.find_elements_by_tag_name('article')
        link_titles = [a.find_element_by_tag_name('a').text for a in articles]

        # Seeing the results, she wants to keep tabs on any new Opinions that
        # come into CL related to her Search. She notices a little RSS icon
        # and decides to click it
        result_count = self.browser.find_element_by_id('result-count')
        rss_link = result_count.find_element_by_tag_name('a')
        rss_link.click()

        # She captures the URL and pops it into her favorite RSS Reader
        self.assertIn(
            'feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en-us"',
            self.browser.page_source
        )
        rss_url = self.browser.current_url

        # The RSS Reader validates the feed and Dora is thrilled! The same
        # first page of results are there!
        f = feedparser.parse(rss_url)
        self.assertEqual(len(link_titles), len(f.entries))

        for entry in f.entries:
            found_similar_title = False
            for title in link_titles:
                if entry.title in title:
                    found_similar_title = True
            self.assertTrue(
                found_similar_title,
                'Should have seen a search result similar to %s' % entry.title
            )
