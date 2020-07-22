from django.conf import settings
from django.urls import reverse
from django.test import TestCase, override_settings
from django.test.client import Client
from django.contrib.auth.models import User, Group
from django.core.files.uploadedfile import SimpleUploadedFile

from cl.opinion_page.forms import TennWorkersForm
import datetime

from rest_framework.status import (
    HTTP_200_OK,
    HTTP_404_NOT_FOUND,
    HTTP_302_FOUND,
    HTTP_300_MULTIPLE_CHOICES,
    HTTP_400_BAD_REQUEST,
)

from cl.lib.scorched_utils import ExtraSolrInterface
from cl.lib.test_helpers import SitemapTest
from cl.opinion_page.views import make_docket_title
from cl.search.models import Citation, Docket
from cl.people_db.models import Person
from cl.sitemap import make_sitemap_solr_params, items_per_sitemap


class TitleTest(TestCase):
    def test_make_title_no_docket_number(self):
        """Can we make titles?"""
        # No docket number
        d = Docket(case_name="foo", docket_number=None)
        self.assertEqual(make_docket_title(d), "foo")


class ViewDocumentTest(TestCase):
    fixtures = ["test_objects_search.json", "judge_judy.json"]

    def test_simple_url_check_for_document(self):
        """Does the page load properly?"""
        response = self.client.get("/opinion/1/asdf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("33 state 1", response.content)


class CitationRedirectorTest(TestCase):
    """Tests to make sure that the basic citation redirector is working."""

    fixtures = ["test_objects_search.json", "judge_judy.json"]
    citation = {"reporter": "F.2d", "volume": "56", "page": "9"}

    def assertStatus(self, r, status):
        self.assertEqual(
            r.status_code,
            status,
            msg="Didn't get a {expected} status code. Got {got} "
            "instead.".format(expected=status, got=r.status_code),
        )

    def test_with_and_without_a_citation(self):
        """Make sure that the url paths are working properly."""
        r = self.client.get(reverse("citation_redirector"))
        self.assertStatus(r, HTTP_200_OK)

        # Are we redirected to the correct place when we use GET or POST?
        r = self.client.get(
            reverse("citation_redirector", kwargs=self.citation), follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)

        r = self.client.post(
            reverse("citation_redirector"), self.citation, follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)

    def test_multiple_results(self):
        """Do we return a 300 status code when there are multiple results?"""
        # Duplicate the citation and add it to another cluster instead.
        f2_cite = Citation.objects.get(**self.citation)
        f2_cite.pk = None
        f2_cite.cluster_id = 3
        f2_cite.save()
        r = self.client.get(
            reverse("citation_redirector", kwargs=self.citation)
        )
        self.assertStatus(r, HTTP_300_MULTIPLE_CHOICES)
        f2_cite.delete()

    def test_unknown_citation(self):
        """Do we get a 404 message if we don't know the citation?"""
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    "reporter": "bad-reporter",
                    "volume": "1",
                    "page": "1",
                },
            ),
        )
        self.assertStatus(r, HTTP_404_NOT_FOUND)

    def test_long_numbers(self):
        """Do really long WL citations work?"""
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "WL", "volume": "2012", "page": "2995064"},
            ),
        )
        self.assertStatus(r, HTTP_404_NOT_FOUND)

    def test_volume_page(self):
        r = self.client.get(
            reverse("citation_redirector", kwargs={"reporter": "F.2d",})
        )
        self.assertStatus(r, HTTP_200_OK)

    def test_case_page(self):
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "F.2d", "volume": "56",},
            )
        )
        self.assertStatus(r, HTTP_200_OK)


class ViewRecapDocketTest(TestCase):
    fixtures = ["test_objects_search.json", "judge_judy.json"]

    def test_regular_docket_url(self):
        """Can we load a regular docket sheet?"""
        r = self.client.get(reverse("view_docket", args=[1, "case-name"]))
        self.assertEqual(r.status_code, HTTP_200_OK)

    def test_recap_docket_url(self):
        """Can we redirect to a regular docket URL from a recap/uscourts.*
        URL?
        """
        r = self.client.get(
            reverse(
                "redirect_docket_recap",
                kwargs={"court": "test", "pacer_case_id": "666666",},
            ),
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)


class NewDocketAlertTest(TestCase):
    fixtures = [
        "test_objects_search.json",
        "judge_judy.json",
        "test_court.json",
    ]

    def test_bad_parameters(self):
        """If we omit the pacer_case_id and court_id params, do things fail?"""
        r = self.client.get(reverse("new_docket_alert"))
        self.assertEqual(r.status_code, HTTP_400_BAD_REQUEST)

    def test_unknown_docket(self):
        """What happens if no docket?"""
        r = self.client.get(
            reverse("new_docket_alert"),
            data={"pacer_case_id": "blah", "court_id": "blah"},
        )
        self.assertEqual(r.status_code, HTTP_404_NOT_FOUND)
        self.assertIn("Refresh this Page", r.content)

    def test_all_systems_go(self):
        """Does everything work with good parameters and good data?"""
        r = self.client.get(
            reverse("new_docket_alert"),
            data={"pacer_case_id": "666666", "court_id": "test"},
        )
        self.assertEqual(r.status_code, HTTP_200_OK)
        self.assertInHTML("Get Docket Alerts", r.content)


@override_settings(
    SOLR_OPINION_URL=settings.SOLR_OPINION_TEST_URL,
    SOLR_AUDIO_URL=settings.SOLR_AUDIO_TEST_URL,
)
class OpinionSitemapTest(SitemapTest):
    def __init__(self, *args, **kwargs):
        super(OpinionSitemapTest, self).__init__(*args, **kwargs)
        self.court_id = "test"
        self.sitemap_url = "%s?court=%s" % (
            reverse("opinion_sitemap"),
            self.court_id,
        )

    def get_expected_item_count(self):
        # OpinionsSitemap uses the solr index to generate the page, so the only
        # accurate count comes from the index itself which will also be based
        # on the fixtures.
        conn = ExtraSolrInterface(settings.SOLR_OPINION_URL)
        params = make_sitemap_solr_params("dateFiled asc", "o_sitemap")
        params["rows"] = items_per_sitemap
        params["fq"] = ["court_exact:%s" % self.court_id]

        r = conn.query().add_extra(**params).execute()

        # the underlying SitemapTest relies on counting url elements in the xml
        # response...this logic mimics the creation of the xml, so we at least
        # know what we *should* get getting for a count if the SiteMapTest's
        # HTTP client-based test gets an HTTP 200
        count = 0
        for result in r:
            if result.get("local_path"):
                count += 2
            else:
                count += 1
        return count

    def test_does_the_sitemap_have_content(self):
        # Class attributes are set, just run the test in super.
        self.expected_item_count = self.get_expected_item_count()
        super(OpinionSitemapTest, self).does_the_sitemap_have_content()


class UploadPublication(TestCase):

    fixtures = ["tenn_judges.json"]

    def setUp(self):
        self.client = Client()
        tenn_group = Group.objects.get(name="tenn_work_uploaders")
        self.tenn_user = User.objects.create_user(
            "learned", "learnedhand@scotus.gov", "thehandofjustice"
        )
        self.reg_user = User.objects.create_user(
            "test_user", "test_user@scotus.gov", "simplepassword"
        )

        self.tenn_user.groups.add(tenn_group)
        self.tenn_user.save()

        self.pdf = SimpleUploadedFile(
            "file.pdf", "file_content", content_type="application/pdf"
        )
        self.png = SimpleUploadedFile(
            "file.png", "file_content", content_type="image/png"
        )

        self.work_comp_app_data = {
            "case_title": "A Sample Case",
            "lead_author": 9708,
            "second_judge": 9709,
            "third_judge": 9710,
            "docket_number": "2016-231-12332",
            "court_str": "tennworkcompapp",
            "pk": "tennworkcompapp",
            "cite_volume": "2020",
            "cite_reporter": "TN WC App.",
            "cite_page": "1",
            "publication_date": datetime.date(2019, 4, 13),
        }

        self.work_comp_data = data = {
            "lead_author": 9707,  # 9707 is one of the tenn judges
            "case_title": "A Sample Case",
            "docket_number": "2016-231-12332",
            "court_str": "tenncompcl",
            "pk": "tenncompcl",
            "cite_volume": "2020",
            "cite_reporter": "TN WC",
            "cite_page": "1",
            "publication_date": datetime.date(2019, 4, 13),
        }

    def test_access_upload_page(self):
        # Test access to Tennessee publishing page
        self.client.login(username="learned", password="thehandofjustice")
        response = self.client.get(
            reverse("court_publishpage", args=["tennworkcompcl"])
        )
        self.assertEqual(response.status_code, 200)

    def test_redirect_without_access(self):
        # Test lack of access to Tennessee publishing page
        self.client.login(username="test_user", password="simplepassword")
        response = self.client.get(
            reverse("court_publishpage", args=["tennworkcompcl"])
        )
        self.assertEqual(response.status_code, 302)

    def test_pdf_upload(self):

        form = TennWorkersForm(
            self.work_comp_data,
            pk="tenncompcl",
            files={"pdf_upload": self.pdf},
        )
        form.fields["lead_author"].queryset = Person.objects.filter(
            positions__court_id="tennworkcompcl"
        )
        self.assertEqual(form.is_valid(), True, form.errors)

    def test_pdf_validation_failure(self):

        form = TennWorkersForm(
            self.work_comp_data,
            pk="tenncompcl",
            files={"pdf_upload": self.png},
        )
        form.fields["lead_author"].queryset = Person.objects.filter(
            positions__court_id="tennworkcompcl"
        )
        self.assertEqual(form.is_valid(), False, form.errors)
        self.assertEqual(
            form.errors["pdf_upload"],
            [
                "File extension 'png' is not allowed. Allowed extensions are: 'pdf'."
            ],
        )

    def test_tn_wc_app_upload(self):

        form = TennWorkersForm(
            self.work_comp_app_data,
            pk="tenncompcl",
            files={"pdf_upload": self.pdf},
        )
        qs = Person.objects.filter(positions__court_id="tennworkcompapp")
        form.fields["lead_author"].queryset = qs
        form.fields["second_judge"].queryset = qs
        form.fields["third_judge"].queryset = qs

        self.assertEqual(form.is_valid(), True, form.errors)

    def test_required_case_title(self):

        self.work_comp_app_data.pop("case_title")

        form = TennWorkersForm(
            self.work_comp_app_data,
            pk="tenncompcl",
            files={"pdf_upload": self.pdf},
        )
        qs = Person.objects.filter(positions__court_id="tennworkcompapp")
        form.fields["lead_author"].queryset = qs
        form.fields["second_judge"].queryset = qs
        form.fields["third_judge"].queryset = qs

        self.assertEqual(
            form.errors["case_title"], ["This field is required."]
        )
