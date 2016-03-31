"""
Unit tests for validating Fixture loading works with model logic
"""
from django.test import TestCase
from cl.people_db.models import Person


class FixtureTest(TestCase):
    """Used to validate certain aspects of various fixture files...
    ...mostly that they will properly load and support other tests."""

    fixtures = ['judge_judy.json']

    def test_does_judge_judy_fixture_load(self):
        """Can we load Judge Judy from a fixture?"""
        judy = Person.objects.get(pk=2)
        self.assertEqual(judy.name_first, 'Judith')
        self.assertEqual(judy.name_last, 'Sheindlin')
