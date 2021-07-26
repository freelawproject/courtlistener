"""
Functional testing of courtlistener RSS feeds
"""
import os

import feedparser
from django.conf import settings
from django.test.utils import override_settings
from django.urls import reverse
from selenium.webdriver.common.by import By
from timeout_decorator import timeout_decorator

from cl.search.models import Court
from cl.tests.base import SELENIUM_TIMEOUT, BaseSeleniumTest


@override_settings(
    MEDIA_ROOT=os.path.join(settings.INSTALL_ROOT, "cl/assets/media/test/")
)
class FeedsFunctionalTest(BaseSeleniumTest):
    """Tests the Feeds page and functionality"""

    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "functest_opinions.json",
        "functest_audio.json",
    ]

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_can_get_to_feeds_from_homepage(self) -> None:
        """Can we get to the feeds/podcasts page from the homepage?"""
        self.browser.get(self.live_server_url)
        link = self.browser.find_element(By.LINK_TEXT, "Feeds")
        link.click()

        self.assertIn("Feeds", self.browser.title)
        self.assertIn("/feeds", self.browser.current_url)
        self.assert_text_in_node("Feeds", "body")

        # Podcasts
        self.browser.get(self.live_server_url)
        link = self.browser.find_element(By.LINK_TEXT, "Podcasts")
        link.click()

        self.assertIn("Podcasts", self.browser.title)
        self.assertIn("/podcasts", self.browser.current_url)
        self.assert_text_in_node("Podcasts", "body")

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_feeds_page_shows_jurisdiction_links(self) -> None:
        """
        Does the feeds page show all the proper links for each jurisdiction?
        """
        courts = Court.objects.filter(in_use=True, has_opinion_scraper=True)
        self.browser.get(f"{self.live_server_url}{reverse('feeds_info')}")
        self.assert_text_in_node("Jurisdiction Feeds for Opinions", "body")

        for court in courts:
            link = self.browser.find_element(By.LINK_TEXT, court.full_name)
            print(f"Testing link to {court.full_name}...", end=" ")
            self.assertEqual(
                link.get_attribute("href"),
                f"{self.live_server_url}/feed/court/{court.pk}/",
            )
            link.click()
            print("clicked...", end=" ")
            self.assertIn(
                'feed xml:lang="en-us" xmlns="http://www.w3.org/2005/Atom"',
                self.browser.page_source,
            )
            self.browser.back()
            print("✓")

    def test_all_jurisdiction_opinion_rss_feeds_usable_in_rss_reader(
        self,
    ) -> None:
        """
        Can the RSS feed for ALL jurisdictions render properly in an RSS reader?
        """
        f = feedparser.parse(
            f"{self.live_server_url}{reverse('all_jurisdictions_feed')}"
        )
        self.assertEqual(
            "CourtListener.com: All Opinions (High Volume)", f.feed.title
        )
        # Per https://pythonhosted.org/feedparser/bozo.html
        self.assertEqual(f.bozo, 0, "Feed should be wellformed")

    def test_court_opinion_rss_feeds_usable_in_rss_reader(self) -> None:
        """
        Can the RSS feeds be properly used in an RSS Reader?
        """
        url = "%s%s" % (
            self.live_server_url,
            reverse("jurisdiction_feed", kwargs={"court": "test"}),
        )
        f = feedparser.parse(url)
        self.assertEqual(
            "CourtListener.com: All opinions for the Testing Supreme Court",
            f.feed.title,
        )
        # Per https://pythonhosted.org/feedparser/bozo.html
        self.assertEqual(f.bozo, 0, "Feed should be wellformed")

    def test_opinion_rss_feeds_contain_valid_attachment_links(self) -> None:
        """
        For Opinions with stored PDFs, does the feed provide valid links
        to the CourtListener copy of the original PDF?
        """
        f = feedparser.parse(
            f"{self.live_server_url}{reverse('all_jurisdictions_feed')}"
        )
        for entry in f.entries:
            if entry.enclosures is not None:
                self.assertEqual(len(entry.enclosures), 1)
                self.assertTrue(len(entry.enclosures[0].type) > 0)

    def test_oral_argument_feeds_contain_valid_mp3_links(self) -> None:
        """
        For Oral Arguments, does the feed provide valid links to MP3 content?
        """
        f = feedparser.parse(
            f"{self.live_server_url}{reverse('all_jurisdictions_podcast')}"
        )
        for entry in f.entries:
            if entry.enclosures is not None:
                self.assertEqual(len(entry.enclosures), 1)

    @timeout_decorator.timeout(SELENIUM_TIMEOUT)
    def test_search_based_opinion_feed(self) -> None:
        """
        Can a user perform a search via CL and use the RSS feed feature?
        """
        # Dora goes to CL and searches for Bonvini
        self.browser.get(self.live_server_url)
        self.browser.find_element(By.ID, "id_q").send_keys("bonvini")
        self.browser.find_element(By.ID, "id_q").submit()

        # She's brought to the SERP.
        self.assertIn("Search Results", self.browser.title)
        articles = self.browser.find_elements(By.TAG_NAME, "article")
        link_titles = [a.find_element(By.TAG_NAME, "a").text for a in articles]

        # Seeing the results, she wants to keep tabs on any new Opinions that
        # come into CL related to her Search. She notices a little RSS icon
        # and decides to click it
        result_count = self.browser.find_element(By.ID, "result-count")
        rss_link = result_count.find_element(By.TAG_NAME, "a")

        with self.wait_for_page_load(timeout=10):
            rss_link.click()

        # She captures the URL and pops it into her RSS Reader
        self.assertIn(
            'feed xml:lang="en-us" xmlns="http://www.w3.org/2005/Atom"',
            self.browser.page_source,
        )

        # The RSS Reader validates the feed and Dora is thrilled! The same
        # first page of results are there!
        xml = self.browser.find_element(By.TAG_NAME, "pre").text
        f = feedparser.parse(xml)
        self.assertEqual(len(link_titles), len(f.entries))

        for entry in f.entries:
            found_similar_title = False
            for title in link_titles:
                if entry.title in title:
                    found_similar_title = True
            self.assertTrue(
                found_similar_title,
                f"Should have seen a search result similar to {entry.title}",
            )
