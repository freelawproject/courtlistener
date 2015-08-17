from datetime import datetime
from django.conf import settings
from juriscraper.OralArgumentSite import OralArgumentSite
from os.path import join


class Site(OralArgumentSite):
    def __init__(self):
        super(Site, self).__init__()
        self.court_id = self.__module__
        self.url = join(settings.INSTALL_ROOT, 'cl/scrapers/test_assets/test_oral_arg_site.xml')
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

    def _get_docket_numbers(self):
        path = '//docket_number/text()'
        return list(self.html.xpath(path))
