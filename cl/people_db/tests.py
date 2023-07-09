from cl.people_db.factories import PersonWithChildrenFactory
from cl.people_db.models import Person, Position

from cl.tests.cases import TransactionTestCase


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
        self.assertEqual(new_person_with_position.id, positions_in_db[0].person_id)
