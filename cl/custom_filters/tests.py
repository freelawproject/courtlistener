import datetime
from django.template import Context
from django.test import TestCase, RequestFactory

from cl.custom_filters.templatetags.extras import get_full_host, granular_date
from cl.custom_filters.templatetags.text_filters import naturalduration
from cl.people_db.models import GRANULARITY_DAY, GRANULARITY_MONTH, \
    GRANULARITY_YEAR


class TestNaturalDuration(TestCase):

    def test_conversion_to_strings(self):
        """Can we get the str output right?"""
        test_cases = (
            ('01', '1'),
            ('61', '1:01'),
            ('3601', '1:00:01'),
            ('86401', '1:00:00:01'),
            ('90061', '1:01:01:01'),
        )
        for test, result in test_cases:
            self.assertEqual(
                naturalduration(test),
                result,
            )

    def test_input_as_int_or_str(self):
        """Can we take input as either an int or a str?"""
        test_cases = (
            ('62', '1:02'),
            (62, '1:02'),
        )
        for test, result in test_cases:
            self.assertEqual(
                naturalduration(test),
                result,
            )

    def test_conversion_to_dict(self):
        """Can we get the numbers right when it's a dict?"""
        test_cases = (
            ('01', {'d': 0, 'h': 0, 'm': 0, 's': 1}),
            ('61', {'d': 0, 'h': 0, 'm': 1, 's': 1}),
            ('3601', {'d': 0, 'h': 1, 'm': 0, 's': 1}),
            ('86401', {'d': 1, 'h': 0, 'm': 0, 's': 1}),
            ('90061', {'d': 1, 'h': 1, 'm': 1, 's': 1}),
        )
        for test, expected_result in test_cases:
            actual_result = naturalduration(test, as_dict=True)
            self.assertEqual(
                actual_result,
                expected_result,
                msg="Could not convert %s to dict.\n"
                    "  Got:      %s\n"
                    "  Expected: %s" % (test, actual_result, expected_result)
            )

    def test_weird_values(self):
        test_cases = (
            (None, '0'),   # None
            (0, '0'),      # Zero
            (22.2, '22'),  # Float
        )
        for test, expected_result in test_cases:
            actual_result = naturalduration(test)
            self.assertEqual(
                actual_result,
                expected_result,
                msg="Error with weird value: %s.\n"
                    "  Got:      %s\n"
                    "  Expected: %s" % (test, actual_result, expected_result)
            )


class TestExtras(TestCase):

    factory = RequestFactory()

    def test_get_full_host(self):
        """Does get_full_host return the right values"""
        c = Context({'request': self.factory.request()})
        self.assertEqual(
            get_full_host(c),
            'http://testserver',
        )

        self.assertEqual(
            get_full_host(c, username='billy', password='crystal'),
            'http://billy:crystal@testserver',
        )

    def test_granular_dates(self):
        """Can we get the correct values for granular dates?"""
        d = datetime.date(year=1982, month=6, day=9)
        q_a = (
            ((d, GRANULARITY_DAY, True), "1982-06-09"),
            ((d, GRANULARITY_MONTH, True), "1982-06"),
            ((d, GRANULARITY_YEAR, True), "1982"),
            ((d, GRANULARITY_DAY, False), "June 9, 1982"),
            ((d, GRANULARITY_MONTH, False), "June, 1982"),
            ((d, GRANULARITY_YEAR, False), "1982"),
        )
        for q, a in q_a:
            result = granular_date(*q)
            self.assertEqual(
                result,
                a,
                msg=("Incorrect granular date conversion. Got: %s instead of "
                     "%s" % (result, a))
            )

    def test_old_granular_dates(self):
        """Can we parse dates older than 1900 without strftime barfing?"""
        d = datetime.date(year=1899, month=1, day=23)
        try:
            granular_date(d)
        except ValueError:
            self.fail("Granular date failed while parsing date prior to 1900.")
