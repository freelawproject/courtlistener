"""
Unit tests for validating Fixture loading works with model logic
"""
from django.test import TestCase
from cl.judges.models import Judge


class FixtureTest(TestCase):
    """Used to validate certain aspects of various fixture files...
    ...mostly that they will properly load and support other tests."""

    fixtures = ['judge_judy.json']

    def test_does_judge_judy_fixture_load(self):
        """Can we load Judge Judy from a fixture?"""
        judge = Judge.objects.get(pk=1)
        self.assertEqual(judge.name_first, 'Judith')
        self.assertEqual(judge.name_last, 'Sheindlin')
