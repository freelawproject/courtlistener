import pytest

from cl.stats.models import Stat
from cl.stats.utils import get_milestone_range, tally_stat
from cl.tests.cases import TestCase


class MilestoneTests(TestCase):
    def test_milestone_ranges(self) -> None:
        numbers = get_milestone_range("XS", "SM")
        self.assertEqual(numbers[0], 1e1)
        self.assertEqual(numbers[-1], 5e4)


@pytest.mark.django_db
class StatTests(TestCase):
    def setUp(self) -> None:
        Stat.objects.all().delete()

    def tearDown(self) -> None:
        Stat.objects.all().delete()

    def test_tally_a_stat(self) -> None:
        count = tally_stat("test")
        self.assertEqual(count, 1)

    def test_increment_a_stat(self) -> None:
        count = tally_stat("test2")
        self.assertEqual(count, 1)
        count = tally_stat("test2")
        self.assertEqual(count, 2)

    def test_increment_by_two(self) -> None:
        count = tally_stat("test3", inc=2)
        self.assertEqual(count, 2)
        count = tally_stat("test3", inc=2)
        self.assertEqual(count, 4)
