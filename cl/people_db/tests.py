import os
from django.conf import settings
from django.test import TestCase
# or whatever you choose to call the file
from cl.people_db.management.commands import (
    cl_download_and_convert
)

# These are celery tasks or tasks broken apart that we can test
# For example if we wnated to test the OCRing capability
# OR the ability to get the first and last name etc.
# In fact you should review the tasks file in the people db to see what tasks have
# Already been written
# from cl.scrapers.tasks import (
#     extract_from_txt,
#     extract_doc_content,
#     process_audio_file,
# )
from cl.people_db.models import Person, FinancialDisclosure
class IngestionTest(TestCase):
    #this fixture if a duplicate of the judge judy json file, but renamed in same
    # directory
    fixtures = ["test_judge_people.json"]
    # This test isnt going to test anything other than can we import from our fixture
    # Its an example for no purpose other than to show you an example
    # def test_import_judges(self):
    #     """Can we successfully ingest judges at a high level?"""
    #     judges = Person.objects.all()
    #     count = judges.count()
    #     self.assertTrue(
    #         judges.count() == 2,
    #         "Should have 2 test opinions, not %s" % count,
    #     )
    def test_download_new_disclosures(self):
        print("test find")
        cl_download_and_convert.Command().download_new_disclosures()

        # At this point we can pass in fake data - or fake URLS to download our
        # TESTING PDFS TO PROCESS

# TODO: add example files to fixtures folder
