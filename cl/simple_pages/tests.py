# coding=utf-8
import datetime
import os

from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import HttpRequest
from django.test import TestCase, RequestFactory
from django.test.utils import override_settings
from lxml.html import fromstring

from cl.audio.models import Audio
from cl.search.models import Opinion, OpinionCluster, Docket, Court
from cl.simple_pages.views import serve_static_file, show_maintenance_warning


class ContactTest(TestCase):
    fixtures = ['authtest_data.json']

    def test_multiple_requests_request(self):
        """ Is state persisted in the contact form?

        The contact form is abstracted in a way that it can have peculiar
        behavior when called multiple times. This test makes sure that that
        behavior does not regress.
        """
        self.client.login(username='pandora', password='password')
        self.client.get('/contact/')
        self.client.logout()

        # Now, as an anonymous user, we get the page again. If the bug is
        # resolved, we should not see anything about the previously logged-in
        # user, pandora.
        r = self.client.get('/contact/')
        self.assertNotIn('pandora', r.content)


class SimplePagesTest(TestCase):

    def check_for_title(self, content):
        """Make sure a page has a valid HTML title"""
        print "Checking for HTML title tag....",
        html_tree = fromstring(content)
        title = html_tree.xpath('//title/text()')
        self.assertGreater(
            len(title),
            0,
            msg="This page didn't have any text in it's <title> tag."
        )
        self.assertGreater(
            len(title[0].strip()),
            0,
            msg="The text in this title tag is empty.",
        )

        print "✓"

    def test_simple_pages(self):
        """Do all the simple pages load properly?"""
        reverse_params = [
            {'viewname': 'about'},
            {'viewname': 'faq'},
            {'viewname': 'coverage'},
            {'viewname': 'feeds_info'},
            {'viewname': 'contribute'},
            {'viewname': 'contact'},
            {'viewname': 'contact_thanks'},
            {'viewname': 'markdown_help'},
            {'viewname': 'advanced_search'},
            {'viewname': 'old_terms', 'args': ['1']},
            {'viewname': 'old_terms', 'args': ['2']},
            {'viewname': 'terms'},
            {'viewname': 'tools'},
            {'viewname': 'bad_browser'},
            {'viewname': 'robots'},
        ]
        for reverse_param in reverse_params:
            path = reverse(**reverse_param)
            print "Testing basic load of: {path}...".format(path=path),
            r = self.client.get(path)
            self.assertEqual(
                r.status_code,
                200,
                msg="Got wrong status code for page at: {path}\n  args: "
                    "{args}\n  kwargs: {kwargs}\n  Status Code: {code}".format(
                        path=path,
                        args=reverse_param.get('args', []),
                        kwargs=reverse_param.get('kwargs', {}),
                        code=r.status_code,
                    )
            )
            print '✓'
            is_html = ('text/html' in r['content-type'])
            if r['content-type'] and is_html:
                self.check_for_title(r.content)

    def test_maintenance_page(self):
        """Does the maintenance page load?

        This gets its own test because in normal configuration it's disabled in
        urls.py.
        """
        request = RequestFactory().get(path='/asdf-anything/')
        response = show_maintenance_warning(request)
        self.assertEqual(response.status_code, 503)
        self.assertIn("undergoing maintenance", ' '.join(response.content.split()))


@override_settings(
    MEDIA_ROOT=os.path.join(settings.INSTALL_ROOT, 'cl/assets/media/test/')
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
