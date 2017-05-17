# coding=utf-8
import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.urlresolvers import reverse
from django.test import TestCase
from rest_framework.status import HTTP_400_BAD_REQUEST, HTTP_201_CREATED, \
    HTTP_401_UNAUTHORIZED
from rest_framework.test import APIClient

from cl.recap.models import ProcessingQueue


class RecapUploadsTest(TestCase):
    fixtures = ['authtest_data.json']

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
        }

    def test_uploading_a_pdf(self):
        """Can we upload a document and have it be saved correctly?"""
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTP_201_CREATED)

        j = json.loads(r.content)
        self.assertEqual(j['court'], 'scotus')
        self.assertEqual(j['document_number'], 'asdf')
        self.assertEqual(j['pacer_case_id'], 'asdf')

    def test_uploading_non_ascii(self):
        """Can we handle it if a client sends non-ascii strings?"""
        self.data['document_number'] = '☠☠☠'
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTP_201_CREATED)

    def test_disallowed_court(self):
        """Do posts fail if a bad court is given?"""
        self.data['court'] = 'ala'
        r = self.client.post(self.path, self.data)
        self.assertEqual(r.status_code, HTTP_400_BAD_REQUEST)

    def test_user_associated_properly(self):
        """Does the user get associated after the upload?"""
        r = self.client.post(self.path, self.data)
        j = json.loads(r.content)
        processing_request = ProcessingQueue.objects.get(pk=j['id'])
        self.assertEqual(self.user.pk, processing_request.uploader_id)

    def test_ensure_no_users_in_response(self):
        """Are users excluded from the response?"""
        r = self.client.post(self.path, self.data)
        j = json.loads(r.content)
        for bad_key in ['uploader', 'user']:
            with self.assertRaises(KeyError):
                # noinspection PyStatementEffect
                j[bad_key]


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

