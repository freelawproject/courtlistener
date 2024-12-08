import datetime

from django.core.management import call_command
from django.urls import reverse
from factory import RelatedFactory

from cl.audio.factories import AudioFactory
from cl.people_db.factories import PersonFactory, PersonWithChildrenFactory
from cl.people_db.models import Person, Position
from cl.search.factories import (
    CourtFactory,
    DocketEntryWithParentsFactory,
    DocketFactory,
    OpinionClusterFactoryWithChildrenAndParents,
    OpinionWithChildrenFactory,
)
from cl.search.models import PRECEDENTIAL_STATUS, SEARCH_TYPES, Docket, Opinion
from cl.tests.cases import ESIndexTestCase, TestCase, TransactionTestCase


class TestPersonWithChildrenFactory(TransactionTestCase):
    def test_positions_connected_to_person(self):
        new_person_with_position = PersonWithChildrenFactory()

        # Made 1 person and 1 position
        self.assertEqual(1, Person.objects.count())
        self.assertEqual(1, Position.objects.count())

        # The person has a position
        self.assertEqual(len(new_person_with_position.positions.all()), 1)
        # The position is connected to the person
        positions_in_db = Position.objects.all()
        self.assertEqual(
            new_person_with_position.id, positions_in_db[0].person_id
        )


class PersonPageRelatedCases(ESIndexTestCase, TestCase):
    """Ensure that related cases are properly displayed on the Person detail page."""

    @classmethod
    def setUpTestData(cls):
        cls.court_1 = CourtFactory(
            id="cabc",
            full_name="Testing Supreme Court",
            jurisdiction="FB",
            citation_string="Bankr. C.D. Cal.",
        )
        cls.docket_1 = DocketFactory.create(
            docket_number="1:21-bk-1234",
            court_id=cls.court_1.pk,
            date_argued=datetime.date(2015, 8, 16),
            case_name="Lorem Audio",
        )
        cls.author = PersonFactory.create(name_last="Jones")
        cls.audio = AudioFactory.create(
            case_name="Oral Argument Ipsum",
            docket_id=cls.docket_1.pk,
            duration=653,
            judges="John Smith ptsd mag",
            sha1="a49ada009774496ac01fb49818837e2296705c94",
        )
        cls.audio.panel.add(cls.author)
        cls.rebuild_index("audio.Audio")

        cls.opinion_cluster = OpinionClusterFactoryWithChildrenAndParents(
            case_name="Strickland v. Lorem.",
            case_name_full="Strickland v. Lorem.",
            date_filed=datetime.date(2020, 8, 15),
            docket=DocketFactory(
                court=cls.court_1,
                docket_number="123456",
                source=Docket.HARVARD,
            ),
            sub_opinions=RelatedFactory(
                OpinionWithChildrenFactory,
                factory_related_name="cluster",
                type=Opinion.ADDENDUM,
            ),
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            source="C",
            judges="",
        )
        cls.opinion_cluster.panel.add(cls.author)

        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.OPINION,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

        cls.de = DocketEntryWithParentsFactory(
            docket=DocketFactory(
                court=cls.court_1,
                case_name="SUBPOENAS SERVED ON",
                case_name_full="Jackson & Sons Holdings vs. Bank",
                date_filed=datetime.date(2015, 8, 16),
                date_argued=datetime.date(2013, 5, 20),
                docket_number="1:21-bk-9999",
                assigned_to=cls.author,
                source=Docket.RECAP,
            ),
            entry_number=1,
            date_filed=datetime.date(2015, 8, 19),
            description="MOTION for Leave to File Amicus Curiae Lorem Served",
        )

        call_command(
            "cl_index_parent_and_child_docs",
            search_type=SEARCH_TYPES.RECAP,
            queue="celery",
            pk_offset=0,
            testing_mode=True,
        )

    async def test_person_detail_page_related_documents(self) -> None:
        """Ensure that related cases are properly displayed on the Person detail page."""
        response = await self.async_client.get(
            reverse(
                "view_person",
                args=[self.author.pk, self.author.slug],
            )
        )

        # Case Law related cases.
        self.assertIn(
            "Case Law Authored by Jones (1)", response.content.decode()
        )
        self.assertIn("Strickland", response.content.decode())
        self.assertIn("123456", response.content.decode())

        # RECAP related cases.
        self.assertIn(
            "Cases Assigned or Referred to Jones (1)",
            response.content.decode(),
        )
        self.assertIn("SUBPOENAS SERVED ON", response.content.decode())
        self.assertIn("1:21-bk-9999", response.content.decode())

        # Oral Arguments related.
        self.assertIn(
            "Most Recent Oral Arguments Heard by Jones (1)",
            response.content.decode(),
        )
        self.assertIn("Oral Argument Ipsum", response.content.decode())
        self.assertIn("1:21-bk-1234", response.content.decode())
