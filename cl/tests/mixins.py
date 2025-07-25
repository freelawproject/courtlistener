import re
from collections.abc import Sized
from datetime import date, datetime
from typing import cast
from urllib.parse import parse_qs, urlparse

from asgiref.sync import sync_to_async
from django.apps import apps
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.dateformat import format
from django.utils.html import strip_tags
from lxml import etree, html
from lxml.html import HtmlElement
from rest_framework.utils.serializer_helpers import ReturnList

from cl.alerts.management.commands.cl_send_scheduled_alerts import (
    get_cut_off_date,
)
from cl.audio.factories import AudioFactory
from cl.audio.models import Audio
from cl.lib.redis_utils import get_redis_interface
from cl.people_db.factories import (
    ABARatingFactory,
    AttorneyFactory,
    AttorneyOrganizationFactory,
    EducationFactory,
    PartyFactory,
    PartyTypeFactory,
    PersonFactory,
    PoliticalAffiliationFactory,
    PositionFactory,
    SchoolFactory,
)
from cl.people_db.models import Race
from cl.search.factories import (
    CitationWithParentsFactory,
    CourtFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionFactory,
    OpinionsCitedByRECAPDocument,
    OpinionsCitedWithParentsFactory,
    RECAPDocumentFactory,
)
from cl.search.models import SEARCH_TYPES, Docket, RECAPDocument
from cl.users.factories import UserFactory, UserProfileWithParentsFactory


class RestartRateLimitMixin:
    """Restart the rate limiter counter to avoid getting blocked in frontend
    after tests.
    """

    @classmethod
    def restart_rate_limit(cls):
        r = get_redis_interface("CACHE")
        keys = r.keys(":1:rl:*")
        if keys:
            r.delete(*keys)

    @classmethod
    def tearDownClass(cls):
        cls.restart_rate_limit()
        super().tearDownClass()


class SimpleUserDataMixin:
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()  # type: ignore
        UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )


class CountESTasksMixin:
    def setUp(self):
        super().setUp()
        self.task_call_count = 0

    def count_task_calls(
        self, task, immutable_signature, *args, **kwargs
    ) -> None:
        """Wraps the task to count its calls and assert the expected count."""
        # Increment the call count
        self.task_call_count += 1
        # Call the task
        if immutable_signature:
            return task.s(*args, **kwargs)
        else:
            task.apply_async(args=args, kwargs=kwargs)

    def reset_and_assert_task_count(self, expected) -> None:
        """Resets the task call count and asserts the expected number of calls."""

        assert self.task_call_count == expected, (
            f"Expected {expected} task calls, but got {self.task_call_count}"
        )
        self.task_call_count = 0


class PrayAndPayMixin:
    """Pray And Pay test case factories"""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.user = UserFactory()
        cls.user_2 = UserFactory()
        cls.user_3 = UserFactory()

        # Create profile for test user records
        UserProfileWithParentsFactory(user=cls.user)
        UserProfileWithParentsFactory(user=cls.user_2)
        UserProfileWithParentsFactory(user=cls.user_3)

        cls.rd_1 = RECAPDocumentFactory(
            pacer_doc_id="98763421",
            document_number="1",
            is_available=True,
        )
        cls.rd_2 = RECAPDocumentFactory(
            pacer_doc_id="98763422",
            document_number="2",
            is_available=False,
        )

        cls.rd_3 = RECAPDocumentFactory(
            pacer_doc_id="98763423",
            document_number="3",
            is_available=False,
        )
        cls.rd_4 = RECAPDocumentFactory(
            pacer_doc_id="98763424",
            document_number="4",
            is_available=False,
        )

        cls.rd_5 = RECAPDocumentFactory(
            pacer_doc_id="98763425",
            document_number="5",
            is_available=False,
        )

        cls.rd_6 = RECAPDocumentFactory(
            pacer_doc_id="98763426",
            document_number="6",
            is_available=False,
        )


class CourtMixin:
    """Court test case factories"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.court_1 = CourtFactory(
            id="ca1",
            full_name="First Circuit",
            jurisdiction="F",
            citation_string="1st Cir.",
            url="https://www.ca1.uscourts.gov/",
        )
        cls.court_2 = CourtFactory(
            id="test",
            full_name="Testing Supreme Court",
            jurisdiction="F",
            citation_string="Test",
            url="https://www.courtlistener.com/",
        )


class PeopleMixin(CourtMixin):
    """People test case factories"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.w_race, _ = Race.objects.get_or_create(race="w")
        cls.b_race, _ = Race.objects.get_or_create(race="b")
        cls.person_1 = PersonFactory.create(
            gender="m",
            name_first="Bill",
            name_last="Clinton",
        )
        cls.person_1.race.add(cls.w_race)

        cls.person_2 = PersonFactory.create(
            gender="f",
            name_first="Judith",
            name_last="Sheindlin",
            name_suffix="2",
            date_dob=date(1942, 10, 21),
            date_dod=date(2020, 11, 25),
            date_granularity_dob="%Y-%m-%d",
            date_granularity_dod="%Y-%m-%d",
            name_middle="Susan",
            dob_city="Brookyln",
            dob_state="NY",
            fjc_id=19832,
        )
        cls.person_2.race.add(cls.w_race)
        cls.person_2.race.add(cls.b_race)

        cls.person_3 = PersonFactory.create(
            gender="f",
            name_first="Sheindlin",
            name_last="Judith",
            date_dob=date(1945, 11, 20),
            date_granularity_dob="%Y-%m-%d",
            name_middle="Olivia",
            dob_city="Queens",
            dob_state="NY",
        )
        cls.person_3.race.add(cls.w_race)

        cls.position_1 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=date(1993, 1, 20),
            date_retirement=date(2001, 1, 20),
            termination_reason="retire_mand",
            position_type="pres",
            person=cls.person_1,
            how_selected="e_part",
        )
        cls.position_2 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=cls.court_1,
            date_start=date(2015, 12, 14),
            predecessor=cls.person_2,
            appointer=cls.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=cls.person_2,
            how_selected="e_part",
            nomination_process="fed_senate",
            date_elected=date(2015, 11, 12),
            date_confirmation=date(2015, 11, 14),
            date_termination=date(2018, 10, 14),
            date_granularity_termination="%Y-%m-%d",
            date_hearing=date(2021, 10, 14),
            date_judicial_committee_action=date(2022, 10, 14),
            date_recess_appointment=date(2013, 10, 14),
            date_referred_to_judicial_committee=date(2010, 10, 14),
            date_retirement=date(2023, 10, 14),
        )
        cls.position_3 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=date(2015, 12, 14),
            organization_name="Pants, Inc.",
            job_title="Corporate Lawyer",
            position_type=None,
            person=cls.person_2,
        )
        cls.position_4 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=cls.court_2,
            date_start=date(2020, 12, 14),
            predecessor=cls.person_3,
            appointer=cls.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=cls.person_3,
            how_selected="a_legis",
            nomination_process="fed_senate",
        )

        cls.school_1 = SchoolFactory(name="New York Law School")
        cls.school_2 = SchoolFactory(name="American University")

        cls.education_1 = EducationFactory(
            degree_level="jd",
            person=cls.person_2,
            degree_year=1965,
            school=cls.school_1,
        )
        cls.education_2 = EducationFactory(
            degree_level="ba",
            person=cls.person_2,
            school=cls.school_2,
        )
        cls.education_3 = EducationFactory(
            degree_level="ba",
            person=cls.person_3,
            school=cls.school_1,
        )

        cls.political_affiliation_1 = PoliticalAffiliationFactory.create(
            political_party="d",
            source="b",
            date_start=date(1993, 1, 1),
            person=cls.person_1,
            date_granularity_start="%Y",
        )
        cls.political_affiliation_2 = PoliticalAffiliationFactory.create(
            political_party="d",
            source="b",
            date_start=date(2015, 12, 14),
            person=cls.person_2,
            date_granularity_start="%Y-%m-%d",
        )
        cls.political_affiliation_3 = PoliticalAffiliationFactory.create(
            political_party="i",
            source="b",
            date_start=date(2015, 12, 14),
            person=cls.person_3,
            date_granularity_start="%Y-%m-%d",
        )

        cls.aba_rating_1 = ABARatingFactory(
            rating="nq",
            person=cls.person_2,
            year_rated="2015",
        )


class SearchMixin(PeopleMixin):
    """Search test case factories"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.docket_1 = DocketFactory.create(
            date_reargument_denied=date(2015, 8, 15),
            court_id=cls.court_2.pk,
            case_name_full="case name full docket 1",
            date_argued=date(2015, 8, 16),
            case_name="case name docket 1",
            case_name_short="case name short docket 1",
            docket_number="docket number 1 005",
            slug="case-name",
            pacer_case_id="666666",
            blocked=False,
            source=0,
        )
        cls.docket_2 = DocketFactory.create(
            date_reargument_denied=date(2015, 8, 15),
            court_id=cls.court_2.pk,
            case_name_full="case name full docket 2",
            date_argued=date(2015, 8, 15),
            case_name="case name docket 2",
            case_name_short="case name short docket 2",
            docket_number="docket number 2",
            slug="case-name",
            blocked=False,
            source=0,
        )
        cls.docket_3 = DocketFactory.create(
            date_reargument_denied=date(2015, 8, 15),
            court_id=cls.court_1.pk,
            case_name_full="case name full docket 3",
            date_argued=date(2015, 8, 14),
            case_name="case name docket 3",
            case_name_short="case name short docket 3",
            docket_number="docket number 3",
            slug="case-name",
            blocked=False,
            source=0,
        )

        cls.opinion_cluster_1 = OpinionClusterFactory.create(
            case_name_full="Paul Debbas v. Franklin",
            case_name_short="Debbas",
            syllabus="some rando syllabus",
            date_filed=date(2015, 8, 14),
            procedural_history="some rando history",
            source="C",
            case_name="Debbas v. Franklin",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            precedential_status="Errata",
            citation_count=4,
            docket=cls.docket_1,
        )
        cls.opinion_cluster_1.panel.add(cls.person_2)

        cls.opinion_cluster_2 = OpinionClusterFactory.create(
            case_name_full="Harvey Howard v. Antonin Honda",
            case_name_short="Howard",
            syllabus="some rando syllabus",
            date_filed=date(1895, 6, 9),
            procedural_history="some rando history",
            source="C",
            judges="David",
            case_name="Howard v. Honda",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            precedential_status="Published",
            citation_count=6,
            scdb_votes_minority=3,
            scdb_votes_majority=6,
            nature_of_suit="copyright",
            docket=cls.docket_2,
        )

        cls.opinion_cluster_3 = OpinionClusterFactory.create(
            case_name_full="Reference to Lissner v. Saad",
            case_name_short="case name short cluster 3",
            syllabus="some rando syllabus",
            date_filed=date(2015, 8, 15),
            procedural_history="some rando history",
            source="C",
            case_name="case name cluster 3",
            attorneys="a bunch of crooks!",
            slug="case-name-cluster",
            precedential_status="Published",
            citation_count=8,
            docket=cls.docket_3,
        )

        cls.citation_1 = CitationWithParentsFactory.create(
            volume=33,
            reporter="state",
            page="1",
            type=1,
            cluster=cls.opinion_cluster_1,
        )
        cls.citation_2 = CitationWithParentsFactory.create(
            volume=22,
            reporter="AL",
            page="339",
            type=8,
            cluster=cls.opinion_cluster_2,
        )
        cls.citation_3 = CitationWithParentsFactory.create(
            volume=33,
            reporter="state",
            page="1",
            type=1,
            cluster=cls.opinion_cluster_2,
        )
        cls.citation_4 = CitationWithParentsFactory.create(
            volume=1,
            reporter="Yeates",
            page="1",
            type=5,
            cluster=cls.opinion_cluster_2,
        )
        cls.citation_5 = CitationWithParentsFactory.create(
            volume=56,
            reporter="F.2d",
            page="9",
            type=1,
            cluster=cls.opinion_cluster_2,
        )
        cls.citation_5 = CitationWithParentsFactory.create(
            volume=56,
            reporter="F.2d",
            page="11",
            type=1,
            cluster=cls.opinion_cluster_3,
        )
        cls.opinion_1 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=cls.person_2,
            plain_text="my plain text secret word for queries",
            cluster=cls.opinion_cluster_1,
            local_path="test/search/opinion_doc.doc",
            per_curiam=False,
            type="020lead",
        )
        cls.opinion_2 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=cls.person_2,
            plain_text="my plain text secret word for queries",
            cluster=cls.opinion_cluster_2,
            html_with_citations='yadda yadda <span class="star-pagination">*9</span> this is page 9 <span class="star-pagination">*10</span> this is content on page 10 can we link to it...',
            local_path="test/search/opinion_pdf_image_based.pdf",
            per_curiam=False,
            type="010combined",
        )
        cls.opinion_2.joined_by.add(cls.person_2)

        cls.opinion_3 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=cls.person_2,
            plain_text="my plain text secret word for queries 1 Yeates 1",
            cluster=cls.opinion_cluster_3,
            local_path="test/search/opinion_pdf_text_based.pdf",
            per_curiam=False,
            type="010combined",
        )
        cls.opinion_4 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=cls.person_2,
            plain_text="my plain text secret word for queries",
            cluster=cls.opinion_cluster_1,
            local_path="test/search/opinion_html.html",
            per_curiam=False,
            type="010combined",
        )
        cls.opinion_5 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=cls.person_2,
            plain_text="my plain text secret word for queries",
            cluster=cls.opinion_cluster_1,
            local_path="test/search/opinion_wpd.wpd",
            per_curiam=False,
            type="010combined",
        )
        cls.opinion_6 = OpinionFactory.create(
            extracted_by_ocr=False,
            author=cls.person_2,
            plain_text="my plain text secret word for queries",
            cluster=cls.opinion_cluster_1,
            local_path="test/search/opinion_text.txt",
            per_curiam=False,
            type="010combined",
        )
        cls.opinion_cited_1 = OpinionsCitedWithParentsFactory.create(
            cited_opinion=cls.opinion_2,
            citing_opinion=cls.opinion_1,
        )
        cls.opinion_cited_2 = OpinionsCitedWithParentsFactory.create(
            cited_opinion=cls.opinion_3,
            citing_opinion=cls.opinion_1,
        )
        cls.opinion_cited_3 = OpinionsCitedWithParentsFactory.create(
            cited_opinion=cls.opinion_3,
            citing_opinion=cls.opinion_2,
        )
        cls.opinion_cited_4 = OpinionsCitedWithParentsFactory.create(
            cited_opinion=cls.opinion_1,
            citing_opinion=cls.opinion_3,
        )


class RECAPSearchMixin:
    """RECAP Search test case factories"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.court = CourtFactory(id="canb", jurisdiction="FB")
        cls.court_2 = CourtFactory(id="ca1", jurisdiction="F")
        cls.judge = PersonFactory.create(
            name_first="Thalassa", name_last="Miller"
        )
        cls.judge_2 = PersonFactory.create(
            name_first="Persephone", name_last="Sinclair"
        )
        cls.de = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=cls.court,
                case_name="SUBPOENAS SERVED ON",
                case_name_full="Jackson & Sons Holdings vs. Bank",
                date_filed=date(2015, 8, 16),
                date_argued=date(2013, 5, 20),
                docket_number="1:21-bk-1234",
                assigned_to=cls.judge,
                referred_to=cls.judge_2,
                nature_of_suit="440",
                source=Docket.RECAP,
                cause="401 Civil",
                jurisdiction_type="'U.S. Government Defendant",
                jury_demand="1,000,000",
            ),
            entry_number=1,
            date_filed=date(2015, 8, 19),
            description="MOTION for Leave to File Amicus Curiae Lorem Served",
        )
        cls.firm = AttorneyOrganizationFactory(name="Associates LLP")
        cls.attorney = AttorneyFactory(
            name="Debbie Russell",
            organizations=[cls.firm],
            docket=cls.de.docket,
        )
        cls.party_type = PartyTypeFactory.create(
            party=PartyFactory(
                name="Defendant Jane Roe",
                docket=cls.de.docket,
                attorneys=[cls.attorney],
            ),
            docket=cls.de.docket,
        )

        cls.rd = RECAPDocumentFactory(
            docket_entry=cls.de,
            description="Leave to File",
            document_number="1",
            is_available=True,
            page_count=5,
            pacer_doc_id="018036652435",
        )

        cls.opinion = OpinionFactory(
            cluster=OpinionClusterFactory(docket=cls.de.docket)
        )
        OpinionsCitedByRECAPDocument.objects.bulk_create(
            [
                OpinionsCitedByRECAPDocument(
                    citing_document=cls.rd,
                    cited_opinion=cls.opinion,
                    depth=1,
                )
            ]
        )
        cls.rd_att = RECAPDocumentFactory(
            docket_entry=cls.de,
            description="Document attachment",
            document_type=RECAPDocument.ATTACHMENT,
            document_number="1",
            attachment_number=2,
            is_available=False,
            page_count=7,
            pacer_doc_id="018036652436",
        )

        cls.judge_3 = PersonFactory.create(
            name_first="Seraphina", name_last="Hawthorne"
        )
        cls.judge_4 = PersonFactory.create(
            name_first="Leopold", name_last="Featherstone"
        )
        cls.de_1 = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                docket_number="12-1235",
                court=cls.court_2,
                case_name="SUBPOENAS SERVED OFF",
                case_name_full="The State of Franklin v. Solutions LLC",
                date_filed=date(2016, 8, 16),
                date_argued=date(2012, 6, 23),
                assigned_to=cls.judge_3,
                referred_to=cls.judge_4,
                source=Docket.COLUMBIA_AND_RECAP,
            ),
            entry_number=3,
            date_filed=date(2014, 7, 5),
            description="MOTION for Leave to File Amicus Discharging Debtor",
        )
        cls.rd_2 = RECAPDocumentFactory(
            docket_entry=cls.de_1,
            description="Leave to File",
            document_number="3",
            page_count=10,
            plain_text="Mauris iaculis, leo sit amet hendrerit vehicula, Maecenas nunc justo. Integer varius sapien arcu, quis laoreet lacus consequat vel.",
            pacer_doc_id="016156723121",
        )


class SitemapMixin:
    sitemap_url: str
    expected_item_count: int

    def setUpSiteDomain(self) -> None:
        # set the domain name in the Sites framework to match the test domain name, set http url schema
        domain = "testserver"
        SiteModel = apps.get_model("sites", "Site")

        SiteModel.objects.update_or_create(
            pk=settings.SITE_ID, defaults={"domain": domain, "name": domain}
        )

    def assert_sitemap_has_content(self) -> None:
        """Does content get into the sitemap?"""
        response = self.client.get(self.sitemap_url)
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        node_count = len(
            cast(
                Sized,
                xml_tree.xpath(
                    "//s:url",
                    namespaces={
                        "s": "http://www.sitemaps.org/schemas/sitemap/0.9"
                    },
                ),
            )
        )
        self.assertGreater(
            self.expected_item_count,
            0,
            msg="Didn't get any content in test case.",
        )
        self.assertEqual(
            node_count,
            self.expected_item_count,
            msg="Did not get the right number of items in the sitemap.\n"
            f"\tCounted:\t{node_count}\n"
            f"\tExpected:\t{self.expected_item_count}",
        )


class AudioMixin:
    """Audio test case factories"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.audio_1 = AudioFactory.create(
            docket_id=1,
            duration=420,
            judges="",
            local_path_original_file="test/audio/ander_v._leo.mp3",
            local_path_mp3="test/audio/2.mp3",
            sha1="de8cff186eb263dc06bdc5340860eb6809f898d3",
            source="C",
            blocked=False,
        )
        cls.audio_2 = AudioFactory.create(
            docket_id=2,
            duration=837,
            judges="",
            local_path_original_file="mp3/2014/06/09/ander_v._leo.mp3",
            local_path_mp3="test/audio/2.mp3",
            sha1="daadaf6cc018114259f7eba27c4c2e6bba9bd0d7",
            source="C",
        )
        cls.audio_3 = AudioFactory.create(
            docket_id=3,
            duration=653,
            judges="",
            local_path_original_file="mp3/2015/07/08/hong_liu_yang_v._loretta_e._lynch.mp3",
            local_path_mp3="test/audio/2.mp3",
            sha1="f540838e606f15585e713812c67537affc0df944",
            source="CR",
        )

    @classmethod
    def tearDownClass(cls):
        Audio.objects.all().delete()
        super().tearDownClass()


class AudioESMixin:
    """Audio test case factories for ES"""

    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "test_objects_search.json",
    ]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.court_1 = CourtFactory(
            id="cabc",
            full_name="Testing Supreme Court",
            jurisdiction="FB",
            citation_string="Bankr. C.D. Cal.",
        )
        cls.court_2 = CourtFactory(
            id="nyed",
            full_name="Court of Appeals for the First Circuit",
            jurisdiction="FB",
            citation_string="Bankr. C.D. Cal.",
        )
        cls.docket_1 = DocketFactory.create(
            docket_number="1:21-bk-1234",
            court_id=cls.court_1.pk,
            date_argued=date(2015, 8, 16),
            date_reargued=date(2016, 9, 16),
            date_reargument_denied=date(2017, 10, 16),
        )
        cls.docket_2 = DocketFactory.create(
            docket_number="19-5734",
            court_id=cls.court_1.pk,
            date_argued=date(2015, 8, 15),
        )
        cls.docket_3 = DocketFactory.create(
            docket_number="ASBCA No. 59126",
            court_id=cls.court_2.pk,
            date_argued=date(2015, 8, 14),
        )
        cls.docket_4 = DocketFactory.create(
            docket_number="1:21-cv-1234-ABC",
            court_id=cls.court_1.pk,
            date_argued=date(2013, 8, 14),
        )
        cls.transcript = "This is the best transcript. Nunc egestas sem sed libero feugiat, at interdum quam viverra. Pellentesque hendrerit ut augue at sagittis. Mauris faucibus fringilla lacus, eget maximus risus. Phasellus id mi at eros fermentum vestibulum nec nec diam. In nec sapien nunc. Ut massa ante, accumsan a erat eget, rhoncus pellentesque felis."
        cls.filepath_local = SimpleUploadedFile(
            "sec_frank.mp3", b"mp3 binary content", content_type="audio/mpeg"
        )
        cls.audio_1 = AudioFactory.create(
            case_name="SEC v. Frank J. Information, WikiLeaks",
            case_name_full="a_random_title",
            docket_id=cls.docket_1.pk,
            duration=420,
            judges="Mary Deposit Learning rd Administrative procedures act",
            local_path_original_file="test/audio/ander_v._leo.mp3",
            local_path_mp3=cls.filepath_local,
            source="C",
            blocked=False,
            sha1="a49ada009774496ac01fb49818837e2296705c97",
            stt_status=Audio.STT_COMPLETE,
            stt_transcript=cls.transcript,
        )
        cls.audio_2 = AudioFactory.create(
            case_name="Jose A. Dominguez v. Loretta E. Lynch",
            docket_id=cls.docket_2.pk,
            duration=837,
            judges="Wallace and Friedland Learn of rd",
            local_path_original_file="mp3/2014/06/09/ander_v._leo.mp3",
            local_path_mp3="test/audio/2.mp3",
            source="C",
            sha1="a49ada009774496ac01fb49818837e2296705c92",
        )
        cls.audio_3 = AudioFactory.create(
            case_name="Hong Liu Yang v. Lynch-Loretta E. Howell",
            docket_id=cls.docket_3.pk,
            duration=653,
            judges="Joseph Information Deposition H Administrative magazine",
            local_path_original_file="mp3/2015/07/08/hong_liu_yang_v._loretta_e._lynch.mp3",
            local_path_mp3="test/audio/2.mp3",
            source="CR",
            sha1="a49ada009774496ac01fb49818837e2296705c93",
        )
        cls.author = PersonFactory.create()
        cls.audio_4 = AudioFactory.create(
            case_name="Hong Liu Lorem v. Lynch-Loretta E.",
            docket_id=cls.docket_3.pk,
            duration=653,
            judges="John Smith ptsd mag",
            sha1="a49ada009774496ac01fb49818837e2296705c94",
        )
        cls.audio_4.panel.add(cls.author)
        cls.audio_5 = AudioFactory.create(
            case_name="Freedom of Inform Wikileaks Howells",
            docket_id=cls.docket_4.pk,
            duration=400,
            judges="Wallace to Friedland ⚖️ Deposit xx-xxxx apa magistrate Freedom of Inform Wikileaks",
            sha1="a49ada009774496ac01fb49818837e2296705c95",
        )
        cls.audio_1.panel.add(cls.author)


class SearchAlertsMixin:
    @staticmethod
    def get_html_content_from_email(email_content):
        html_content = None
        for content, content_type in email_content.alternatives:
            if content_type == "text/html":
                html_content = content
                break
        return html_content

    def _confirm_number_of_alerts(self, html_content, expected_count):
        """Test the number of alerts included in the email alert."""
        tree = html.fromstring(html_content)
        got = len(tree.xpath("//h2"))

        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of alerts in the email. "
            f"Expected: {expected_count} - Got: {got}\n\n",
        )

    @staticmethod
    def _extract_cases_from_alert(html_tree, alert_title):
        """Extract the case elements (h3) under a specific alert (h2) from the
        HTML tree.
        """
        alert_element = html_tree.xpath(
            f"//h2[contains(text(), '{alert_title}')]"
        )
        h2_elements = html_tree.xpath("//h2")
        alert_index = h2_elements.index(alert_element[0])
        # Find the <h3> elements between this <h2> and the next <h2>
        if alert_index + 1 < len(h2_elements):
            next_alert_element = h2_elements[alert_index + 1]
            alert_cases = html_tree.xpath(
                f"//h2[contains(text(), '{alert_title}')]/following-sibling::*[following-sibling::h2[1] = '{next_alert_element.text}'][self::h3]"
            )
        else:
            alert_cases = html_tree.xpath(
                f"//h2[contains(text(), '{alert_title}')]/following-sibling::h3"
            )
        return alert_cases

    @staticmethod
    def clean_case_title(case_title):
        """Clean the case text to get the case name to compare it.
        Input: 1. SUBPOENAS SERVED CASE ()
        Output: SUBPOENAS SERVED CASE
        """

        # Split the string by the dot and take everything after it.
        parts = case_title.split(".", 1)
        if len(parts) > 1:
            case_title = parts[1].strip()
        # Remove everything from the first open parenthesis to the end
        case_title = re.split(r"\s*\(", case_title)[0].strip()
        return case_title

    def _count_alert_hits_and_child_hits(
        self,
        html_content,
        alert_title,
        expected_hits,
        case_title,
        expected_child_hits,
    ):
        """Confirm the following assertions for the email alert:
        - An specific alert is included in the email alert.
        - The specified alert contains the expected number of hits.
        - The specified case contains the expected number of child hits.
        """
        tree = html.fromstring(html_content)
        alert_element = tree.xpath(f"//h2[contains(text(), '{alert_title}')]")
        self.assertTrue(
            alert_element, msg=f"Not alert with title {alert_title} found."
        )
        alert_cases = self._extract_cases_from_alert(tree, alert_title)
        self.assertEqual(
            len(alert_cases),
            expected_hits,
            msg=f"Did not get the right number of hits for the alert {alert_title}. "
            f"Expected: {expected_hits} - Got: {len(alert_cases)}\n\n",
        )
        if case_title:
            for case in alert_cases:
                case_text = " ".join(
                    [element.strip() for element in case.xpath(".//text()")]
                )
                case_text_cleaned = self.clean_case_title(case_text)
                if case_title == case_text_cleaned:
                    child_hit_count = len(
                        case.xpath(
                            "following-sibling::ul[1]/li/a | following-sibling::ul[1]/li/strong"
                        )
                    )
                    self.assertEqual(
                        child_hit_count,
                        expected_child_hits,
                        msg=f"Did not get the right number of child hits for the case {case_title}. "
                        f"Expected: {expected_child_hits} - Got: {child_hit_count}\n\n",
                    )
                    break

    def _assert_child_hits_content(
        self,
        html_content,
        alert_title,
        case_title,
        expected_child_descriptions,
    ):
        """Confirm the child hits in a case are the expected ones, comparing
        their descriptions.
        """
        tree = html.fromstring(html_content)
        # Get the alert cases from the HTML.
        alert_cases = self._extract_cases_from_alert(tree, alert_title)

        def extract_child_descriptions(case_item):
            child_documents = case_item.xpath("./following-sibling::ul[1]/li")
            results = []
            for li in child_documents:
                child_tag = li.xpath(".//a | .//strong")[0]
                full_text = child_tag.text_content()
                first_part = full_text.split("\u2014")[0].strip()
                results.append(first_part)

            return results

        child_descriptions = set()
        for case in alert_cases:
            case_text = "".join(case.xpath(".//text()")).strip()
            case_text_cleaned = self.clean_case_title(case_text)
            if case_title == case_text_cleaned:
                child_descriptions = set(extract_child_descriptions(case))
                break

        self.assertEqual(
            child_descriptions,
            set(expected_child_descriptions),
            msg=f"Child hits didn't match for case {case_title}, Got {child_descriptions}, Expected: {expected_child_descriptions} ",
        )

    def _count_webhook_hits_and_child_hits(
        self,
        webhooks,
        alert_title,
        expected_hits,
        case_title,
        expected_child_hits,
        nested_field="recap_documents",
    ):
        """Confirm the following assertions for the search alert webhook:
        - An specific alert webhook was triggered.
        - The specified alert contains the expected number of hits.
        - The specified case contains the expected number of child hits.
        """

        matched_alert_name = None
        matched_case_title = None
        for webhook in webhooks:
            if webhook["payload"]["alert"]["name"] == alert_title:
                webhook_cases = webhook["payload"]["results"]
                self.assertEqual(
                    len(webhook_cases),
                    expected_hits,
                    msg=f"Did not get the right number of hits for the alert {alert_title}. ",
                )
                matched_alert_name = True
                for case in webhook["payload"]["results"]:
                    if case_title == strip_tags(case["caseName"]):
                        matched_case_title = True
                        if nested_field is None:
                            self.assertTrue(nested_field not in case)
                            continue
                        self.assertEqual(
                            len(case[nested_field]),
                            expected_child_hits,
                            msg=f"Did not get the right number of child documents for the case {case_title}. ",
                        )
        self.assertTrue(matched_alert_name, msg="Alert name didn't match")
        self.assertTrue(matched_case_title, msg="Case title didn't match")

    def _count_percolator_webhook_hits_and_child_hits(
        self,
        webhooks,
        alert_title,
        expected_hits,
        expected_child_hits,
        expected_child_descriptions,
    ):
        """Confirm the following assertions for the percolator search alert
        webhook:
        - The specified alert was triggered the expected number of times.
        - The specified alert contains only 1 hit.
        - If the specified case contains child documents it must be 1.
        """

        alert_title_webhooks = 0
        alert_child_hits = 0
        alert_child_ids = set()
        for webhook in webhooks:
            if webhook["payload"]["alert"]["name"] == alert_title:
                alert_title_webhooks += 1

                hits = webhook["payload"]["results"]

                self.assertEqual(
                    1,
                    len(hits),
                    msg="Did not get the right number of hits for the case {}. ".format(
                        webhook["payload"]["results"][0]["caseName"]
                    ),
                )
                alert_child_hits = alert_child_hits + len(
                    webhook["payload"]["results"][0]["recap_documents"]
                )
                for rd in webhook["payload"]["results"][0]["recap_documents"]:
                    alert_child_ids.add(rd["id"])

        self.assertEqual(
            alert_title_webhooks,
            expected_hits,
            msg=f"Did not get the right number of webhooks for alert {alert_title}. ",
        )
        self.assertEqual(
            alert_child_hits,
            expected_child_hits,
            msg=f"Did not get the right number of child hits for alert {alert_title}. ",
        )
        if expected_child_descriptions:
            self.assertEqual(
                alert_child_ids,
                set(expected_child_descriptions),
                msg=f"Did not get the right child hits IDs for alert {alert_title}. ",
            )

    def _assert_webhook_hit_hl(
        self,
        webhooks,
        alert_title,
        field_name,
        hl_expected,
        child_field,
        nested_field="recap_documents",
    ):
        """Assert Hl in webhook fields."""
        for webhook in webhooks:
            if webhook["payload"]["alert"]["name"] == alert_title:
                hit = webhook["payload"]["results"][0]
                if child_field:
                    self.assertNotIn(
                        "score",
                        hit[nested_field][0]["meta"],
                        msg="score shouldn't be present on webhook nested documents",
                    )
                    child_field_content = hit[nested_field][0][field_name]
                    self.assertIn(
                        hl_expected,
                        child_field_content,
                        msg=f"Did not get the HL content in field: {field_name}. ",
                    )
                else:
                    self.assertNotIn(
                        "score",
                        hit["meta"],
                        msg="score shouldn't be present on webhook main document",
                    )
                    parent_field_content = hit[field_name]
                    self.assertIn(
                        hl_expected,
                        parent_field_content,
                        msg=f"Did not get the HL content in field: {field_name}. ",
                    )

    def _assert_timestamp_filter(
        self, html_content, rate, date, sweep_index=False
    ):
        """Confirm that timestamp filter is properly set in the
        'View Full Results' URL.
        """
        view_results_url = html.fromstring(str(html_content)).xpath(
            '//a[text()="View Full Results / Edit this Alert"]/@href'
        )
        parsed_url = urlparse(view_results_url[0])
        params = parse_qs(parsed_url.query)
        cut_off_date = get_cut_off_date(rate, date, sweep_index)
        iso_datetime = (
            cut_off_date.strftime("%Y-%m-%dT%H:%M:%S")
            if isinstance(cut_off_date, datetime)
            else cut_off_date.strftime("%Y-%m-%d")
        )
        self.assertIn(f"timestamp:[{iso_datetime} TO *]", params["q"][0])

    def _assert_date_updated(self, date_to_compare, html_content, txt_content):
        """Confirm that date_updated is properly set in the alert email."""

        self.assertIn(
            f"Date Updated: {format(date_to_compare, 'F jS, Y h:i a T')}",
            html_content,
        )

        self.assertIn(
            f"Date Updated: {format(date_to_compare, 'F jS, Y h:i a T')}",
            txt_content,
        )

    @staticmethod
    def _extract_snippet_content(html_content: str):
        html_doc = html.fromstring(html_content)
        snippet_content = cast(
            list[HtmlElement],
            html_doc.xpath('//*[self::p or self::span][@id="snippet"]'),
        )
        assert snippet_content, "No snippet found"

        snippet_text = snippet_content[0].text_content().strip()
        return snippet_text.replace("…", "").replace("&hellip;", "")


class V4SearchAPIMixin:
    """Common assertions for V4 Search API tests."""

    async def _compare_field(
        self,
        meta_field,
        meta_value,
        meta_fields_to_compare,
        content_to_compare,
    ):
        get_meta_expected_value = meta_fields_to_compare.get(meta_field)
        meta_expected_value = await sync_to_async(get_meta_expected_value)(
            content_to_compare
        )
        if meta_field == "score":
            # Special case for the score field. Only confirm the presence of
            # keys and avoid comparing values, as they differ in each response.
            self.assertEqual(
                set(meta_value.keys()),
                set(meta_expected_value.keys()),
                f"The keys in field '{meta_field}' do not match.",
            )
            for score_value in meta_value.values():
                self.assertIsNotNone(
                    score_value, "The score value can't be None."
                )

        else:
            self.assertEqual(
                meta_value,
                meta_expected_value,
                f"The field '{meta_field}' does not match.",
            )

    async def _test_api_fields_content(
        self,
        api_response,
        content_to_compare,
        fields_to_compare,
        child_document_keys,
        meta_fields_to_compare,
    ):
        for (
            field,
            get_expected_value,
        ) in fields_to_compare.items():
            with self.subTest(field=field):
                if isinstance(api_response, ReturnList):
                    parent_document = api_response[0]
                else:
                    parent_document = api_response.data["results"][0]
                actual_value = parent_document.get(field)
                if field in ["recap_documents", "opinions", "positions"]:
                    child_document = actual_value[0]
                    for child_field, child_value in child_document.items():
                        with self.subTest(child_field=child_field):
                            if child_field == "meta":
                                for (
                                    meta_field,
                                    meta_value,
                                ) in child_value.items():
                                    with self.subTest(meta_field=meta_field):
                                        self.assertFalse(
                                            meta_field == "score",
                                            msg="score key should not be present in nested documents",
                                        )
                                        await self._compare_field(
                                            meta_field,
                                            meta_value,
                                            meta_fields_to_compare,
                                            content_to_compare,
                                        )
                            else:
                                await self._compare_field(
                                    child_field,
                                    child_value,
                                    child_document_keys,
                                    content_to_compare,
                                )
                elif field == "meta":
                    for meta_field, meta_value in actual_value.items():
                        with self.subTest(meta_field=meta_field):
                            await self._compare_field(
                                meta_field,
                                meta_value,
                                meta_fields_to_compare,
                                content_to_compare,
                            )
                else:
                    expected_value = await sync_to_async(get_expected_value)(
                        content_to_compare
                    )
                    self.assertEqual(
                        actual_value,
                        expected_value,
                        f"Parent field '{field}' does not match.",
                    )

    def _test_results_ordering(self, test, field, version="v4"):
        """Ensure dockets appear in the response in a specific order."""

        with self.subTest(test=test, msg=f"{test['name']}"):
            r = self.client.get(
                reverse("search-list", kwargs={"version": version}),
                test["search_params"],
            )

            expected_order_key = "expected_order"
            if version == "v3":
                expected_order_key = (
                    "expected_order_v3"
                    if "expected_order_v3" in test
                    else "expected_order"
                )

            self.assertEqual(
                len(r.data["results"]), len(test[expected_order_key])
            )
            # Note that dockets where the date_field is null are sent to the bottom
            # of the results
            actual_order = [result[field] for result in r.data["results"]]
            self.assertEqual(
                actual_order,
                test[expected_order_key],
                msg=f"Expected order {test[expected_order_key]}, but got {actual_order} for "
                f"Search type: {test['search_params']['type']}",
            )

    def _assert_order_in_html(
        self, decoded_content: str, expected_order: list
    ) -> None:
        """Assert that the expected order of documents appears correctly in the
        HTML content."""

        for i in range(len(expected_order) - 1):
            self.assertTrue(
                decoded_content.index(str(expected_order[i]))
                < decoded_content.index(str(expected_order[i + 1])),
                f"Expected {expected_order[i]} to appear before {expected_order[i + 1]} in the HTML content.",
            )

    async def _test_article_count(self, params, expected_count, field_name):
        r = await self.async_client.get("/", params)
        tree = html.fromstring(r.content.decode())
        got = len(tree.xpath("//article"))
        self.assertEqual(
            got,
            expected_count,
            msg=f"Did not get the right number of search results in Frontend with {field_name} "
            "filter applied.\n"
            f"Expected: {expected_count}\n"
            f"     Got: {got}\n\n"
            f"Params were: {params}",
        )
        return r

    def _test_page_variables(
        self, response, test_case, current_page, search_type
    ):
        """Ensure the page variables are the correct ones according to the
        current page."""

        # Test page
        self.assertEqual(
            len(response.data["results"]),
            test_case["results"],
            msg="Results in page didn't match.",
        )
        self.assertEqual(
            response.data["count"],
            test_case["count_exact"],
            msg="Results count didn't match.",
        )
        if search_type == SEARCH_TYPES.RECAP:
            self.assertEqual(
                response.data["document_count"],
                test_case["document_count"],
                msg="Document count didn't match.",
            )
        else:
            self.assertNotIn(
                "document_count",
                response.data,
                msg="Document count should not be present.",
            )

        next_page = response.data["next"]
        expected_next_page = test_case["next"]
        if expected_next_page:
            self.assertTrue(next_page, msg="Next page value didn't match")
            current_page = next_page
        else:
            self.assertFalse(next_page, msg="Next page value didn't match")

        previous_page = response.data["previous"]
        expected_previous_page = test_case["previous"]
        if expected_previous_page:
            self.assertTrue(
                previous_page,
                msg="Previous page value didn't match",
            )
        else:
            self.assertFalse(
                previous_page,
                msg="Previous page value didn't match",
            )
        return next_page, previous_page, current_page
