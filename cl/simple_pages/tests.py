# coding=utf-8
from __future__ import print_function

import datetime
import os

from django.conf import settings
from django.core import mail
from django.core.urlresolvers import reverse
from django.http import HttpRequest
from django.test import TestCase
from django.test.utils import override_settings
from lxml.html import fromstring

from cl.audio.models import Audio
from cl.search.models import Opinion, OpinionCluster, Docket, Court
from cl.simple_pages.views import serve_static_file


class ContactTest(TestCase):
    fixtures = ['authtest_data.json']
    test_msg = {
        'name': "pandora",
        'phone_number': "asdf",
        'message': '123456789012345678901',
        'email': 'pandora@box.com',
        'skip_me_if_alive': "",
    }

    def test_multiple_requests_request(self):
        """ Is state persisted in the contact form?

        The contact form is abstracted in a way that it can have peculiar
        behavior when called multiple times. This test makes sure that that
        behavior does not regress.
        """
        self.client.login(username='pandora', password='password')
        self.client.get(reverse('contact'))
        self.client.logout()

        # Now, as an anonymous user, we get the page again. If the bug is
        # resolved, we should not see anything about the previously logged-in
        # user, pandora.
        r = self.client.get(reverse('contact'))
        self.assertNotIn('pandora', r.content)

    def test_contact_logged_in(self):
        """Can we use the contact form to send a message when logged in?"""
        self.client.login(username='pandora', password='password')
        response = self.client.post(reverse('contact'), self.test_msg)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_contact_logged_out(self):
        """Can we use the contact form to send a message when logged out?"""
        response = self.client.post(reverse('contact'), self.test_msg)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_contact_unicode(self):
        """Can unicode be used when contacting us?"""
        msg = self.test_msg.copy()
        msg['message'] = (
            'Possible ideas and thoughts are vast in number. A distinct word '
            'for every distinct idea and thought would require a vast '
            'vocabulary. The problem in language is to express many ideas and '
            'thoughts with comparatively few words. — John Wesley Powell'
        )
        response = self.client.post(reverse('contact'), msg)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_spam_message_is_rejected(self):
        """Do we reject it if people put a phone number in the phone_number
        field?

        We should! The phone_number field is labeled as the Subject field in the
        UI. Anything putting a phone number in here is a bot to be rejected.
        """
        msg = self.test_msg.copy()
        msg['phone_number'] = '909-576-4123'
        response = self.client.post(reverse('contact'), msg)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

        # Number in middle of subject is OK!
        msg['phone_number'] = 'asdf 909 asdf'
        response = self.client.post(reverse('contact'), msg)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)


class SimplePagesTest(TestCase):

    def check_for_title(self, content):
        """Make sure a page has a valid HTML title"""
        print("Checking for HTML title tag....", end='')
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

        print("✓")

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
            {'viewname': 'alert_help'},
            {'viewname': 'markdown_help'},
            {'viewname': 'advanced_search'},
            {'viewname': 'old_terms', 'args': ['1']},
            {'viewname': 'old_terms', 'args': ['2']},
            {'viewname': 'terms'},
            {'viewname': 'tools'},
            {'viewname': 'bad_browser'},
            {'viewname': 'robots'},
            {'viewname': 'humans'},
        ]
        for reverse_param in reverse_params:
            path = reverse(**reverse_param)
            print("Testing basic load of: {path}...".format(path=path), end='')
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
            print('✓')
            is_html = ('text/html' in r['content-type'])
            if r['content-type'] and is_html:
                self.check_for_title(r.content)


@override_settings(
    MEDIA_ROOT=os.path.join(settings.INSTALL_ROOT, 'cl/assets/media/test/')
)
class StaticFilesTest(TestCase):
    good_mp3_path = 'mp3/2014/06/09/ander_v._leo.mp3'
    good_txt_path = 'txt/2015/12/28/opinion_text.txt'
    good_pdf_path = 'pdf/2013/06/12/' + \
                    'in_re_motion_for_consent_to_disclosure_of_court_records.pdf'

    def setUp(self):
        self.court = Court.objects.get(pk='test')
        self.docket = Docket(case_name=u'Docket', court=self.court, source=Docket.DEFAULT)
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
        self.txtopinion.save(index=False)

        self.pdfopinion = Opinion(
            cluster=self.opinioncluster,
            type='Lead Opinion',
            local_path=self.good_pdf_path
        )
        self.pdfopinion.save(index=False)

    def test_serve_static_file_serves_mp3(self):
        request = HttpRequest()
        file_path = self.audio.local_path_mp3
        response = serve_static_file(request, file_path=self.good_mp3_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'audio/mpeg')
        self.assertIn('inline;', response['Content-Disposition'])

    def test_serve_static_file_serves_txt(self):
        request = HttpRequest()
        response = serve_static_file(request, file_path=self.good_txt_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertIn('inline;', response['Content-Disposition'])
        self.assertIn(
            'FOR THE DISTRICT OF COLUMBIA CIRCUIT',
            response.content
        )

    def test_serve_static_file_serves_pdf(self):
        request = HttpRequest()
        response = serve_static_file(request, file_path=self.good_pdf_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('inline;', response['Content-Disposition'])
