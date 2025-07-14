from cl.people_db.factories import (
    ABARatingFactory,
    EducationFactory,
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
    OpinionsCitedWithParentsFactory,
    RECAPDocumentFactory,
)
from cl.users.factories import UserFactory, UserProfileWithParentsFactory


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


class PeopleMixin:
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
            date_dob=datetime.date(1942, 10, 21),
            date_dod=datetime.date(2020, 11, 25),
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
            date_dob=datetime.date(1945, 11, 20),
            date_granularity_dob="%Y-%m-%d",
            name_middle="Olivia",
            dob_city="Queens",
            dob_state="NY",
        )
        cls.person_3.race.add(cls.w_race)

        cls.position_1 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(1993, 1, 20),
            date_retirement=datetime.date(2001, 1, 20),
            termination_reason="retire_mand",
            position_type="pres",
            person=cls.person_1,
            how_selected="e_part",
        )
        cls.position_2 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=cls.court_1,
            date_start=datetime.date(2015, 12, 14),
            predecessor=cls.person_2,
            appointer=cls.position_1,
            judicial_committee_action="no_rep",
            termination_reason="retire_mand",
            position_type="c-jud",
            person=cls.person_2,
            how_selected="e_part",
            nomination_process="fed_senate",
            date_elected=datetime.date(2015, 11, 12),
            date_confirmation=datetime.date(2015, 11, 14),
            date_termination=datetime.date(2018, 10, 14),
            date_granularity_termination="%Y-%m-%d",
            date_hearing=datetime.date(2021, 10, 14),
            date_judicial_committee_action=datetime.date(2022, 10, 14),
            date_recess_appointment=datetime.date(2013, 10, 14),
            date_referred_to_judicial_committee=datetime.date(2010, 10, 14),
            date_retirement=datetime.date(2023, 10, 14),
        )
        cls.position_3 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(2015, 12, 14),
            organization_name="Pants, Inc.",
            job_title="Corporate Lawyer",
            position_type=None,
            person=cls.person_2,
        )
        cls.position_4 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            court=cls.court_2,
            date_start=datetime.date(2020, 12, 14),
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
            date_start=datetime.date(1993, 1, 1),
            person=cls.person_1,
            date_granularity_start="%Y",
        )
        cls.political_affiliation_2 = PoliticalAffiliationFactory.create(
            political_party="d",
            source="b",
            date_start=datetime.date(2015, 12, 14),
            person=cls.person_2,
            date_granularity_start="%Y-%m-%d",
        )
        cls.political_affiliation_3 = PoliticalAffiliationFactory.create(
            political_party="i",
            source="b",
            date_start=datetime.date(2015, 12, 14),
            person=cls.person_3,
            date_granularity_start="%Y-%m-%d",
        )

        cls.aba_rating_1 = ABARatingFactory(
            rating="nq",
            person=cls.person_2,
            year_rated="2015",
        )


class SearchMixin:
    """Search test case factories"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.docket_1 = DocketFactory.create(
            date_reargument_denied=datetime.date(2015, 8, 15),
            court_id=cls.court_2.pk,
            case_name_full="case name full docket 1",
            date_argued=datetime.date(2015, 8, 16),
            case_name="case name docket 1",
            case_name_short="case name short docket 1",
            docket_number="docket number 1 005",
            slug="case-name",
            pacer_case_id="666666",
            blocked=False,
            source=0,
        )
        cls.docket_2 = DocketFactory.create(
            date_reargument_denied=datetime.date(2015, 8, 15),
            court_id=cls.court_2.pk,
            case_name_full="case name full docket 2",
            date_argued=datetime.date(2015, 8, 15),
            case_name="case name docket 2",
            case_name_short="case name short docket 2",
            docket_number="docket number 2",
            slug="case-name",
            blocked=False,
            source=0,
        )
        cls.docket_3 = DocketFactory.create(
            date_reargument_denied=datetime.date(2015, 8, 15),
            court_id=cls.court_1.pk,
            case_name_full="case name full docket 3",
            date_argued=datetime.date(2015, 8, 14),
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
            date_filed=datetime.date(2015, 8, 14),
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
            date_filed=datetime.date(1895, 6, 9),
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
            date_filed=datetime.date(2015, 8, 15),
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
