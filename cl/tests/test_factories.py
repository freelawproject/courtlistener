from cl.lib.management.commands.make_dev_data import FACTORIES
from cl.search.factories import DocketWithChildrenFactory
from cl.search.models import Docket, Opinion, OpinionCluster, Parenthetical
from cl.tests.cases import TestCase


class TestFactoryCreation(TestCase):
    """
    Tests to make sure that we can use our factories to generate data.
    """

    def test_making_docket(self) -> None:
        """Can we make a docket and have all its children get made?"""
        # Make sure things are empty at first
        self.assertEqual(Docket.objects.count(), 0)
        self.assertEqual(OpinionCluster.objects.count(), 0)
        self.assertEqual(Opinion.objects.count(), 0)
        self.assertEqual(Parenthetical.objects.count(), 0)

        # Make the docket
        DocketWithChildrenFactory.create()

        # Check for a docket, opinion cluster, opinion, and parenthetical
        num_dockets = Docket.objects.count()
        self.assertGreaterEqual(num_dockets, 1)
        self.assertGreaterEqual(OpinionCluster.objects.count(), 1)
        self.assertGreaterEqual(Opinion.objects.count(), 1)
        self.assertGreaterEqual(Parenthetical.objects.count(), 1)
        docket = Docket.objects.all()[0]
        FACTORIES[107].create(parent_id=docket.id)
        self.assertEqual(Docket.objects.count(), num_dockets)

    def test_making_specific_objects(self) -> None:
        """Can each of our basic factories be run properly?"""
        for Factory in FACTORIES.values():
            Factory.create()
