import factory
from django.db.models import signals

from cl.lib.management.commands.make_dev_data import FACTORIES
from cl.search.factories import DocketWithChildrenFactory
from cl.search.models import Docket, Opinion, OpinionCluster, Parenthetical
from cl.tests.cases import TestCase


class TestFactoryCreation(TestCase):
    """
    Tests to make sure that we can use our factories to generate data.
    """

    @factory.django.mute_signals(signals.pre_save, signals.post_save)
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
        self.assertGreaterEqual(Docket.objects.count(), 1)
        self.assertGreaterEqual(OpinionCluster.objects.count(), 1)
        self.assertGreaterEqual(Opinion.objects.count(), 1)
        self.assertGreaterEqual(Parenthetical.objects.count(), 1)

    @factory.django.mute_signals(signals.pre_save, signals.post_save)
    def test_making_specific_objects(self) -> None:
        """Can each of our basic factories be run properly?"""
        for Factory in FACTORIES.values():
            Factory.create()
