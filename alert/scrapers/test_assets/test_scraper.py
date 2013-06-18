from datetime import date
from datetime import datetime

from juriscraper.GenericSite import GenericSite


class Site(GenericSite):
    def __init__(self):
        super(Site, self).__init__()
        self.court_id = self.__module__
        self.url = 'http://localhost:8080/scrapers/test_assets/test_court.xml'

    def _get_download_urls(self):
        path = '//opinion/url/text()'
        return ['http://localhost:8080/scrapers/test_assets/%s' % url for
                url in self.html.xpath(path)]

    def _get_case_names(self):
        path = '//opinion/name/text()'
        return list(self.html.xpath(path))

    def _get_case_dates(self):
        path = '//opinion/date/text()'
        return [datetime.strptime(date_string, '%Y/%m/%d').date()
                for date_string in self.html.xpath(path)]

    def _get_precedential_statuses(self):
        path = '//opinion/status/text()'
        return list(self.html.xpath(path))

    def _get_docket_numbers(self):
        path = '//opinion/docket_number/text()'
        return list(self.html.xpath(path))

    def _get_neutral_citations(self):
        path = '//opinion/neutral_cite/text()'
        return list(self.html.xpath(path))

    def _get_west_citations(self):
        path = '//opinion/west_cite/text()'
        return list(self.html.xpath(path))
