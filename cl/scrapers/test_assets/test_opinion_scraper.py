from datetime import datetime
from django.conf import settings
from juriscraper.OpinionSite import OpinionSite
from os.path import join


class Site(OpinionSite):
    def __init__(self):
        super(Site, self).__init__()
        self.court_id = self.__module__
        self.url = join(settings.INSTALL_ROOT, 'alert/scrapers/test_assets/test_opinion_site.xml')
        self.method = 'LOCAL'

    def _get_download_urls(self):
        path = '//url/text()'
        return ['scrapers/test_assets/%s' % url for
                url in self.html.xpath(path)]

    def _get_case_names(self):
        path = '//name/text()'
        return list(self.html.xpath(path))

    def _get_case_dates(self):
        path = '//date/text()'
        return [datetime.strptime(date_string, '%Y/%m/%d')
                for date_string in self.html.xpath(path)]

    def _get_precedential_statuses(self):
        path = '//status/text()'
        return list(self.html.xpath(path))

    def _get_docket_numbers(self):
        path = '//docket_number/text()'
        return list(self.html.xpath(path))

    def _get_neutral_citations(self):
        path = '//neutral_cite/text()'
        return list(self.html.xpath(path))

    def _get_west_citations(self):
        path = '//federal_cite/text()'
        return list(self.html.xpath(path))

    def _get_nature_of_suit(self):
        path = '//nature_of_suit/text()'
        return list(self.html.xpath(path))

    def _get_judges(self):
        path = '//judge/text()'
        return list(self.html.xpath(path))
