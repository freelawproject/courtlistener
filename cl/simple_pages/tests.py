from django.http import HttpRequest
from django.test import TestCase
from cl.simple_pages.views import serve_static_file

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


class StaticFilesTest(TestCase):

    def test_serve_static_file_serves_mp3(self):
        request = HttpRequest()
        file_path = 'test/audio/2.mp3'
        response = serve_static_file(request, file_path=file_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'audio/mpeg')
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_serve_static_file_serves_txt(self):
        request = HttpRequest()
        file_path = 'test/search/opinion_text.txt'
        response = server_static_file(request, file_path=file_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn(
            'FOR THE DISTRICT OF COLUMBIA CIRCUIT',
            response.content
        )

    def test_serve_static_file_serves_pdf(self):
        request = HttpRequest()
        file_path = 'test/search/opinion_pdf_text_based.pdf'
        response = server_static_file(request, file_path=file_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
