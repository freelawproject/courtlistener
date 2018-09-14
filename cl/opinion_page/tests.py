from django.core.urlresolvers import reverse
from django.test import TestCase
from rest_framework.status import HTTP_200_OK, HTTP_404_NOT_FOUND, \
    HTTP_302_FOUND


class ViewDocumentTest(TestCase):
    fixtures = ['test_objects_search.json', 'judge_judy.json']

    def test_simple_url_check_for_document(self):
        """Does the page load properly?"""
        response = self.client.get('/opinion/1/asdf/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('33 state 1', response.content)


class CitationRedirectorTest(TestCase):
    """Tests to make sure that the basic citation redirector is working."""
    fixtures = ['test_objects_search.json', 'judge_judy.json']

    def assertStatus(self, r, status):
        self.assertEqual(
            r.status_code,
            status,
            msg="Didn't get a {expected} status code. Got {got} "
                "instead.".format(expected=status, got=r.status_code)
        )

    def test_with_and_without_a_citation(self):
        """Make sure that the url paths are working properly."""
        r = self.client.get(reverse('citation_redirector'))
        self.assertStatus(r, HTTP_200_OK)

        citation = {'reporter': 'F.2d', 'volume': '56', 'page': '9'}

        # Are we redirected to the correct place when we use GET or POST?
        r = self.client.get(
            reverse('citation_redirector', kwargs=citation),
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)

        r = self.client.post(
            reverse('citation_redirector'),
            citation,
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)

    def test_unknown_citation(self):
        """Do we get a 404 message if we don't know the citation?"""
        r = self.client.get(
            reverse('citation_redirector', kwargs={
                'reporter': 'bad-reporter',
                'volume': '1',
                'page': '1',
            }),
        )
        self.assertStatus(r, HTTP_404_NOT_FOUND)

    def test_long_numbers(self):
        """Do really long WL citations work?"""
        r = self.client.get(
            reverse('citation_redirector', kwargs={
                'reporter': 'WL',
                'volume': '2012',
                'page': '2995064'
            }),
        )
        self.assertStatus(r, HTTP_404_NOT_FOUND)


class ViewRecapDocketTest(TestCase):
    fixtures = ['test_objects_search.json', 'judge_judy.json']

    def test_regular_docket_url(self):
        """Can we load a regular docket sheet?"""
        r = self.client.get(reverse('view_docket', args=[1, 'case-name']))
        self.assertEqual(r.status_code, HTTP_200_OK)

    def test_recap_docket_url(self):
        """Can we redirect to a regular docket URL from a recap/uscourts.*
        URL?
        """
        r = self.client.get(reverse('redirect_docket_recap', kwargs={
            'court': 'test',
            'pacer_case_id': '666666',
        }), follow=True)
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)
