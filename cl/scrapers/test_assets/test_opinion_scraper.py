import re
from datetime import datetime
from os.path import join

from django.conf import settings
from juriscraper.OpinionSite import OpinionSite


class Site(OpinionSite):
    def __init__(self):
        super().__init__()
        self.court_id = self.__module__
        self.url = "http://test"
        self.mock_url = join(
            settings.INSTALL_ROOT,
            "cl/scrapers/test_assets/test_opinion_site.xml",
        )
        self.method = "LOCAL"

    def _get_download_urls(self):
        path = "//url/text()"
        return [f"test/search/{url}" for url in self.html.xpath(path)]

    def _get_case_names(self):
        path = "//name/text()"
        return list(self.html.xpath(path))

    def _get_case_dates(self) -> list[datetime]:
        path = "//date/text()"
        return [
            datetime.strptime(date_string, "%Y/%m/%d")
            for date_string in self.html.xpath(path)
        ]

    def _get_precedential_statuses(self):
        path = "//status/text()"
        return list(self.html.xpath(path))

    def _get_docket_numbers(self):
        path = "//docket_number/text()"
        return list(self.html.xpath(path))

    def _get_neutral_citations(self):
        path = "//neutral_cite/text()"
        return list(self.html.xpath(path))

    def _get_west_citations(self):
        path = "//federal_cite/text()"
        return list(self.html.xpath(path))

    def _get_nature_of_suit(self):
        path = "//nature_of_suit/text()"
        return list(self.html.xpath(path))

    def _get_judges(self):
        path = "//judge/text()"
        return list(self.html.xpath(path))

    def _get_lower_court_numbers(self):
        path = "//lower_court_number"
        return [i.text for i in self.html.xpath(path)]

    def _get_lower_court_judges(self):
        path = "//lower_court_judge"
        return [i.text for i in self.html.xpath(path)]

    def extract_from_text(self, scraped_text):
        metadata = {}
        docket_regex = r"Docket Number: (?P<docket>\d+-\d+)"
        disposition_regex = r"Disposition: (?P<disposition>\w+)"
        citation_regex = r"20\d{2} VT \d+"
        originating_court_information_regex = (
            r"Originating Court Docket Number: (?P<oci_docket_number>\d+-\d+)"
        )

        if docket_match := re.search(docket_regex, scraped_text):
            metadata["Docket"] = {
                "docket_number": docket_match.group("docket")
            }

        if disposition_match := re.search(disposition_regex, scraped_text):
            metadata["OpinionCluster"] = {
                "disposition": disposition_match.group("disposition")
            }

        if citation_match := re.search(citation_regex, scraped_text):
            metadata["Citation"] = citation_match.group(0)

        if oci_match := re.search(
            originating_court_information_regex, scraped_text
        ):
            metadata["OriginatingCourtInformation"] = {
                "docket_number": oci_match.group("oci_docket_number")
            }

        return metadata

    @staticmethod
    def cleanup_content(content):
        """Implemented just to override OpinionSite.cleanup_content for tests"""
        return content
