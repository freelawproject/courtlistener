# mypy: disable-error-code=attr-defined
import datetime
import os
import re
import shutil
from datetime import date
from http import HTTPStatus
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import (
    AsyncRequestFactory,
    RequestFactory,
    SimpleTestCase,
    override_settings,
)
from django.test.client import AsyncClient
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from factory import RelatedFactory

from cl.citations.utils import slugify_reporter
from cl.lib.models import THUMBNAIL_STATUSES
from cl.lib.redis_utils import get_redis_interface
from cl.lib.storage import clobbering_get_name
from cl.opinion_page.forms import (
    MeCourtUploadForm,
    MissCourtUploadForm,
    MoCourtUploadForm,
    TennWorkCompAppUploadForm,
    TennWorkCompClUploadForm,
)
from cl.opinion_page.utils import (
    es_get_citing_and_related_clusters_with_cache,
    generate_docket_entries_csv_data,
    make_docket_title,
)
from cl.opinion_page.views import (
    download_docket_entries_csv,
    fetch_docket_entries,
    get_prev_next_volumes,
)
from cl.people_db.factories import (
    PersonFactory,
    PersonWithChildrenFactory,
    PositionFactory,
)
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
    DocketEntryFactory,
    DocketFactory,
    OpinionClusterWithChildrenAndParentsFactory,
    OpinionClusterWithParentsFactory,
    OpinionFactory,
    OpinionsCitedWithParentsFactory,
    RECAPDocumentFactory,
)
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SEARCH_TYPES,
    Citation,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    RECAPDocument,
)
from cl.sitemaps_infinite.sitemap_generator import generate_urls_chunk
from cl.tests.cases import ESIndexTestCase, TestCase
from cl.tests.mixins import (
    CourtMixin,
    PeopleMixin,
    SearchMixin,
    SimpleUserDataMixin,
    SitemapMixin,
)
from cl.tests.providers import fake
from cl.users.factories import UserFactory, UserProfileWithParentsFactory


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

    async def test_simple_rd_page(self) -> None:
        path = reverse(
            "view_recap_document",
            kwargs={"docket_id": 1, "doc_num": "1", "slug": "asdf"},
        )
        response = await self.async_client.get(path)
        self.assertEqual(response.status_code, HTTPStatus.OK)


class OpinionPageLoadTest(
    SearchMixin,
    PeopleMixin,
    CourtMixin,
    ESIndexTestCase,
):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.o_cluster_1 = OpinionClusterWithParentsFactory.create(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            citation_count=1,
            date_filed=datetime.date.today(),
        )
        cls.o_1 = OpinionFactory.create(
            cluster=cls.o_cluster_1,
            type=Opinion.COMBINED,
        )
        cls.o_cluster_2 = OpinionClusterWithParentsFactory.create(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            citation_count=4,
            date_filed=datetime.date.today(),
        )
        cls.o_2 = OpinionFactory.create(
            cluster=cls.o_cluster_2,
            type=Opinion.COMBINED,
        )
        cls.o_cluster_3 = OpinionClusterWithParentsFactory.create(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            citation_count=0,
            date_filed=datetime.date.today(),
        )
        cls.o_3 = OpinionFactory.create(
            cluster=cls.o_cluster_3,
            type=Opinion.COMBINED,
        )
        cls.o_3_1 = OpinionFactory.create(
            cluster=cls.o_cluster_3,
            type=Opinion.COMBINED,
        )
        cls.o_cluster_4 = OpinionClusterWithParentsFactory.create(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            citation_count=5,
            date_filed=datetime.date.today(),
        )
        cls.o_4 = OpinionFactory.create(
            cluster=cls.o_cluster_4,
            type=Opinion.COMBINED,
        )
        OpinionsCitedWithParentsFactory.create(
            cited_opinion=cls.o_3,
            citing_opinion=cls.o_1,
        )
        OpinionsCitedWithParentsFactory.create(
            cited_opinion=cls.o_3,
            citing_opinion=cls.o_2,
        )
        OpinionsCitedWithParentsFactory.create(
            cited_opinion=cls.o_3_1,
            citing_opinion=cls.o_4,
        )
        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    async def test_simple_opinion_page(self) -> None:
        """Does the page load properly?"""
        path = reverse(
            "view_case", kwargs={"pk": self.opinion_cluster_1.pk, "_": "asdf"}
        )
        response = await self.async_client.get(path)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("33 state 1", response.content.decode())

    async def test_es_get_citing_clusters_with_cache(self) -> None:
        """Does es_get_citing_and_related_clusters_with_cache return the
        correct clusters citing and the total cites count?
        """

        request = AsyncRequestFactory().get("/")
        result = await es_get_citing_and_related_clusters_with_cache(
            self.o_cluster_3, request
        )
        clusters = result.citing_clusters
        count = result.citing_cluster_count

        c_list_names = [c["caseName"] for c in clusters]
        expected_clusters = [
            self.o_cluster_1.case_name,
            self.o_cluster_2.case_name,
            self.o_cluster_4.case_name,
        ]
        # Compare expected clusters citing and total count.
        self.assertEqual(set(c_list_names), set(expected_clusters))
        self.assertEqual(count, len(expected_clusters))


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
        async_to_sync(add_docket_entries)(
            cls.docket, cls.de_data["docket_entries"]
        )

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
        async_to_sync(merge_attachment_page_data)(
            cls.court,
            cls.att_data["pacer_case_id"],
            cls.att_data["pacer_doc_id"],
            None,
            "",
            cls.att_data["attachments"],
        )

    async def test_redirect_to_attachment_page(self) -> None:
        """Does the page redirect to the attachment page?"""
        path = reverse(
            "view_recap_document",
            kwargs={
                "docket_id": self.docket.pk,
                "doc_num": 1,
                "slug": self.docket.slug,
            },
        )
        r = await self.async_client.get(path, follow=True)
        self.assertEqual(r.redirect_chain[0][1], HTTPStatus.FOUND)
        self.assertEqual(r.status_code, HTTPStatus.OK)


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

    async def test_citation_homepage(self) -> None:
        r = await self.async_client.get(reverse("citation_homepage"))
        self.assertStatus(r, HTTPStatus.OK)

    def test_with_a_citation(self) -> None:
        """Make sure that the url paths are working properly."""
        # Are we redirected to the correct place when we use GET or POST?
        r = self.client.get(
            reverse("citation_redirector", kwargs=self.citation), follow=True
        )
        self.assertEqual(r.redirect_chain[0][1], HTTPStatus.FOUND)

    async def test_multiple_results(self) -> None:
        """Do we return a 300 status code when there are multiple results?"""
        # Duplicate the citation and add it to another cluster instead.
        f2_cite = await Citation.objects.aget(**self.citation)
        f2_cite.pk = None
        f2_cite.cluster_id = 3
        await f2_cite.asave()

        self.citation["reporter"] = slugify_reporter(self.citation["reporter"])
        r = await self.async_client.get(
            reverse("citation_redirector", kwargs=self.citation)
        )
        self.assertStatus(r, HTTPStatus.MULTIPLE_CHOICES)
        # The page is displaying the expected message
        self.assertIn("Found More than One Result", r.content.decode())
        # the list of citations is showing the court names
        self.assertIn("Testing Supreme Court |", r.content.decode())

        # Test the search bar input
        r = await self.async_client.post(
            reverse("citation_homepage"),
            {"reporter": "56 F.2d 9 (1st Cir. 2015)"},
            follow=True,
        )
        self.assertStatus(r, HTTPStatus.MULTIPLE_CHOICES)
        # The page is displaying the expected message
        self.assertIn("Found More than One Result", r.content.decode())
        # the list of citations is showing the court names
        self.assertIn("Testing Supreme Court |", r.content.decode())

        await f2_cite.adelete()

    async def test_handle_ambiguous_reporter_variations(self) -> None:
        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    "reporter": "bailey",
                },
            ),
        )
        self.assertStatus(r, HTTPStatus.MULTIPLE_CHOICES)
        self.assertIn(
            "Found More Than One Possible Reporter", r.content.decode()
        )

    async def test_unknown_citation(self) -> None:
        """Do we get a 404 message if we don't know the citation?"""
        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    "reporter": "bad-reporter",
                    "volume": "1",
                    "page": "1",
                },
            ),
        )
        self.assertStatus(r, HTTPStatus.NOT_FOUND)

        # Test the search bar input
        r = await self.async_client.post(
            reverse("citation_homepage"),
            {"reporter": "1 bad-reporter 1"},
            follow=True,
        )
        self.assertStatus(r, HTTPStatus.BAD_REQUEST)
        self.assertIn("No Citations Detected", r.content.decode())

        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    "reporter": "Maryland Code, Criminal Law § 11-208",
                },
            ),
            follow=True,
        )
        self.assertStatus(r, HTTPStatus.NOT_FOUND)
        self.assertIn("Unable to Find Reporter", r.content.decode())

        # Test the search bar input
        r = await self.async_client.post(
            reverse("citation_homepage"),
            {"reporter": "Maryland Code, Criminal Law § 11-208"},
            follow=True,
        )
        self.assertStatus(r, HTTPStatus.BAD_REQUEST)
        self.assertIn("No Citations Detected", r.content.decode())

        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    "reporter": "§ 97-29-63",
                },
            ),
            follow=True,
        )
        self.assertStatus(r, HTTPStatus.NOT_FOUND)
        self.assertIn("Unable to Find Reporter", r.content.decode())

        # Test the search bar input
        r = await self.async_client.post(
            reverse("citation_homepage"),
            {"reporter": "§ 97-29-63"},
            follow=True,
        )
        self.assertStatus(r, HTTPStatus.BAD_REQUEST)
        self.assertIn("No Citations Detected", r.content.decode())

    async def test_invalid_page_number_1918(self) -> None:
        """Do we fail gracefully with invalid page numbers?"""
        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    "reporter": "f2d",
                    "volume": "1",
                    "page": "asdf",  # <-- Nasty, nasty hobbits
                },
            ),
        )
        self.assertStatus(r, HTTPStatus.NOT_FOUND)

    async def test_long_numbers(self) -> None:
        """Do really long WL citations work?"""
        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "wl", "volume": "2012", "page": "2995064"},
            ),
        )
        self.assertStatus(r, HTTPStatus.NOT_FOUND)

    async def test_volume_page(self) -> None:
        r = await self.async_client.get(
            reverse("citation_redirector", kwargs={"reporter": "f2d"})
        )
        self.assertStatus(r, HTTPStatus.OK)

    async def test_case_page(self) -> None:
        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "f2d", "volume": "56"},
            )
        )
        self.assertStatus(r, HTTPStatus.OK)

    async def test_handle_volume_pagination_properly(self) -> None:
        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "f2d", "volume": "56"},
            ),
            {"page": 0},
        )
        self.assertStatus(r, HTTPStatus.OK)
        self.assertEqual(r.context["cases"].number, 1)

        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "f2d", "volume": "56"},
            ),
            {"page": "a"},
        )
        self.assertStatus(r, HTTPStatus.OK)
        self.assertEqual(r.context["cases"].number, 1)

    async def test_link_to_page_in_citation(self) -> None:
        """Test link to page with star pagination"""
        # Here opinion cluster 2 has the citation 56 F.2d 9, but the
        # HTML with citations contains star pagination for pages 9 and 10.
        # This tests if we can find opinion cluster 2 with page 9 and 10
        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "f2d", "volume": "56", "page": "9"},
            )
        )
        self.assertEqual(r.url, "/opinion/2/case-name-cluster/")

        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "f2d", "volume": "56", "page": "10"},
            )
        )
        self.assertEqual(r.url, "/opinion/2/case-name-cluster/")

    async def test_slugifying_reporters(self) -> None:
        """Test reporter slugification"""
        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={"reporter": "F.2d", "volume": "56", "page": "9"},
            )
        )
        self.assertEqual(r.url, "/c/f2d/56/9/")

    async def test_slugifying_reporters_collision(self) -> None:
        """Test reporter collision-aware slugification"""
        test_pairs = [("Vt.", "VT"), ("La.", "LA"), ("MSPB", "M.S.P.B.")]
        for r1, r2 in test_pairs:
            response1 = await self.async_client.get(
                reverse(
                    "citation_redirector",
                    kwargs={"reporter": r1},
                )
            )
            response2 = await self.async_client.get(
                reverse(
                    "citation_redirector",
                    kwargs={"reporter": r2},
                )
            )
            self.assertNotEqual(response1.url, response2.url)

    async def test_reporter_variation_just_reporter(self) -> None:
        """Do we redirect properly when we get reporter variations?"""
        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    # Introduce a space (slugified to a dash) into the reporter
                    "reporter": "f-2d",
                },
            )
        )
        self.assertEqual(r.status_code, HTTPStatus.FOUND)
        self.assertEqual(r.url, "/c/f2d/")

    async def test_reporter_variation_just_reporter_and_volume(self) -> None:
        """Do we redirect properly when we get reporter variations?"""
        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    # Introduce a space (slugified to a dash) into the reporter
                    "reporter": "f-2d",
                    "volume": "56",
                },
            )
        )
        self.assertEqual(r.status_code, HTTPStatus.FOUND)
        self.assertEqual(r.url, "/c/f2d/56/")

    async def test_reporter_variation_full_citation(self) -> None:
        """Do we redirect properly when we get reporter variations?"""
        r = await self.async_client.get(
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
        self.assertEqual(r.status_code, HTTPStatus.FOUND)
        self.assertEqual(r.url, "/c/f2d/56/9/")

    async def test_volume_pagination(self) -> None:
        """Can we properly paginate reporter volume numbers?"""

        # Create test data usign factories
        test_obj = await sync_to_async(CitationWithParentsFactory.create)(
            volume="2016",
            reporter="COA",
            page="1",
            cluster=await sync_to_async(
                OpinionClusterWithChildrenAndParentsFactory
            )(
                docket=await sync_to_async(DocketFactory)(
                    court=await sync_to_async(CourtFactory)(id="coloctapp")
                ),
                case_name="In re the Marriage of Morton",
                date_filed=datetime.date(2016, 1, 14),
            ),
        )

        await sync_to_async(CitationWithParentsFactory.create)(
            volume="2017",
            reporter="COA",
            page="3",
            cluster=await sync_to_async(
                OpinionClusterWithChildrenAndParentsFactory
            )(
                docket=await sync_to_async(DocketFactory)(
                    court=await sync_to_async(CourtFactory)(id="coloctapp")
                ),
                case_name="Begley v. Ireson",
                date_filed=datetime.date(2017, 1, 12),
            ),
        )

        await sync_to_async(CitationWithParentsFactory.create)(
            volume="2018",
            reporter="COA",
            page="1",
            cluster=await sync_to_async(
                OpinionClusterWithChildrenAndParentsFactory
            )(
                docket=await sync_to_async(DocketFactory)(
                    court=await sync_to_async(CourtFactory)(id="coloctapp")
                ),
                case_name="People v. Sparks",
                date_filed=datetime.date(2018, 1, 11),
            ),
        )

        await sync_to_async(CitationWithParentsFactory.create)(
            volume="2018",
            reporter="COA",
            page="1",
            cluster=await sync_to_async(
                OpinionClusterWithChildrenAndParentsFactory
            )(
                docket=await sync_to_async(DocketFactory)(
                    court=await sync_to_async(CourtFactory)(id="coloctapp")
                ),
                case_name="People v. Sparks",
                date_filed=datetime.date(2018, 1, 11),
            ),
        )

        # Get previous and next volume for "2017 COA"
        volume_next, volume_previous = await get_prev_next_volumes(
            "COA", "2017"
        )
        self.assertEqual(volume_previous, 2016)
        self.assertEqual(volume_next, 2018)

        # Delete previous
        await test_obj.adelete()

        # Only get next volume for "2017 COA"
        volume_next, volume_previous = await get_prev_next_volumes(
            "COA", "2017"
        )
        self.assertEqual(volume_previous, None)
        self.assertEqual(volume_next, 2018)

        # Create new test data
        await sync_to_async(CitationWithParentsFactory.create)(
            volume="454",
            reporter="U.S.",
            page="1",
            cluster=await sync_to_async(
                OpinionClusterWithChildrenAndParentsFactory
            )(
                docket=await sync_to_async(DocketFactory)(
                    court=await sync_to_async(CourtFactory)(id="scotus")
                ),
                case_name="Duckworth v. Serrano",
                date_filed=datetime.date(1981, 10, 19),
            ),
        )

        # No next or previous volume for "454 U.S."
        volume_next, volume_previous = await get_prev_next_volumes(
            "U.S.", "454"
        )
        self.assertEqual(volume_previous, None)
        self.assertEqual(volume_next, None)

    def test_full_citation_redirect(self) -> None:
        """Do we get redirected to the correct URL when we pass in a full
        citation?"""
        r = self.client.post(
            reverse("citation_homepage"),
            {
                "reporter": "Reference to Lissner v. Saad, 56 F.2d 9 11 (1st Cir. 2015)",
            },
            follow=True,
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(r, "opinions.html")
        self.assertEqual(
            r.context["cluster"].get_absolute_url(),
            "/opinion/2/case-name-cluster/",
        )

    async def test_avoid_exception_possible_matches_page_with_letter(
        self,
    ) -> None:
        """Can we order the possible matches when page number contains a
        letter without getting a DataError exception?"""

        # See: freelawproject/courtlistener#2474

        # Create the citation that contains 40M as page number and was
        # causing the exception
        cf = await sync_to_async(CourtFactory)(id="coloctapp")
        df = await sync_to_async(DocketFactory)(court=cf)
        await sync_to_async(CitationWithParentsFactory.create)(
            volume="2017",
            reporter="COA",
            page="40M",
            cluster=await sync_to_async(
                OpinionClusterWithChildrenAndParentsFactory
            )(
                docket=df,
                case_name="People v. Davis",
                date_filed=datetime.date(2017, 5, 4),
            ),
        )

        r = await self.async_client.get(
            reverse(
                "citation_redirector",
                kwargs={
                    "reporter": "coa",
                    "volume": "2017",
                    "page": "157",
                },
            ),
        )
        self.assertStatus(r, HTTPStatus.NOT_FOUND)

    async def test_can_handle_text_with_slashes(self):
        r = await self.async_client.post(
            reverse("citation_homepage"),
            {"reporter": "ARB/11/20/"},
            follow=True,
        )
        self.assertTemplateUsed(r, "volumes_for_reporter.html")
        self.assertIn("No Citations Detected", r.content.decode())
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

        r = await self.async_client.post(
            reverse("citation_homepage"),
            {
                "reporter": "https://dockets.justia.com/docket/circuit-courts/ca5/20-10820"
            },
            follow=True,
        )
        self.assertTemplateUsed(r, "volumes_for_reporter.html")
        self.assertIn("No Citations Detected", r.content.decode())
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

    async def test_can_filter_out_non_case_law_citation(self):
        chests_of_tea = await sync_to_async(CitationWithParentsFactory.create)(
            volume=22, reporter="U.S.", page="444", type=1
        )
        r = await self.async_client.post(
            reverse("citation_homepage"),
            {
                "reporter": "§102 USC 222 is the statute that was discussed in 22 U.S. 444"
            },
            follow=True,
        )

        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertTemplateUsed(r, "opinions.html")
        self.assertIn(str(chests_of_tea), r.content.decode())

    async def test_show_error_for_non_opinion_citations(self):
        r = await self.async_client.post(
            reverse("citation_homepage"),
            {"reporter": "44 Vand. L. Rev. 1041"},
            follow=True,
        )

        self.assertIn("No Citations Detected", r.content.decode())
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)


class ViewRecapDocketTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.docket = DocketFactory(
            court=cls.court,
            source=Docket.RECAP,
        )
        cls.de_1 = DocketEntryFactory(
            docket=cls.docket,
            entry_number=11,
            date_filed=date(2025, 1, 15),
            description="Lorem ipsum description.",
        )
        cls.de_2 = DocketEntryFactory(
            docket=cls.docket,
            entry_number=11,
            date_filed=date(2025, 1, 17),
            description="Entry outside the range.",
        )
        RECAPDocumentFactory(
            docket_entry=cls.de_1,
            pacer_doc_id="005065812111",
            document_number="005065281111",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        cls.court_appellate = CourtFactory(id="ca1", jurisdiction="F")
        cls.docket_appellate = DocketFactory(
            court=cls.court_appellate,
            source=Docket.RECAP,
        )

    async def test_regular_docket_url(self) -> None:
        """Can we load a regular docket sheet?"""
        r = await self.async_client.get(
            reverse("view_docket", args=[self.docket.pk, self.docket.slug])
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)

    async def test_recap_docket_url(self) -> None:
        """Can we redirect to a regular docket URL from a recap/uscourts.*
        URL?
        """
        r = await self.async_client.get(
            reverse(
                "redirect_docket_recap",
                kwargs={
                    "court": self.court.pk,
                    "pacer_case_id": self.docket.pacer_case_id,
                },
            ),
            follow=True,
        )
        self.assertEqual(r.redirect_chain[0][1], HTTPStatus.FOUND)

    async def test_pagination_returns_last_page_if_page_out_of_range(self):
        """
        Verify that the Docket view handles out-of-range page requests by returning
        the last valid page.
        """
        entries = DocketEntriesDataFactory(
            docket_entries=DocketEntryDataFactory.create_batch(50)
        )
        await add_docket_entries(self.docket, entries["docket_entries"])
        response = await self.async_client.get(
            reverse("view_docket", args=[self.docket.pk, self.docket.slug]),
            {"page": 0},
        )

        self.assertEqual(
            response.context["docket_entries"].number,
            response.context["docket_entries"].paginator.num_pages,
        )

    async def test_recap_docket_entry_filed_filter(self) -> None:
        """Can we properly filter docket entries by date filed?"""
        params = {
            "filed_after": "01/15/2025",
            "filed_before": "01/16/2025",
            "order_by": "asc",
        }
        url = reverse("view_docket", args=[self.docket.pk, self.docket.slug])
        r = await self.async_client.get(url, query_params=params)
        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertIn(self.de_1.description, r.content.decode())
        self.assertNotIn(self.de_2.description, r.content.decode())

    async def test_recap_docket_invalid_entry_filed_filter(self) -> None:
        """Confirm that invalid date values in the docket entry filed filter
        produce a validation error for users.
        """
        params = {
            "filed_after": "02/10/2025",
            "filed_before": ".",
            "order_by": "asc",
        }
        url = reverse("view_docket", args=[self.docket.pk, self.docket.slug])
        r = await self.async_client.get(url, query_params=params)
        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertIn(
            "There were errors applying your filters", r.content.decode()
        )


class OgRedirectLookupViewTest(TestCase):
    fixtures = ["recap_docs.json"]

    def setUp(self) -> None:
        self.async_client = AsyncClient()
        self.url = reverse("redirect_og_lookup")

    async def test_do_we_404_no_param(self) -> None:
        """Does the view return 404 when no parameters given?"""
        r = await self.async_client.get(self.url)
        self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)

    async def test_unknown_doc(self) -> None:
        """Do we redirect to S3 when unknown file path?"""
        r = await self.async_client.get(self.url, {"file_path": "xxx"})
        self.assertEqual(r.status_code, HTTPStatus.FOUND)

    @mock.patch("cl.opinion_page.views.make_png_thumbnail_for_instance")
    async def test_success_goes_to_view(self, mock: MagicMock) -> None:
        path = (
            "recap/dev.gov.uscourts.txnd.28766/gov.uscourts.txnd.28766.1.0.pdf"
        )
        r = await self.async_client.get(
            self.url, {"file_path": path}, USER_AGENT="facebookexternalhit"
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        mock.assert_called_once()

    @mock.patch("cl.lib.thumbnails.microservice")
    async def test_creates_thumbnail_successfully(
        self, microservice_mock: MagicMock
    ) -> None:
        path = (
            "recap/dev.gov.uscourts.txnd.28766/gov.uscourts.txnd.28766.1.0.pdf"
        )

        # Create a fake response object
        response_mock = MagicMock()
        type(response_mock).is_success = PropertyMock(return_value=True)
        type(response_mock).content = PropertyMock(return_value=fake.binary(8))

        microservice_mock.return_value = response_mock

        r = await self.async_client.get(
            self.url, {"file_path": path}, USER_AGENT="facebookexternalhit"
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        microservice_mock.assert_called_once()

        recap_doc = await RECAPDocument.objects.aget(pk=1)
        self.assertEqual(
            recap_doc.thumbnail_status, THUMBNAIL_STATUSES.COMPLETE
        )


class NewDocketAlertTest(SimpleUserDataMixin, TestCase):
    fixtures = [
        "test_objects_search.json",
        "judge_judy.json",
        "test_court.json",
    ]

    @async_to_sync
    async def setUp(self) -> None:
        self.assertTrue(
            await self.async_client.alogin(
                username="pandora", password="password"
            )
        )

    async def test_bad_parameters(self) -> None:
        """If we omit the pacer_case_id and court_id params, do things fail?"""
        r = await self.async_client.get(reverse("new_docket_alert"))
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)

    async def test_unknown_docket(self) -> None:
        """What happens if no docket?"""
        r = await self.async_client.get(
            reverse("new_docket_alert"),
            data={"pacer_case_id": "blah", "court_id": "blah"},
        )
        self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)
        self.assertIn("Refresh this Page", r.content.decode())

    async def test_all_systems_go(self) -> None:
        """Does everything work with good parameters and good data?"""
        r = await self.async_client.get(
            reverse("new_docket_alert"),
            data={"pacer_case_id": "666666", "court_id": "test"},
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertInHTML("Get Docket Alerts", r.content.decode())


class OpinionSitemapTest(SitemapMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
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
        super().setUp()
        self.sitemap_url = reverse(
            "sitemaps", kwargs={"section": SEARCH_TYPES.OPINION}
        )
        self.expected_item_count = 2

    def test_does_the_sitemap_have_content(self) -> None:
        super().assert_sitemap_has_content()


class DocketSitemapTest(SitemapMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
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
        super().setUp()
        self.setUpSiteDomain()

        self.sitemap_url = reverse(
            "sitemaps-pregenerated", kwargs={"section": SEARCH_TYPES.RECAP}
        )
        self.expected_item_count = 2

    def test_is_the_sitemap_generated_and_have_content(self) -> None:
        """Is content generated and read properly from the cache into the sitemap?"""

        with self.assertRaises(
            NotImplementedError,
            msg="Did not get a NotImplementedError exception before generating the sitemap.",
        ):
            _ = self.client.get(self.sitemap_url)

        generate_urls_chunk()

        response = self.client.get(self.sitemap_url)
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get a 200 OK status code after generating the sitemap.",
        )

    def test_does_the_sitemap_have_content(self) -> None:
        generate_urls_chunk()
        super().assert_sitemap_has_content()


class DocketEmptySitemapTest(SitemapMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Excluded b/c old
        DocketFactory.create(
            source=Docket.RECAP,
            blocked=False,
            view_count=0,
            date_filed=datetime.date.today() - datetime.timedelta(days=60),
        )
        # Excluded b/c blocked
        DocketFactory.create(
            source=Docket.RECAP,
            blocked=True,
            view_count=50,
            date_filed=datetime.date.today(),
        )
        DocketFactory.create(
            source=Docket.RECAP,
            blocked=True,
        )

    def setUp(self) -> None:
        super().setUp()
        self.setUpSiteDomain()

        self.sitemap_url = reverse(
            "sitemaps-pregenerated", kwargs={"section": SEARCH_TYPES.RECAP}
        )

    def test_is_the_sitemap_generated_and_have_content(self) -> None:
        """Is content generated and read properly from the cache into the sitemap?"""

        with self.assertRaises(
            NotImplementedError,
            msg="Did not get a NotImplementedError exception before generating the sitemap.",
        ):
            _ = self.client.get(self.sitemap_url)

        generate_urls_chunk()

        response = self.client.get(self.sitemap_url)
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get a 200 OK status code after generating the sitemap.",
        )


class BlockedSitemapTest(SitemapMixin, TestCase):
    """Do we create sitemaps of recently blocked opinions?"""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
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
        super().setUp()
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
        court_mo = CourtFactory.create(id="mo")
        court_miss = CourtFactory.create(id="miss")
        court_me = CourtFactory.create(id="me")

        # Create judges
        people = PersonFactory.create_batch(4)
        for person in people[:3]:
            PositionFactory.create(court=court_app, person=person)
        PositionFactory.create(court=court_cl, person=people[3])
        people_me = PersonFactory.create_batch(3)
        for person in people_me:
            PositionFactory.create(
                court=court_me, person=person, position_type="c-jus"
            )
        PersonWithChildrenFactory(
            positions=RelatedFactory(
                PositionFactory, factory_related_name="person", court=court_mo
            )
        )
        PersonWithChildrenFactory(
            positions=RelatedFactory(
                PositionFactory,
                factory_related_name="person",
                court=court_miss,
            )
        )

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
        self.async_client = AsyncClient()

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

        self.me_data = {
            "case_title": "A Sample Case",
            "docket_number": "Pen-23-123",
            "court_str": "me",
            "pk": "me",
            "date_argued": datetime.date(2024, 5, 12),
            "date_reargued": datetime.date(2024, 6, 12),
            "author_str": "Sample",
            "publication_date": datetime.date(2024, 4, 12),
            "cite_volume": "2024",
            "cite_reporter": "ME",
            "cite_page": "1",
            "panel": Person.objects.filter(
                positions__court_id="me"
            ).values_list("pk", flat=True),
        }

        # mo and moctapp have the same fields
        self.mo_data = {
            "lead_author": Person.objects.filter(positions__court_id="mo")[
                0
            ].id,
            "case_title": "A Sample Case",
            "docket_number": "SC123456",
            "court_str": "mo",
            "pk": "mo",
            "disposition": "Lorem ipsum dolor sit amet",
            "author_str": "Sample",
            "publication_date": datetime.date(2024, 6, 12),
        }

        # miss and missctapp have the same fields
        self.miss_data = {
            "lead_author": Person.objects.filter(positions__court_id="miss")[
                0
            ].id,
            "case_title": "A Sample Case",
            "docket_number": "2021-CT-123456-SCT",
            "court_str": "miss",
            "pk": "miss",
            "disposition": "Lorem ipsum dolor sit amet",
            "summary": "Lorem ipsum dolor sit amet",
            "author_str": "Sample",
            "publication_date": datetime.date(2024, 6, 12),
        }

    def tearDown(self) -> None:
        if os.path.exists(os.path.join(settings.MEDIA_ROOT, "pdf/2019/")):
            shutil.rmtree(os.path.join(settings.MEDIA_ROOT, "pdf/2019/"))
        Docket.objects.all().delete()

    async def test_access_upload_page(self, mock) -> None:
        """Can we successfully access upload page with access?"""
        await self.async_client.alogin(username="learned", password="password")
        response = await self.async_client.get(
            reverse("court_publish_page", args=["tennworkcompcl"])
        )
        self.assertEqual(response.status_code, 200)

    async def test_redirect_without_access(self, mock) -> None:
        """Can we successfully redirect individuals without proper access?"""
        await self.async_client.alogin(
            username="test_user", password="password"
        )
        response = await self.async_client.get(
            reverse("court_publish_page", args=["tennworkcompcl"])
        )
        self.assertEqual(response.status_code, 302)

    def test_pdf_upload(self, mock) -> None:
        """Can we upload a PDF and form?"""
        form = TennWorkCompClUploadForm(
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

        self.assertEqual(form.is_valid(), True, msg=form.errors)

        if form.is_valid():
            form.save()

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
        form = TennWorkCompClUploadForm(
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
        form = TennWorkCompAppUploadForm(
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
        self.assertEqual(form.is_valid(), True, msg=form.errors)

        if form.is_valid():
            form.save()

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

        form = TennWorkCompAppUploadForm(
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

        form = TennWorkCompAppUploadForm(
            self.work_comp_app_data,
            pk="tennworkcompapp",
            files={"pdf_upload": self.pdf},
        )
        qs = Person.objects.filter(positions__court_id="tennworkcompapp")
        form.fields["lead_author"].queryset = qs
        form.fields["second_judge"].queryset = qs
        form.fields["third_judge"].queryset = qs

        self.assertEqual(form.is_valid(), True, msg=form.errors)

        if form.is_valid():
            form.save()

        self.assertEqual(pre_count + 1, Opinion.objects.all().count())

    def test_me_form_save(self, mock) -> None:
        """Can we save maine form successfully to db?"""

        pre_count = Opinion.objects.all().count()

        form = MeCourtUploadForm(
            self.me_data,
            pk="me",
            files={"pdf_upload": self.pdf},
        )

        self.assertEqual(form.is_valid(), True, msg=form.errors)

        if form.is_valid():
            form.save()

        self.assertEqual(pre_count + 1, Opinion.objects.all().count())

    def test_mo_form_save(self, mock) -> None:
        """Can we save missouri form successfully to db?"""

        pre_count = Opinion.objects.filter(
            cluster__docket__court__id="mo"
        ).count()

        form = MoCourtUploadForm(
            self.mo_data,
            pk="mo",
            files={"pdf_upload": self.pdf},
        )

        self.assertEqual(form.is_valid(), True, msg=form.errors)

        if form.is_valid():
            form.save()

        post_save_count = Opinion.objects.filter(
            cluster__docket__court__id="mo"
        ).count()
        self.assertEqual(pre_count + 1, post_save_count)

    def test_miss_form_save(self, mock) -> None:
        """Can we save mississippi form successfully to db?"""

        pre_count = Opinion.objects.filter(
            cluster__docket__court__id="miss"
        ).count()

        form = MissCourtUploadForm(
            self.miss_data,
            pk="miss",
            files={"pdf_upload": self.pdf},
        )

        self.assertEqual(form.is_valid(), True, msg=form.errors)

        if form.is_valid():
            form.save()

        post_save_count = Opinion.objects.filter(
            cluster__docket__court__id="miss"
        ).count()
        self.assertEqual(pre_count + 1, post_save_count)

    def test_form_two_judges_2042(self, mock) -> None:
        """Can we still save if there's only one or two judges on the panel?"""
        pre_count = Opinion.objects.all().count()

        # Remove a judge from the data
        self.work_comp_app_data["third_judge"] = None

        form = TennWorkCompAppUploadForm(
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

        form2 = TennWorkCompClUploadForm(
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


class TestBlockSearchItemAjax(TestCase):
    @classmethod
    def setUpTestData(cls):
        # User admin
        cls.admin = UserProfileWithParentsFactory.create(
            user__username="admin",
            user__password=make_password("password"),
        )
        cls.admin.user.is_superuser = True
        cls.admin.user.is_staff = True
        cls.admin.user.save()

        # Courts
        court_ca2 = CourtFactory(id="ca2")
        # cluster
        cls.cluster = OpinionClusterWithChildrenAndParentsFactory(
            docket=DocketFactory(court=court_ca2),
            case_name="Fisher v. SD Protection Inc.",
            date_filed=date(2020, 1, 1),
        )

    async def test_return_404_for_invalid_type(self) -> None:
        """is it returning 404 for invalid types?"""
        self.assertFalse(self.cluster.blocked)
        self.assertFalse(self.cluster.docket.blocked)

        client = AsyncClient()
        await client.aforce_login(user=self.admin.user)

        response = await client.post(
            reverse("block_item"),
            data={"id": self.cluster.pk, "type": "recap"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 400)

    async def test_block_docket_via_ajax_view(self) -> None:
        """can a super_user block a docket?"""
        self.assertFalse(self.cluster.docket.blocked)

        client = AsyncClient()
        await client.aforce_login(user=self.admin.user)

        response = await client.post(
            reverse("block_item"),
            data={"id": self.cluster.docket.pk, "type": "docket"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)

        await self.cluster.docket.arefresh_from_db()
        self.assertTrue(self.cluster.docket.blocked)

    async def test_block_cluster_and_docket_via_ajax_view(self) -> None:
        """can a super_user block an opinion cluster?"""
        self.assertFalse(self.cluster.blocked)
        self.assertFalse(self.cluster.docket.blocked)

        client = AsyncClient()
        await client.aforce_login(user=self.admin.user)

        response = await client.post(
            reverse("block_item"),
            data={"id": self.cluster.pk, "type": "cluster"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        self.assertEqual(response.status_code, 200)

        await self.cluster.docket.arefresh_from_db()
        self.assertTrue(self.cluster.docket.blocked)

        await self.cluster.arefresh_from_db()
        self.assertTrue(self.cluster.blocked)


class DocketEntryFileDownload(TestCase):
    """Test Docket entries File Download and required functions."""

    def setUp(self):
        court = CourtFactory(id="ca5", jurisdiction="F")
        # Main docket to test
        docket = DocketFactory(
            court=court,
            case_name="Foo v. Bar",
            docket_number="12-11111",
            pacer_case_id="12345",
        )

        de1 = DocketEntryFactory(
            docket=docket,
            entry_number=506581111,
        )
        RECAPDocumentFactory(
            docket_entry=de1,
            pacer_doc_id="00506581111",
            document_number="00506581111",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        de1_2 = DocketEntryFactory(
            docket=docket,
            entry_number=1,
        )
        RECAPDocumentFactory(
            docket_entry=de1_2,
            pacer_doc_id="00506581111",
            document_number="1",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        de2 = DocketEntryFactory(
            docket=docket,
            entry_number=2,
            description="Lorem ipsum dolor sit amet",
        )
        RECAPDocumentFactory(
            docket_entry=de2,
            pacer_doc_id="",
            document_number="2",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )

        de3 = DocketEntryFactory(
            docket=docket,
            entry_number=506582222,
        )
        RECAPDocumentFactory(
            docket_entry=de3,
            pacer_doc_id="00506582222",
            document_number="3",
            document_type=RECAPDocument.ATTACHMENT,
            attachment_number=1,
        )
        RECAPDocumentFactory(
            docket_entry=de3,
            description="Document attachment",
            document_type=RECAPDocument.ATTACHMENT,
            document_number="3",
            attachment_number=2,
        )
        # Create extra docket and docket entries to make sure it only fetch
        # required docket_entries
        docket1 = DocketFactory(
            court=court,
            case_name="Test v. Test1",
            docket_number="12-222222",
            pacer_case_id="12345",
        )
        de4 = DocketEntryFactory(
            docket=docket1,
            entry_number=506582222,
        )
        RECAPDocumentFactory(
            docket_entry=de4,
            pacer_doc_id="00506582222",
            document_number="005506582222",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        self.mocked_docket = docket
        self.mocked_extra_docket = docket1
        self.mocked_docket_entries = [de1, de1_2, de2, de3]
        self.mocked_extra_docket_entries = [de4]

        request_factory = RequestFactory()
        self.request = request_factory.get("/mock-url/")
        self.user = UserFactory.create(
            username="learned",
            email="learnedhand@scotus.gov",
        )
        self.request.auser = AsyncMock(return_value=self.user)

    def tearDown(self):
        # Clear all test data
        Docket.objects.all().delete()
        DocketEntry.objects.all().delete()
        RECAPDocument.objects.all().delete()
        User.objects.all().delete()

    async def test_fetch_docket_entries(self) -> None:
        """Verify that fetch entries function returns right docket_entries"""
        res = await fetch_docket_entries(self.mocked_docket)
        self.assertEqual(await res.acount(), len(self.mocked_docket_entries))
        self.assertTrue(await res.acontains(self.mocked_docket_entries[0]))
        self.assertFalse(
            await res.acontains(self.mocked_extra_docket_entries[0])
        )

    def test_generate_docket_entries_csv_data(self) -> None:
        """Verify str with csv data is created. Check column and data entry"""
        res = generate_docket_entries_csv_data(self.mocked_docket_entries)
        res_lines = res.split("\r\n")
        res_line_data = res_lines[1].split(",")
        self.assertEqual(res[:16], '"docketentry_id"')
        self.assertEqual(res_line_data[1], '"506581111"')

        # Checks if the number of values in each CSV row matches the expected
        # number of columns.

        # Compute the expected number of columns by combining the columns from
        # the docket entry and recap documents
        docket_entry = self.mocked_docket_entries[0]
        de_columns = docket_entry.get_csv_columns(get_column_name=True)
        rd_columns = docket_entry.recap_documents.first().get_csv_columns(
            get_column_name=True
        )
        column_count = len(de_columns + rd_columns)

        # Iterate over each line in the generated CSV data and count the number
        # of values.
        rows = [
            len(re.findall('"([^"]*)"', line)) == column_count
            for line in res_lines
            if line
        ]
        # Assert that all rows have the expected number of values.
        self.assertTrue(
            all(rows),
            "One or more rows of the CSV file has more values than expected",
        )

    @mock.patch("cl.opinion_page.utils.user_has_alert")
    @mock.patch("cl.opinion_page.utils.core_docket_data")
    @mock.patch("cl.opinion_page.utils.generate_docket_entries_csv_data")
    def test_view_download_docket_entries_csv(
        self,
        mock_download_function,
        mock_core_docket_data,
        mock_user_has_alert,
    ) -> None:
        """Test download_docket_entries_csv returns csv content"""

        mock_download_function.return_value = (
            '"col1","col2","col3"\r\n"value1","value2","value3"'
        )
        mock_user_has_alert.return_value = False
        mock_core_docket_data.return_value = (
            self.mocked_docket,
            {
                "docket": self.mocked_docket,
                "title": "title",
                "note_form": "note_form",
                "has_alert": mock_user_has_alert.return_value,
                "timezone": "EST",
                "private": True,
            },
        )
        response = download_docket_entries_csv(
            self.request, self.mocked_docket.id
        )
        self.assertEqual(response["Content-Type"], "text/csv")


class CachePageIgnoreParamsTest(TestCase):
    """Test the cache_page_ignore_params decorator."""

    @classmethod
    def setUpTestData(cls):
        court = CourtFactory(id="ca5", jurisdiction="F")
        cls.docket = DocketFactory(
            court=court,
            case_name="Foo v. Bar",
            docket_number="12-11111",
            pacer_case_id="12345",
        )

    def setUp(self):
        r = get_redis_interface("CACHE")
        keys_to_delete = r.keys(":1:custom.views.decorator.cache*")
        if keys_to_delete:
            r.delete(*keys_to_delete)

    def test_cache_view_docket_feed(self) -> None:
        """Confirm that cache_page_ignore_params can cache a view while ignoring
        the GET params from the URL.
        """

        base_url = reverse(
            "docket_feed",
            kwargs={"docket_id": self.docket.id},
        )

        # Request docket/<int:docket_id>/feed/
        # Response returned from DB.
        with CaptureQueriesContext(connection) as queries:
            response = async_to_sync(self.async_client.get)(base_url)
            self.assertGreater(
                len(queries), 0, "Expected more than 0 queries."
            )
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get 200 OK status code for podcasts.",
        )

        # Request docket/<int:docket_id>/feed/?ts=12345
        # Response returned from cache.
        with CaptureQueriesContext(connection) as queries:
            response = async_to_sync(self.async_client.get)(
                base_url, {"ts": 12345}
            )
            self.assertEqual(
                len(queries), 0, "Expected 0 queries for cached response."
            )
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get 200 OK status code for podcasts.",
        )
        self.assertIn("Cache-Control", response.headers)
        self.assertEqual(response.headers["Cache-Control"], "max-age=300")
        self.assertIn("Expires", response.headers)
        self.assertIn(self.docket.case_name, response.content.decode())
