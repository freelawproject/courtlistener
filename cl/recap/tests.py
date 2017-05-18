# coding=utf-8
import json

import mock
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.urlresolvers import reverse
from django.test import TestCase
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_201_CREATED, \
    HTTP_401_UNAUTHORIZED
from rest_framework.test import APIClient

from cl.recap.models import ProcessingQueue
from cl.recap.tasks import process_recap_pdf
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
            'status': 1,
            'upload_type': 3,
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

    def test_uploading_non_ascii(self, mock):
        """Can we handle it if a client sends non-ascii strings?"""
        self.data['document_number'] = '☠☠☠'
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
            status=ProcessingQueue.AWAITING_PROCESSING,
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
