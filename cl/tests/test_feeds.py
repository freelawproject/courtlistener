# coding=utf-8
"""
Functional testing of courtlistener feeds
"""
from cl.search.models import Court
from cl.tests.base import BaseSeleniumTest



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
            self.assert_text_in_body('<?xml version="1.0" encoding="utf-8"?>')
            self.browser.back()

    def test_feeds_contain_links_to_pdf_opinions(self):
        """
        Do the Opinion feeds for those with PDFs provide valid links to
        the original and the backup PDF copies?
        """
        self.fail('Finish Test')
