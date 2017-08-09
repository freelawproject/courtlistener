# coding=utf-8
import json
import os

import mock
from datetime import date

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.urlresolvers import reverse
from django.test import TestCase
from rest_framework.status import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
)
from rest_framework.test import APIClient

from cl.people_db.models import Party, AttorneyOrganizationAssociation, \
    Attorney, Role
from cl.recap.models import ProcessingQueue
from cl.recap.tasks import process_recap_pdf, add_attorney, process_recap_docket
from cl.search.models import Docket, RECAPDocument, DocketEntry


@mock.patch('cl.recap.views.process_recap_upload')
class RecapUploadsTest(TestCase):
    """Test the rest endpoint, but exclude the processing tasks."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.get(username='recap')
        token = 'Token ' + self.user.auth_token.key
        self.client.credentials(HTTP_AUTHORIZATION=token)
        self.path = reverse('processingqueue-list', kwargs={'version': 'v3'})
        f = SimpleUploadedFile("file.txt", b"file content more content")
        self.data = {
            'court': 'scotus',
            'pacer_case_id': 'asdf',
            'document_number': 'asdf',
            'filepath_local': f,
            'upload_type': ProcessingQueue.PDF,
        }

    def test_uploading_a_pdf(self, mock):
        """Can we upload a document and have it be saved correctly?"""
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTP_201_CREATED)

        j = json.loads(r.content)
        self.assertEqual(j['court'], 'scotus')
        self.assertEqual(j['document_number'], 'asdf')
        self.assertEqual(j['pacer_case_id'], 'asdf')
        mock.assert_called()

    def test_uploading_a_docket(self, mock):
        """Can we upload a docket and have it be saved correctly?
        
        Note that this works fine even though we're not actually uploading a 
        docket due to the mock.
        """
        self.data.update({
            'upload_type': ProcessingQueue.DOCKET,
            'document_number': '',
        })
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTP_201_CREATED)

    def test_numbers_in_docket_uploads_fail(self, mock):
        """Are invalid uploads denied?
        
        For example, if you're uploading a Docket, you shouldn't be providing a
        document number.
        """
        self.data['upload_type'] = ProcessingQueue.DOCKET
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTP_400_BAD_REQUEST)

    def test_no_numbers_in_docket_uploads_work(self, mock):
        self.data['upload_type'] = ProcessingQueue.DOCKET
        self.data['document_number'] = ''
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTP_201_CREATED)

    def test_uploading_non_ascii(self, mock):
        """Can we handle it if a client sends non-ascii strings?"""
        self.data['document_number'] = u'☠☠☠'
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTP_201_CREATED)
        mock.assert_called()

    def test_disallowed_court(self, mock):
        """Do posts fail if a bad court is given?"""
        self.data['court'] = 'ala'
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTP_400_BAD_REQUEST)

    def test_fails_no_document(self, mock):
        """Do posts fail if the lack an attachment?"""
        del self.data['filepath_local']
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTP_400_BAD_REQUEST)

    def test_user_associated_properly(self, mock):
        """Does the user get associated after the upload?"""
        r = self.client.post(self.path, self.data)
        j = json.loads(r.content)
        processing_request = ProcessingQueue.objects.get(pk=j['id'])
        self.assertEqual(self.user.pk, processing_request.uploader_id)
        mock.assert_called()

    def test_ensure_no_users_in_response(self, mock):
        """Are users excluded from the response?"""
        r = self.client.post(self.path, self.data)
        j = json.loads(r.content)
        for bad_key in ['uploader', 'user']:
            with self.assertRaises(KeyError):
                # noinspection PyStatementEffect
                j[bad_key]
        mock.assert_called()


class RecapPdfTaskTest(TestCase):

    def setUp(self):
        user = User.objects.get(username='recap')
        self.filename = 'file.pdf'
        self.file_content = b"file content more content"
        f = SimpleUploadedFile(self.filename, self.file_content)
        sha1 = 'dcfdea519bef494e9672b94a4a03a49d591e3762'  # <-- SHA1 for above
        self.pq = ProcessingQueue.objects.create(
            court_id='scotus',
            uploader=user,
            pacer_case_id='asdf',
            pacer_doc_id='asdf',
            document_number='1',
            filepath_local=f,
            upload_type=ProcessingQueue.PDF,
        )
        self.docket = Docket.objects.create(source=0, court_id='scotus',
                                            pacer_case_id='asdf')
        self.de = DocketEntry.objects.create(docket=self.docket, entry_number=1)
        self.rd = RECAPDocument.objects.create(
            docket_entry=self.de,
            document_type=1,
            document_number=1,
            pacer_doc_id='asdf',
            sha1=sha1,
        )

    def tearDown(self):
        self.pq.filepath_local.delete()
        self.pq.delete()
        try:
            self.docket.delete()  # This cascades to self.de and self.rd
        except (Docket.DoesNotExist, AssertionError):
            pass

    def test_pq_has_default_status(self):
        self.assertTrue(self.pq.status == ProcessingQueue.AWAITING_PROCESSING)

    @mock.patch('cl.recap.tasks.extract_recap_pdf')
    def test_recap_document_already_exists(self, mock):
        """We already have everything"""
        # Update self.rd so it looks like it is already all good.
        self.rd.is_available = True
        cf = ContentFile(self.file_content)
        self.rd.filepath_local.save(self.filename, cf)

        rd = process_recap_pdf(self.pq.pk)

        # Did we avoid creating new objects?
        self.assertEqual(rd, self.rd)
        self.assertEqual(rd.docket_entry, self.de)
        self.assertEqual(rd.docket_entry.docket, self.docket)

        # Did we update pq appropriately?
        self.pq.refresh_from_db()
        self.assertEqual(self.pq.status, self.pq.PROCESSING_SUCCESSFUL)
        self.assertFalse(self.pq.error_message)
        self.assertFalse(self.pq.filepath_local)

        # Did we correctly avoid running document extraction?
        mock.assert_not_called()

    def test_only_the_docket_already_exists(self):
        """Never seen this docket entry before? 
        
        Alas, we fail. In theory, this shouldn't happen.
        """
        self.de.delete()
        with self.assertRaises(DocketEntry.DoesNotExist):
            process_recap_pdf(self.pq.pk)
        self.pq.refresh_from_db()
        # This doesn't do the celery retries, unfortunately. If we get that
        # working, the correct status is self.pq.PROCESSING_FAILED.
        self.assertEqual(self.pq.status, self.pq.QUEUED_FOR_RETRY)
        self.assertIn('Unable to find docket entry', self.pq.error_message)

    @mock.patch('cl.recap.tasks.extract_recap_pdf')
    def test_docket_and_docket_entry_already_exist(self, mock):
        """What happens if we have everything but the PDF?
        
        This is the good case. We simply create a new item.
        """
        self.rd.delete()
        rd = process_recap_pdf(self.pq.pk)
        self.assertTrue(rd.is_available)
        self.assertTrue(rd.sha1)
        self.assertTrue(rd.filepath_local)
        mock.assert_called_once()
        self.assertIn('gov.uscourts.scotus.asdf.1.0', rd.filepath_local.name)

        self.pq.refresh_from_db()
        self.assertEqual(self.pq.status, self.pq.PROCESSING_SUCCESSFUL)
        self.assertFalse(self.pq.error_message)
        self.assertFalse(self.pq.filepath_local)

    def test_nothing_already_exists(self):
        """If a PDF is uploaded but there's no recap document and no docket do 
        we fail?
        
        In practice, this shouldn't happen.
        """
        self.docket.delete()
        with self.assertRaises(Docket.DoesNotExist):
            process_recap_pdf(self.pq.pk)
        self.pq.refresh_from_db()
        # This doesn't do the celery retries, unfortunately. If we get that
        # working, the correct status is self.pq.PROCESSING_FAILED.
        self.assertEqual(self.pq.status, self.pq.QUEUED_FOR_RETRY)
        self.assertIn('Unable to find docket', self.pq.error_message)


class RecapAddAttorneyTest(TestCase):

    def setUp(self):
        self.atty_org_name = "Lane Powell LLC"
        self.atty_phone = "907-276-2631"
        self.atty_email = "jamiesonb@lanepowell.com"
        self.atty_name = "Brewster H. Jamieson"
        self.atty = {
            "contact": "{org_name}\n"
                       "301 W. Nothern Lights Blvd., Suite 301\n"
                       "Anchorage, AK 99503-2648\n"
                       "{phone}\n"
                       "Fax: 907-276-2631\n"
                       "Email: {email}\n".format(org_name=self.atty_org_name,
                                                 phone=self.atty_phone,
                                                 email=self.atty_email),
            "name": self.atty_name,
            "roles": [
                "LEAD ATTORNEY",
                "ATTORNEY TO BE NOTICED"
            ]
        }
        self.d = Docket.objects.create(source=0, court_id='scotus',
                                       pacer_case_id='asdf',
                                       date_filed=date(2017, 1, 1))
        self.p = Party.objects.create(name="John Wesley Powell")

    def test_new_atty_to_db(self):
        """Can we add a new atty to the DB when none exist?"""
        a = add_attorney(self.atty, self.p, self.d)
        self.assertEqual(a.contact_raw, self.atty['contact'])
        self.assertEqual(a.name, self.atty['name'])
        self.assertTrue(
            AttorneyOrganizationAssociation.objects.filter(
                attorney=a,
                attorney_organization__name=self.atty_org_name,
                docket=self.d,
            ).exists(),
            msg="Unable to find attorney organization association."
        )
        self.assertEqual(a.email, self.atty_email)
        self.assertEqual(a.roles.all().count(), 2)

    def test_docket_is_newer(self):
        """If the atty already exists, but with older data than the docket, do 
        we update the old data?
        """
        a_orig = Attorney.objects.create(name=self.atty_name,
                                         email=self.atty_email,
                                         date_sourced=date(2016, 12, 31))
        a_from_docket = add_attorney(self.atty, self.p, self.d)
        self.assertEqual(a_orig.pk, a_from_docket.pk)
        # Phone updated? (Adding newly sourced docket should update old info)
        self.assertNotEqual(a_orig.phone, a_from_docket.phone)
        self.assertEqual(a_from_docket.roles.all().count(), 2)

    def test_docket_is_older(self):
        """If the atty already exists, but with newer data than the docket, do 
        we avoid updating the better data?
        """
        a_orig = Attorney.objects.create(name=self.atty_name,
                                         email=self.atty_email,
                                         date_sourced=date(2017, 1, 2))
        a_from_docket = add_attorney(self.atty, self.p, self.d)
        self.assertEqual(a_orig.pk, a_from_docket.pk)
        # No updates?
        self.assertEqual(a_orig.phone, a_from_docket.phone)
        self.assertEqual(a_from_docket.roles.all().count(), 2)

    def test_no_contact_info(self):
        """Do things work properly when we lack contact information?"""
        self.atty['contact'] = ""
        a = add_attorney(self.atty, self.p, self.d)
        # No org info added because none provided:
        self.assertEqual(a.organizations.all().count(), 0)
        # But roles still get done.
        self.assertEqual(a.roles.all().count(), 2)

    def test_no_contact_info_another_already_exists(self):
        """If we lack contact info, and such a atty already exists (without 
        contact info), do we properly consider them the same person?
        """
        new_a = Attorney.objects.create(name=self.atty_name,
                                        date_sourced=date(2016, 12, 31))
        self.atty['contact'] = ''
        a = add_attorney(self.atty, self.p, self.d)
        self.assertEqual(a.pk, new_a.pk)

    def test_existing_roles_get_overwritten(self):
        """Do existing roles get overwritten with latest data?"""
        new_a = Attorney.objects.create(name=self.atty_name,
                                        email=self.atty_email,
                                        date_sourced=date(2017, 1, 2))
        r = Role.objects.create(attorney=new_a, party=self.p, docket=self.d,
                                role=Role.DISBARRED)
        a = add_attorney(self.atty, self.p, self.d)
        self.assertEqual(new_a.pk, a.pk)
        roles = a.roles.all()
        self.assertEqual(roles.count(), 2)
        self.assertNotIn(r, roles)


@mock.patch('cl.recap.tasks.add_attorney')
class RecapDocketTaskTest(TestCase):
    def setUp(self):
        user = User.objects.get(username='recap')
        self.filename = 'cand.html'
        path = os.path.join(settings.INSTALL_ROOT, 'cl', 'recap', 'test_assets',
                            self.filename)
        with open(path, 'r') as f:
            f = SimpleUploadedFile(self.filename, f.read())
        self.pq = ProcessingQueue.objects.create(
            court_id='scotus',
            uploader=user,
            pacer_case_id='asdf',
            filepath_local=f,
            upload_type=ProcessingQueue.DOCKET,
        )

    def tearDown(self):
        self.pq.filepath_local.delete()
        self.pq.delete()
        Docket.objects.all().delete()

    def test_parsing_docket_does_not_exist(self, add_atty_mock):
        """Can we parse an HTML docket we have never seen before?"""
        d = process_recap_docket(self.pq.pk)
        # XXX
        pass

    def test_parsing_docket_already_exists(self, add_atty_mock):
        """Can we parse an HTML docket for a docket we have in the DB?"""
        existing_d = Docket.objects.create(
            source=Docket.DEFAULT,
            pacer_case_id='asdf',
            court_id='scotus',
        )
        d = process_recap_docket(self.pq.pk)
        self.assertEqual(d.source, Docket.RECAP_AND_SCRAPER)
        self.assertTrue(d.case_name)
        self.assertEqual(existing_d.pacer_case_id, d.pacer_case_id)

    def test_docket_and_de_already_exist(self, add_atty_mock):
        """Can we parse if the docket and the docket entry already exist?"""
        existing_d = Docket.objects.create(
            source=Docket.DEFAULT,
            pacer_case_id='asdf',
            court_id='scotus',
        )
        existing_de = DocketEntry.objects.create(
            docket=existing_d,
            entry_number='1',
            date_filed=date(2008, 1, 1),
        )
        d = process_recap_docket(self.pq.pk)
        de = d.docket_entries.get(pk=existing_de.pk)
        self.assertNotEqual(
            existing_de.description,
            de.description,
            msg="Description field did not get updated during import.",
        )
        self.assertTrue(
            de.recap_documents.filter(is_available=False).exists(),
            msg="Recap document didn't get created properly.",
        )
        self.assertTrue(
            d.docket_entries.filter(entry_number='2').exists(),
            msg="New docket entry didn't get created."
        )


class RecapUploadAuthenticationTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.path = reverse('processingqueue-list', kwargs={'version': 'v3'})

    def test_authentication(self):
        """Does POSTing and GETting fail when we send the wrong credentials?"""
        self.client.credentials(HTTP_AUTHORIZATION='Token asdf')  # Junk token.
        r = self.client.post(self.path)
        self.assertEqual(r.status_code, HTTP_401_UNAUTHORIZED)

        r = self.client.get(self.path)
        self.assertEqual(r.status_code, HTTP_401_UNAUTHORIZED)

    def test_no_credentials(self):
        """Does POSTing and GETting fail if we lack credentials?"""
        self.client.credentials()
        r = self.client.post(self.path)
        self.assertEqual(r.status_code, HTTP_401_UNAUTHORIZED)

        r = self.client.get(self.path)
        self.assertEqual(r.status_code, HTTP_401_UNAUTHORIZED)
