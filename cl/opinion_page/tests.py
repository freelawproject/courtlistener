# mypy: disable-error-code=attr-defined
import datetime
import os
import shutil
from unittest import mock
from unittest.mock import MagicMock

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test.client import Client
from django.urls import reverse
from django.utils.text import slugify
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_300_MULTIPLE_CHOICES,
    HTTP_302_FOUND,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from cl.lib.storage import clobbering_get_name
from cl.lib.test_helpers import SimpleUserDataMixin, SitemapTest
from cl.opinion_page.forms import CourtUploadForm
from cl.opinion_page.views import get_prev_next_volumes, make_docket_title
from cl.people_db.factories import PersonFactory, PositionFactory
from cl.people_db.models import Person
from cl.recap.factories import (
    AppellateAttachmentFactory,
    AppellateAttachmentPageFactory,
    DocketEntriesDataFactory,
    DocketEntryDataFactory,
)
from cl.recap.mergers import add_docket_entries, merge_attachment_page_data
from cl.search.factories import (
    CitationWithParentsFactory,
    CourtFactory,
    DocketFactory,
    OpinionClusterFactoryWithChildrenAndParents,
    OpinionClusterWithParentsFactory,
)
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    Citation,
    Docket,
    Opinion,
    OpinionCluster,
)
from cl.tests.cases import SimpleTestCase, TestCase
from cl.users.factories import UserFactory


class TitleTest(SimpleTestCase):
    def test_make_title_no_docket_number(self) -> None:
        """Can we make titles?"""
        # No docket number
        d = Docket(case_name="foo", docket_number=None)
        self.assertEqual(make_docket_title(d), "foo")


class SimpleLoadTest(TestCase):
    fixtures = [
        "test_objects_search.json",
        "judge_judy.json",
        "recap_docs.json",
    ]

    def test_simple_opinion_page(self) -> None:
        """Does the page load properly?"""
        path = reverse("view_case", kwargs={"pk": 1, "_": "asdf"})
        response = self.client.get(path)
        self.assertEqual(response.status_code, HTTP_200_OK)
        self.assertIn("33 state 1", response.content.decode())

    def test_simple_rd_page(self) -> None:
        path = reverse(
            "view_recap_document",
            kwargs={"docket_id": 1, "doc_num": "1", "slug": "asdf"},
        )
        response = self.client.get(path)
        self.assertEqual(response.status_code, HTTP_200_OK)


class DocumentPageRedirection(TestCase):
    """
    Test to make sure the document page of appellate entries redirect users
    to the attachment page if the main document got converted into an attachment
    """

    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="ca1", jurisdiction="F")
        cls.docket = DocketFactory(
            court=cls.court, source=Docket.RECAP, pacer_case_id="104490"
        )
        cls.de_data = DocketEntriesDataFactory(
            docket_entries=[
                DocketEntryDataFactory(
                    pacer_doc_id="288651",
                    document_number=1,
                )
            ],
        )
        add_docket_entries(cls.docket, cls.de_data["docket_entries"])

        cls.att_data = AppellateAttachmentPageFactory(
            attachments=[
                AppellateAttachmentFactory(
                    attachment_number=1, pacer_doc_id="288651"
                ),
                AppellateAttachmentFactory(),
            ],
            pacer_doc_id="288651",
            pacer_case_id="104490",
        )
        merge_attachment_page_data(
            cls.court,
            cls.att_data["pacer_case_id"],
            cls.att_data["pacer_doc_id"],
            None,
            "",
            cls.att_data["attachments"],
        )

    def test_redirect_to_attachment_page(self) -> None:
        """Does the page redirect to the attachment page?"""
        path = reverse(
            "view_recap_document",
            kwargs={
                "docket_id": self.docket.pk,
                "doc_num": 1,
                "slug": self.docket.slug,
            },
        )
        r = self.client.get(path, follow=True)
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)
        self.assertEqual(r.status_code, HTTP_200_OK)


class CitationRedirectorTest(TestCase):
    """Tests to make sure that the basic citation redirector is working."""

    fixtures = ["test_objects_search.json", "judge_judy.json"]
    citation = {"reporter": "F.2d", "volume": "56", "page": "9"}

    def assertStatus(self, r, status):
        self.assertEqual(
            r.status_code,
            status,
            msg=f"Didn't get a {status} status code. Got {r.status_code} instead.",
        )

    def test_citation_homepage(self) -> None:
        r = self.client.get(reverse("citation_homepage"))
        self.assertStatus(r, HTTP_200_OK)

    def test_with_a_citation(self) -> None:
        """Make sure that the url paths are working properly."""
        # Are we redirected to the correct place when we use GET or POST?
        r = self.client.get(
            reverse("citation_redirector", kwargs=self.citation), follow=True
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)

        r = self.client.post(
            reverse("citation_redirector"), self.citation, follow=True
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)

    def test_multiple_results(self) -> None:
        """Do we return a 300 status code when there are multiple results?"""
        # Duplicate the citation and add it to another cluster instead.
        f2_cite = Citation.objects.get(**self.citation)
        f2_cite.pk = None
        f2_cite.cluster_id = 3
        f2_cite.save()
        self.citation["reporter"] = slugify(self.citation["reporter"])
        r = self.client.get(
            reverse("citation_redirector", kwargs=self.citation)
        )
        self.assertStatus(r, HTTP_300_MULTIPLE_CHOICES)
        f2_cite.delete()

    def test_unknown_citation(self) -> None:
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

    def test_invalid_page_number_1918(self) -> None:
        """Do we fail gracefully with invalid page numbers?"""
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    "reporter": "f2d",
                    "volume": "1",
                    "page": "asdf",  # <-- Nasty, nasty hobbits
                },
            ),
        )
        self.assertStatus(r, HTTP_404_NOT_FOUND)

    def test_long_numbers(self) -> None:
        """Do really long WL citations work?"""
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "wl", "volume": "2012", "page": "2995064"},
            ),
        )
        self.assertStatus(r, HTTP_404_NOT_FOUND)

    def test_volume_page(self) -> None:
        r = self.client.get(
            reverse("citation_redirector", kwargs={"reporter": "f2d"})
        )
        self.assertStatus(r, HTTP_200_OK)

    def test_case_page(self) -> None:
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "f2d", "volume": "56"},
            )
        )
        self.assertStatus(r, HTTP_200_OK)

    def test_link_to_page_in_citation(self) -> None:
        """Test link to page with star pagination"""
        # Here opinion cluster 2 has the citation 56 F.2d 9, but the
        # HTML with citations contains star pagination for pages 9 and 10.
        # This tests if we can find opinion cluster 2 with page 9 and 10
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "f2d", "volume": "56", "page": "9"},
            )
        )
        self.assertEqual(r.url, "/opinion/2/case-name-cluster/")

        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "f2d", "volume": "56", "page": "10"},
            )
        )
        self.assertEqual(r.url, "/opinion/2/case-name-cluster/")

    def test_slugifying_reporters(self) -> None:
        """Test reporter slugification"""
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "F.2d", "volume": "56", "page": "9"},
            )
        )
        self.assertEqual(r.url, "/c/f2d/56/9/")

    def test_reporter_variation_just_reporter(self) -> None:
        """Do we redirect properly when we get reporter variations?"""
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    # Introduce a space (slugified to a dash) into the reporter
                    "reporter": "f-2d",
                },
            )
        )
        self.assertEqual(r.status_code, HTTP_302_FOUND)
        self.assertEqual(r.url, "/c/f2d/")

    def test_reporter_variation_just_reporter_and_volume(self) -> None:
        """Do we redirect properly when we get reporter variations?"""
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    # Introduce a space (slugified to a dash) into the reporter
                    "reporter": "f-2d",
                    "volume": "56",
                },
            )
        )
        self.assertEqual(r.status_code, HTTP_302_FOUND)
        self.assertEqual(r.url, "/c/f2d/56/")

    def test_reporter_variation_full_citation(self) -> None:
        """Do we redirect properly when we get reporter variations?"""
        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    # Introduce a space (slugified to a dash) into the reporter
                    "reporter": "f-2d",
                    "volume": "56",
                    "page": "9",
                },
            )
        )
        self.assertEqual(r.status_code, HTTP_302_FOUND)
        self.assertEqual(r.url, "/c/f2d/56/9/")

    def test_volume_pagination(self) -> None:
        """Can we properly paginate reporter volume numbers?"""

        # Create test data usign factories
        test_obj = CitationWithParentsFactory.create(
            volume="2016",
            reporter="COA",
            page="1",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=CourtFactory(id="coloctapp")),
                case_name="In re the Marriage of Morton",
                date_filed=datetime.date(2016, 1, 14),
            ),
        )

        CitationWithParentsFactory.create(
            volume="2017",
            reporter="COA",
            page="3",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=CourtFactory(id="coloctapp")),
                case_name="Begley v. Ireson",
                date_filed=datetime.date(2017, 1, 12),
            ),
        )

        CitationWithParentsFactory.create(
            volume="2018",
            reporter="COA",
            page="1",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=CourtFactory(id="coloctapp")),
                case_name="People v. Sparks",
                date_filed=datetime.date(2018, 1, 11),
            ),
        )

        CitationWithParentsFactory.create(
            volume="2018",
            reporter="COA",
            page="1",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=CourtFactory(id="coloctapp")),
                case_name="People v. Sparks",
                date_filed=datetime.date(2018, 1, 11),
            ),
        )

        # Get previous and next volume for "2017 COA"
        volume_next, volume_previous = get_prev_next_volumes("COA", "2017")
        self.assertEqual(volume_previous, 2016)
        self.assertEqual(volume_next, 2018)

        # Delete previous
        test_obj.delete()

        # Only get next volume for "2017 COA"
        volume_next, volume_previous = get_prev_next_volumes("COA", "2017")
        self.assertEqual(volume_previous, None)
        self.assertEqual(volume_next, 2018)

        # Create new test data
        CitationWithParentsFactory.create(
            volume="454",
            reporter="U.S.",
            page="1",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=CourtFactory(id="scotus")),
                case_name="Duckworth v. Serrano",
                date_filed=datetime.date(1981, 10, 19),
            ),
        )

        # No next or previous volume for "454 U.S."
        volume_next, volume_previous = get_prev_next_volumes("U.S.", "454")
        self.assertEqual(volume_previous, None)
        self.assertEqual(volume_next, None)

    def test_full_citation_redirect(self) -> None:
        """Do we get redirected to the correct URL when we pass in a full
        citation?"""

        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    "reporter": "Reference to Lissner v. Saad, 56 F.2d 9 11 (1st Cir. 2015)",
                },
            ),
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)
        self.assertEqual(r.status_code, HTTP_200_OK)
        self.assertEqual(
            r.redirect_chain[0][0], "/opinion/2/case-name-cluster/"
        )

    def test_avoid_exception_possible_matches_page_with_letter(self) -> None:
        """Can we order the possible matches when page number contains a
        letter without getting a DataError exception?"""

        # See: freelawproject/courtlistener#2474

        # Create the citation that contains 40M as page number and was
        # causing the exception
        CitationWithParentsFactory.create(
            volume="2017",
            reporter="COA",
            page="40M",
            cluster=OpinionClusterFactoryWithChildrenAndParents(
                docket=DocketFactory(court=CourtFactory(id="coloctapp")),
                case_name="People v. Davis",
                date_filed=datetime.date(2017, 5, 4),
            ),
        )

        r = self.client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    "reporter": "coa",
                    "volume": "2017",
                    "page": "157",
                },
            ),
        )
        self.assertStatus(r, HTTP_404_NOT_FOUND)


class ViewRecapDocketTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.docket = DocketFactory(
            court=cls.court,
            source=Docket.RECAP,
        )
        cls.court_appellate = CourtFactory(id="ca1", jurisdiction="F")
        cls.docket_appellate = DocketFactory(
            court=cls.court_appellate,
            source=Docket.RECAP,
        )

    def test_regular_docket_url(self) -> None:
        """Can we load a regular docket sheet?"""
        r = self.client.get(
            reverse("view_docket", args=[self.docket.pk, self.docket.slug])
        )
        self.assertEqual(r.status_code, HTTP_200_OK)

    def test_recap_docket_url(self) -> None:
        """Can we redirect to a regular docket URL from a recap/uscourts.*
        URL?
        """
        r = self.client.get(
            reverse(
                "redirect_docket_recap",
                kwargs={
                    "court": self.court.pk,
                    "pacer_case_id": self.docket.pacer_case_id,
                },
            ),
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], HTTP_302_FOUND)

    def test_docket_view_counts_increment_by_one(self) -> None:
        """Test the view count for a Docket increments on page view"""

        old_view_count = self.docket.view_count
        r = self.client.get(
            reverse("view_docket", args=[self.docket.pk, self.docket.slug])
        )
        self.assertEqual(r.status_code, HTTP_200_OK)
        self.docket.refresh_from_db(fields=["view_count"])
        self.assertEqual(old_view_count + 1, self.docket.view_count)

    def test_appellate_docket_no_pacer_case_id_increment_view_count(
        self,
    ) -> None:
        """Test the view count for a RECAP Docket without pacer_case_id
        increments on page view
        """

        # Set pacer_case_id blank
        Docket.objects.filter(pk=self.docket_appellate.pk).update(
            pacer_case_id=None
        )
        old_view_count = self.docket_appellate.view_count
        r = self.client.get(
            reverse(
                "view_docket",
                args=[self.docket_appellate.pk, self.docket_appellate.slug],
            )
        )
        self.assertEqual(r.status_code, HTTP_200_OK)
        self.docket_appellate.refresh_from_db(fields=["view_count"])
        self.assertEqual(old_view_count + 1, self.docket_appellate.view_count)


class OgRedirectLookupViewTest(TestCase):
    fixtures = ["recap_docs.json"]

    def setUp(self) -> None:
        self.client = Client(HTTP_USER_AGENT="facebookexternalhit")
        self.url = reverse("redirect_og_lookup")

    def test_do_we_404_no_param(self) -> None:
        """Does the view return 404 when no parameters given?"""
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, HTTP_404_NOT_FOUND)

    def test_unknown_doc(self) -> None:
        """Do we redirect to S3 when unknown file path?"""
        r = self.client.get(self.url, {"file_path": "xxx"})
        self.assertEqual(r.status_code, HTTP_302_FOUND)

    @mock.patch("cl.opinion_page.views.make_png_thumbnail_for_instance")
    def test_success_goes_to_view(self, mock: MagicMock) -> None:
        path = (
            "recap/dev.gov.uscourts.txnd.28766/gov.uscourts.txnd.28766.1.0.pdf"
        )
        r = self.client.get(self.url, {"file_path": path})
        self.assertEqual(r.status_code, HTTP_200_OK)
        mock.assert_called_once()


class NewDocketAlertTest(SimpleUserDataMixin, TestCase):
    fixtures = [
        "test_objects_search.json",
        "judge_judy.json",
        "test_court.json",
    ]

    def setUp(self) -> None:
        self.assertTrue(
            self.client.login(username="pandora", password="password")
        )

    def test_bad_parameters(self) -> None:
        """If we omit the pacer_case_id and court_id params, do things fail?"""
        r = self.client.get(reverse("new_docket_alert"))
        self.assertEqual(r.status_code, HTTP_400_BAD_REQUEST)

    def test_unknown_docket(self) -> None:
        """What happens if no docket?"""
        r = self.client.get(
            reverse("new_docket_alert"),
            data={"pacer_case_id": "blah", "court_id": "blah"},
        )
        self.assertEqual(r.status_code, HTTP_404_NOT_FOUND)
        self.assertIn("Refresh this Page", r.content.decode())

    def test_all_systems_go(self) -> None:
        """Does everything work with good parameters and good data?"""
        r = self.client.get(
            reverse("new_docket_alert"),
            data={"pacer_case_id": "666666", "court_id": "test"},
        )
        self.assertEqual(r.status_code, HTTP_200_OK)
        self.assertInHTML("Get Docket Alerts", r.content.decode())


class OpinionSitemapTest(SitemapTest):
    @classmethod
    def setUpTestData(cls) -> None:
        # Included b/c so new
        OpinionClusterWithParentsFactory.create(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            citation_count=0,
            date_filed=datetime.date.today(),
        )
        # Included b/c cited
        OpinionClusterWithParentsFactory.create(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            citation_count=1,
            date_filed=datetime.date.today() - datetime.timedelta(365 * 15),
        )
        # Excluded because no cites
        OpinionClusterWithParentsFactory.create(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            citation_count=0,
            date_filed=datetime.date.today() - datetime.timedelta(365 * 15),
        )
        # Excluded because blocked
        OpinionClusterWithParentsFactory.create(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            citation_count=100,
            blocked=True,
        )

    def setUp(self) -> None:
        self.sitemap_url = reverse(
            "sitemaps", kwargs={"section": SEARCH_TYPES.OPINION}
        )
        self.expected_item_count = 2

    def test_does_the_sitemap_have_content(self) -> None:
        super().assert_sitemap_has_content()


class DocketSitemapTest(SitemapTest):
    @classmethod
    def setUpTestData(cls) -> None:
        # Included b/c so new
        DocketFactory.create(
            source=Docket.RECAP,
            blocked=False,
            view_count=0,
            date_filed=datetime.date.today(),
        )
        # Included b/c many views
        DocketFactory.create(
            source=Docket.RECAP,
            blocked=False,
            view_count=50,
            date_filed=datetime.date.today() - datetime.timedelta(days=60),
        )
        # Excluded b/c blocked
        DocketFactory.create(
            source=Docket.RECAP,
            blocked=True,
        )

    def setUp(self) -> None:
        self.sitemap_url = reverse(
            "sitemaps", kwargs={"section": SEARCH_TYPES.RECAP}
        )
        self.expected_item_count = 2

    def test_does_the_sitemap_have_content(self) -> None:
        super().assert_sitemap_has_content()


class BlockedSitemapTest(SitemapTest):
    """Do we create sitemaps of recently blocked opinions?"""

    @classmethod
    def setUpTestData(cls) -> None:
        # Included b/c recently blocked
        OpinionClusterWithParentsFactory.create(
            blocked=True,
            date_blocked=datetime.date.today(),
        )
        # Excluded b/c blocked too long ago
        OpinionClusterWithParentsFactory.create(
            blocked=True,
            date_blocked=datetime.date.today() - datetime.timedelta(days=60),
        )

    def setUp(self) -> None:
        self.sitemap_url = reverse(
            "sitemaps", kwargs={"section": "blocked-opinions"}
        )
        self.expected_item_count = 1

    def test_does_the_sitemap_have_content(self) -> None:
        super().assert_sitemap_has_content()


@override_settings(
    MEDIA_ROOT=os.path.join(settings.INSTALL_ROOT, "cl/assets/media/test/")
)
@mock.patch(
    "cl.lib.storage.get_name_by_incrementing",
    side_effect=clobbering_get_name,
)
class UploadPublication(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        # Create courts
        court_cl = CourtFactory.create(id="tennworkcompcl")
        court_app = CourtFactory.create(id="tennworkcompapp")

        # Create judges
        people = PersonFactory.create_batch(4)
        for person in people[:3]:
            PositionFactory.create(court=court_app, person=person)
        PositionFactory.create(court=court_cl, person=people[3])

        # Create users
        cls.tenn_user = UserFactory.create(
            username="learned",
            email="learnedhand@scotus.gov",
        )
        Group.objects.create(name="uploaders_tennworkcompcl")
        Group.objects.create(name="uploaders_tennworkcompapp")
        tenn_cl_group = Group.objects.get(name="uploaders_tennworkcompcl")
        tenn_app_group = Group.objects.get(name="uploaders_tennworkcompapp")
        cls.tenn_user.groups.add(tenn_cl_group)
        cls.tenn_user.groups.add(tenn_app_group)

        cls.reg_user = UserFactory.create(
            username="test_user",
            email="test_user@scotus.gov",
        )

        # Other stuff
        cls.pdf = SimpleUploadedFile(
            "file.pdf",
            b"%PDF-1.trailer<</Root<</Pages<</Kids[<</MediaBox[0 0 3 3]>>]>>>>>>",
            content_type="application/pdf",
        )
        cls.png = SimpleUploadedFile(
            "file.png", b"file_content", content_type="image/png"
        )

    def setUp(self) -> None:
        self.client = Client()

        qs = Person.objects.filter(positions__court_id="tennworkcompapp")
        self.work_comp_app_data = {
            "case_title": "A Sample Case",
            "lead_author": qs[0].id,
            "second_judge": qs[1].id,
            "third_judge": qs[2].id,
            "docket_number": "2016-231-12332",
            "court_str": "tennworkcompapp",
            "pk": "tennworkcompapp",
            "cite_volume": "2020",
            "cite_reporter": "TN WC App.",
            "cite_page": "1",
            "publication_date": datetime.date(2019, 4, 13),
        }

        self.work_comp_data = {
            "lead_author": Person.objects.filter(
                positions__court_id="tennworkcompcl"
            )[0].id,
            "case_title": "A Sample Case",
            "docket_number": "2016-231-12332",
            "court_str": "tennworkcompcl",
            "pk": "tennworkcompcl",
            "cite_volume": "2020",
            "cite_reporter": "TN WC",
            "cite_page": "1",
            "publication_date": datetime.date(2019, 4, 13),
        }

    def tearDown(self) -> None:
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, "pdf/2019/")):
            shutil.rmtree(os.path.join(settings.MEDIA_ROOT, "pdf/2019/"))
        Docket.objects.all().delete()

    def test_access_upload_page(self, mock) -> None:
        """Can we successfully access upload page with access?"""
        self.client.login(username="learned", password="password")
        response = self.client.get(
            reverse("court_publish_page", args=["tennworkcompcl"])
        )
        self.assertEqual(response.status_code, 200)

    def test_redirect_without_access(self, mock) -> None:
        """Can we successfully redirect individuals without proper access?"""
        self.client.login(username="test_user", password="password")
        response = self.client.get(
            reverse("court_publish_page", args=["tennworkcompcl"])
        )
        self.assertEqual(response.status_code, 302)

    def test_pdf_upload(self, mock) -> None:
        """Can we upload a PDF and form?"""
        form = CourtUploadForm(
            self.work_comp_data,
            pk="tennworkcompcl",
            files={"pdf_upload": self.pdf},
        )
        form.fields["lead_author"].queryset = Person.objects.filter(
            positions__court_id="tennworkcompcl"
        )

        # Validate that no citations exist
        count = OpinionCluster.objects.all().count()
        cite_count = Citation.objects.all().count()
        self.assertEqual(
            0, count, msg=f"The opinion count should be zero not {count}"
        )
        self.assertEqual(
            0,
            cite_count,
            msg=f"The citation count should be zero not {cite_count}",
        )

        if form.is_valid():
            form.save()
        self.assertEqual(form.is_valid(), True, form.errors)

        # Validate that citations were created on upload.
        count = OpinionCluster.objects.all().count()
        cite_count = Citation.objects.all().count()
        self.assertEqual(
            1, count, msg=f"The opinion count should be zero not {count}"
        )
        self.assertEqual(
            1,
            cite_count,
            msg=f"The citation count should be zero not {cite_count}",
        )

    def test_pdf_validation_failure(self, mock) -> None:
        """Can we fail upload documents that are not PDFs?"""
        form = CourtUploadForm(
            self.work_comp_data,
            pk="tennworkcompcl",
            files={"pdf_upload": self.png},
        )
        form.fields["lead_author"].queryset = Person.objects.filter(
            positions__court_id="tennworkcompcl"
        )
        self.assertFalse(form.is_valid(), form.errors)
        self.assertEqual(
            form.errors["pdf_upload"],
            [
                "File extension “png” is not allowed. Allowed "
                "extensions are: pdf."
            ],
        )

    def test_tn_wc_app_upload(self, mock) -> None:
        """Can we test appellate uploading?"""
        form = CourtUploadForm(
            self.work_comp_app_data,
            pk="tennworkcompapp",
            files={"pdf_upload": self.pdf},
        )
        qs = Person.objects.filter(positions__court_id="tennworkcompapp")
        form.fields["lead_author"].queryset = qs
        form.fields["second_judge"].queryset = qs
        form.fields["third_judge"].queryset = qs

        # Check no citations exist before upload
        count = OpinionCluster.objects.all().count()
        cite_count = Citation.objects.all().count()
        self.assertEqual(
            0, count, msg=f"The opinion count should be zero not {count}"
        )
        self.assertEqual(
            0,
            cite_count,
            msg=f"The citation count should be zero not {cite_count}",
        )

        if form.is_valid():
            form.save()
        self.assertEqual(form.is_valid(), True, form.errors)

        # Check that citations were created on upload.
        count = OpinionCluster.objects.all().count()
        cite_count = Citation.objects.all().count()
        self.assertEqual(
            1, count, msg=f"The opinion count should be zero not {count}"
        )
        self.assertEqual(
            1,
            cite_count,
            msg=f"The citation count should be zero not {cite_count}",
        )

    def test_required_case_title(self, mock) -> None:
        """Can we validate required testing field case title?"""
        self.work_comp_app_data.pop("case_title")

        form = CourtUploadForm(
            self.work_comp_app_data,
            pk="tennworkcompapp",
            files={"pdf_upload": self.pdf},
        )
        qs = Person.objects.filter(positions__court_id="tennworkcompapp")
        form.fields["lead_author"].queryset = qs
        form.fields["second_judge"].queryset = qs
        form.fields["third_judge"].queryset = qs
        form.is_valid()
        self.assertEqual(
            form.errors["case_title"], ["This field is required."]
        )

    def test_form_save(self, mock) -> None:
        """Can we save successfully to db?"""

        pre_count = Opinion.objects.all().count()

        form = CourtUploadForm(
            self.work_comp_app_data,
            pk="tennworkcompapp",
            files={"pdf_upload": self.pdf},
        )
        qs = Person.objects.filter(positions__court_id="tennworkcompapp")
        form.fields["lead_author"].queryset = qs
        form.fields["second_judge"].queryset = qs
        form.fields["third_judge"].queryset = qs

        if form.is_valid():
            form.save()

        self.assertEqual(pre_count + 1, Opinion.objects.all().count())

    def test_form_two_judges_2042(self, mock) -> None:
        """Can we still save if there's only one or two judges on the panel?"""
        pre_count = Opinion.objects.all().count()

        # Remove a judge from the data
        self.work_comp_app_data["third_judge"] = None

        form = CourtUploadForm(
            self.work_comp_app_data,
            pk="tennworkcompapp",
            files={"pdf_upload": self.pdf},
        )
        qs = Person.objects.filter(positions__court_id="tennworkcompapp")
        form.fields["lead_author"].queryset = qs
        form.fields["second_judge"].queryset = qs
        # form.fields["third_judge"].queryset = qs

        if form.is_valid():
            form.save()

        self.assertEqual(pre_count + 1, Opinion.objects.all().count())

    def test_handle_duplicate_pdf(self, mock) -> None:
        """Can we validate PDF not in system?"""
        d = Docket.objects.create(
            source=Docket.DIRECT_INPUT,
            court_id="tennworkcompcl",
            pacer_case_id=None,
            docket_number="1234123",
            case_name="One v. Two",
        )
        oc = OpinionCluster.objects.create(
            case_name="One v. Two",
            docket=d,
            date_filed=datetime.date(2010, 1, 1),
        )
        Opinion.objects.create(
            cluster=oc,
            type="Lead Opinion",
            sha1="ffe0ec472b16e4e573aa1bbaf2ae358460b5d72c",
        )

        form2 = CourtUploadForm(
            self.work_comp_data,
            pk="tennworkcompcl",
            files={"pdf_upload": self.pdf},
        )
        form2.fields["lead_author"].queryset = Person.objects.filter(
            positions__court_id="tennworkcompcl"
        )
        if form2.is_valid():
            form2.save()

        self.assertIn(
            "Document already in database", form2.errors["pdf_upload"][0]
        )
