from django.urls import reverse

from cl.people_db.factories import PersonFactory, PersonWithChildrenFactory
from cl.people_db.models import Person, Position
from cl.tests.cases import TestCase, TransactionTestCase


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


class PersonPageSearchButtons(TestCase):
    """Ensure that search buttons are displayed on the Person detail page."""

    @classmethod
    def setUpTestData(cls):
        cls.person = PersonFactory.create(name_last="Jones")

    async def test_person_detail_page_has_search_buttons(self) -> None:
        """Verify the person page shows search buttons with nofollow links."""
        response = await self.async_client.get(
            reverse(
                "view_person",
                args=[self.person.pk, self.person.slug],
            )
        )
        content = response.content.decode()

        # Section heading.
        self.assertIn("More Resources for Jones", content)

        # Search buttons.
        self.assertIn("Search Case Law", content)
        self.assertIn("Search Federal Dockets", content)
        self.assertIn("Search Oral Arguments", content)

    async def test_person_search_buttons_have_nofollow(self) -> None:
        """Verify all search buttons include rel=nofollow for SEO."""
        response = await self.async_client.get(
            reverse(
                "view_person",
                args=[self.person.pk, self.person.slug],
            )
        )
        content = response.content.decode()
        self.assertEqual(content.count('rel="nofollow"'), 3)
