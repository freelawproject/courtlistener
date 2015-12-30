from django.conf import settings
from django.http import HttpRequest
from django.test import TestCase
from cl.simple_pages.views import serve_static_file
from cl.search.models import Opinion, OpinionCluster, Docket, Court
from cl.audio.models import Audio
import datetime
import os


class ContactTest(TestCase):
    fixtures = ['authtest_data.json']

    def test_multiple_requests_request(self):
        """ Is state persisted in the contact form?

        The contact form is abstracted in a way that it can have peculiar behavior when called multiple times. This test
        makes sure that that behavior does not regress.
        """
        self.client.login(username='pandora', password='password')
        self.client.get('/contact/')
        self.client.logout()

        # Now, as an anonymous user, we get the page again. If the bug is resolved, we should not see anything about
        # the previously logged-in user, pandora.
        r = self.client.get('/contact/')
        self.assertNotIn('pandora', r.content)

    def test_robots_page(self):
        r = self.client.get('/robots.txt')
        self.assertTrue(r.status_code, 200)


@override_settings(
    MEDIA_ROOT = os.path.join(settings.INSTALL_ROOT, 'cl/assets/media/test/')
)
class StaticFilesTest(TestCase):

    fixtures = ['court_data.json']

    good_mp3_path = 'mp3/2014/06/09/ander_v._leo.mp3'
    good_txt_path = 'txt/2015/12/28/opinion_text.txt'
    good_pdf_path = 'pdf/2013/06/12/' + \
     'in_re_motion_for_consent_to_disclosure_of_court_records.pdf'

    def setUp(self):
        self.court = Court.objects.get(pk='test')
        self.docket = Docket(case_name=u'Docket', court=self.court)
        self.docket.save()

        self.audio = Audio(
            local_path_original_file=self.good_mp3_path,
            local_path_mp3=self.good_mp3_path,
            docket=self.docket,
            blocked=False,
            case_name_full='Ander v. Leo',
            date_created=datetime.date(2014, 6, 9)
        )
        self.audio.save(index=False)

        self.opinioncluster = OpinionCluster(
            case_name=u'Hotline Bling',
            docket=self.docket,
            date_filed=datetime.date(2015, 12, 14),
        )
        self.opinioncluster.save(index=False)

        self.txtopinion = Opinion(
            cluster=self.opinioncluster,
            type='Lead Opinion',
            local_path=self.good_txt_path
        )
        self.txtopinion.save()

        self.pdfopinion = Opinion(
            cluster=self.opinioncluster,
            type='Lead Opinion',
            local_path=self.good_pdf_path
        )
        self.pdfopinion.save()

    def test_serve_static_file_serves_mp3(self):
        request = HttpRequest()
        file_path = self.audio.local_path_mp3
        response = serve_static_file(request, file_path=self.good_mp3_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'audio/mpeg')
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_serve_static_file_serves_txt(self):
        request = HttpRequest()
        response = serve_static_file(request, file_path=self.good_txt_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn(
            'FOR THE DISTRICT OF COLUMBIA CIRCUIT',
            response.content
        )

    def test_serve_static_file_serves_pdf(self):
        request = HttpRequest()
        response = serve_static_file(request, file_path=self.good_pdf_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
