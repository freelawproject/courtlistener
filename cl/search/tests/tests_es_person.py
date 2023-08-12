import datetime

from cl.lib.test_helpers import CourtTestCase
from cl.people_db.factories import (
    EducationFactory,
    PersonFactory,
    PoliticalAffiliationFactory,
    PositionFactory,
    SchoolFactory,
)
from cl.search.documents import PEOPLE_DOCS_TYPE_ID, PersonBaseDocument
from cl.tests.cases import ESIndexTestCase, TestCase


class PeopleSearchTestElasticSearch(CourtTestCase, ESIndexTestCase, TestCase):
    """People search tests for Elasticsearch"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rebuild_index("audio.Audio")
        cls.rebuild_index("people_db.Person")
        cls.person = PersonFactory.create(name_first="John Deer")
        cls.pos_1 = PositionFactory.create(
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(2015, 12, 14),
            organization_name="Pants, Inc.",
            job_title="Corporate Lawyer",
            position_type=None,
            person=cls.person,
        )
        cls.pos_2 = PositionFactory.create(
            court=cls.court_1,
            person=cls.person,
            date_granularity_start="%Y-%m-%d",
            date_start=datetime.date(1993, 1, 20),
            date_retirement=datetime.date(2001, 1, 20),
            termination_reason="retire_mand",
            position_type="c-jud",
            how_selected="e_part",
            nomination_process="fed_senate",
        )
        PoliticalAffiliationFactory.create(person=cls.person)
        school = SchoolFactory.create(name="Harvard University")
        cls.education = EducationFactory.create(
            person=cls.person,
            school=school,
            degree_level="ma",
            degree_year="1990",
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

    def test_index_parent_and_child_objects(self) -> None:
        """Confirm Parent object and child objects are properly indexed."""

        # Judge is indexed.
        self.assertTrue(PersonBaseDocument.exists(id=self.person.pk))

        # Position 1 is indexed.
        self.assertTrue(
            PersonBaseDocument.exists(
                id=PEOPLE_DOCS_TYPE_ID(self.pos_1.pk).POSITION
            )
        )

        # Position 2 is indexed.
        self.assertTrue(
            PersonBaseDocument.exists(
                id=PEOPLE_DOCS_TYPE_ID(self.pos_2.pk).POSITION
            )
        )

        # Education is indexed.
        self.assertTrue(
            PersonBaseDocument.exists(
                id=PEOPLE_DOCS_TYPE_ID(self.education.pk).EDUCATION
            )
        )
