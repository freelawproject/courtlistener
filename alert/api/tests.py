from datetime import timedelta
import shutil
from django.test import TestCase
from django.test.utils import override_settings
from django.utils.timezone import now

from alert.api.management.commands.cl_make_bulk_data import Command
from alert.search.models import Docket, Citation, Court, Document
from alert.scrapers.management.commands.cl_scrape_oral_arguments import \
    Command as OralArgumentCommand
from alert.scrapers.test_assets import test_oral_arg_scraper


class BulkDataTest(TestCase):
    fixtures = ['test_court.json']
    tmp_data_dir = '/tmp/bulk-dir/'

    def setUp(self):
        c1 = Citation(case_name=u"foo")
        c1.save(index=False)
        docket = Docket(
            case_name=u'foo',
            court=Court.objects.get(pk='test'),
        )
        docket.save()
        # Must be more than a year old for all tests to be runnable.
        last_month = now().date() - timedelta(days=400)
        self.doc = Document(
            citation=c1,
            docket=docket,
            date_filed=last_month
        )
        self.doc.save(index=False)

        # Scrape the audio "site" and add its contents
        site = test_oral_arg_scraper.Site().parse()
        OralArgumentCommand().scrape_court(site, full_crawl=True)

    def tearDown(self):
        Document.objects.all().delete()
        Docket.objects.all().delete()
        Citation.objects.all().delete()
        shutil.rmtree(self.tmp_data_dir)

    @override_settings(BULK_DATA_DIR=tmp_data_dir)
    def test_make_all_bulk_files(self):
        """Can we successfully generate all bulk files?"""
        Command().execute()
