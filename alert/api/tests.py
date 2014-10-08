from datetime import timedelta
from django.test import TestCase
from django.utils.timezone import now
from alert.search.models import Docket, Citation, Court, Document
from api.management.commands.cl_make_bulk_data import Command


class BulkDataTest(TestCase):
    fixtures = ['test_court.json']

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

    def tearDown(self):
        self.doc.delete()

    def test_make_all_bulk_files(self):
        """Can we successfully generate all bulk files?"""
        Command.do_everything()
