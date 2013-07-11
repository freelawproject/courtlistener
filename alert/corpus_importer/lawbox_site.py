# import re
from datetime import date
from datetime import datetime
from juriscraper.lib import parse_dates
from lxml import html

from juriscraper.GenericSite import GenericSite
# from juriscraper.lib.string_utils import titlecase


class Site(GenericSite):
    def __init__(self, url):
        super(Site, self).__init__()
        self.method = 'LOCAL'
        self.url = url

    def _get_case_names(self):


    def _get_case_dates(self):
        path = '//center'
        dates = []
        argued = None
        elements = self.html.xpath(path)
        for e in elements:
            s = html.tostring(e, method='text', encoding='unicode')
            if 'argued' in s.lower():
                argued = parse_dates.parse(s)
                continue
            elif 'decided' in s.lower():
                return parse_dates.parse(s)
            else:
                dates.append(parse_dates.parse(s))

        # If we get this far, we have several dates to choose from
        if len(dates) == 0 and argued:
            # Problem. We've found no dates.
            return argued
        elif len(dates) == 1:
            # We found just one date, return it.
            return dates[0]
        else:
            # More than 1 date, get the most logical one.
            print "Getting most logical date based on query"


        return dates







    """
      Optional method used for downloading multiple pages of a court site.
    """
    def _download_backwards(self, date_str):
        """ This is a simple method that can be used to generate Site objects
            that can be used to paginate through a court's entire website.

            This method is usually called by a backscraper caller (see the
            one in CourtListener/alert/scrapers for details), and typically
            modifies aspects of the Site object's attributes such as Site.url.

            A simple example has been provided below. The idea is that the
            caller runs this method with a different variable on each iteration.
            That variable is often a date that is getting iterated or is simply
            a index (i), that we iterate upon.

            This can also be used to hold notes useful to future backscraper
            development.
        """
        self.url = 'http://example.com/new/url/%s' % date_str
        self.html = self._download()
