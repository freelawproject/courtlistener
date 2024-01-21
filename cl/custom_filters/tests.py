import datetime

from django.template import Context
from django.test import RequestFactory

from cl.custom_filters.templatetags.extras import (
    get_canonical_element,
    get_full_host,
    granular_date,
)
from cl.custom_filters.templatetags.text_filters import (
    naturalduration,
    oxford_join,
)
from cl.people_db.models import (
    GRANULARITY_DAY,
    GRANULARITY_MONTH,
    GRANULARITY_YEAR,
)
from cl.tests.cases import SimpleTestCase


class TestOxfordJoinFilter(SimpleTestCase):
    def test_oxford(self) -> None:
        # Zero items
        self.assertEqual(oxford_join([]), "")

        # One item
        self.assertEqual(oxford_join(["a"]), "a")

        # Two items
        self.assertEqual(oxford_join(["a", "b"]), "a and b")

        # Three items
        self.assertEqual(oxford_join(["a", "b", "c"]), "a, b, and c")

        # Custom separator
        self.assertEqual(
            oxford_join(["a", "b", "c"], separator=";"), "a; b; and c"
        )

        # Custom conjunction(self) -> None:
        self.assertEqual(
            oxford_join(["a", "b", "c"], conjunction="or"), "a, b, or c"
        )


class TestNaturalDuration(SimpleTestCase):
    def test_conversion_to_strings(self) -> None:
        """Can we get the str output right?"""
        test_cases = (
            ("01", "1"),
            ("61", "1:01"),
            ("3601", "1:00:01"),
            ("86401", "1:00:00:01"),
            ("90061", "1:01:01:01"),
        )
        for test, result in test_cases:
            self.assertEqual(naturalduration(test), result)

    def test_input_as_int_or_str(self) -> None:
        """Can we take input as either an int or a str?"""
        test_cases = (
            ("62", "1:02"),
            (62, "1:02"),
        )
        for test, result in test_cases:
            self.assertEqual(naturalduration(test), result)

    def test_conversion_to_dict(self) -> None:
        """Can we get the numbers right when it's a dict?"""
        test_cases = (
            ("01", {"d": 0, "h": 0, "m": 0, "s": 1}),
            ("61", {"d": 0, "h": 0, "m": 1, "s": 1}),
            ("3601", {"d": 0, "h": 1, "m": 0, "s": 1}),
            ("86401", {"d": 1, "h": 0, "m": 0, "s": 1}),
            ("90061", {"d": 1, "h": 1, "m": 1, "s": 1}),
        )
        for test, expected_result in test_cases:
            actual_result = naturalduration(test, as_dict=True)
            self.assertEqual(
                actual_result,
                expected_result,
                msg="Could not convert %s to dict.\n"
                "  Got:      %s\n"
                "  Expected: %s" % (test, actual_result, expected_result),
            )

    def test_weird_values(self) -> None:
        test_cases = (
            (None, "0"),  # None
            (0, "0"),  # Zero
            (22.2, "22"),  # Float
        )
        for test, expected_result in test_cases:
            actual_result = naturalduration(test)
            self.assertEqual(
                actual_result,
                expected_result,
                msg="Error with weird value: %s.\n"
                "  Got:      %s\n"
                "  Expected: %s" % (test, actual_result, expected_result),
            )


class DummyObject:
    pass


class TestExtras(SimpleTestCase):
    factory = RequestFactory()

    def test_get_full_host(self) -> None:
        """Does get_full_host return the right values"""
        c = Context({"request": self.factory.request()})
        self.assertEqual(get_full_host(c), "http://testserver")

        self.assertEqual(
            get_full_host(c, username="billy", password="crystal"),
            "http://billy:crystal@testserver",
        )

    def test_get_canonical_element(self) -> None:
        """Do we get a simple canonical element?"""

        c = Context({"request": self.factory.get("/some-path/")})
        self.assertEqual(
            get_canonical_element(c),
            '<link rel="canonical" href="http://testserver/some-path/" />',
        )

    def test_granular_dates(self) -> None:
        """Can we get the correct values for granular dates?"""
        q_a = (
            ((GRANULARITY_DAY, True), "1982-06-09"),
            ((GRANULARITY_MONTH, True), "1982-06"),
            ((GRANULARITY_YEAR, True), "1982"),
            ((GRANULARITY_DAY, False), "June 9, 1982"),
            ((GRANULARITY_MONTH, False), "June, 1982"),
            ((GRANULARITY_YEAR, False), "1982"),
        )
        d = datetime.date(year=1982, month=6, day=9)
        obj = DummyObject()
        for q, a in q_a:
            setattr(obj, "date_start", d)
            setattr(obj, "date_granularity_start", q[0])
            result = granular_date(obj, "date_start", *q)
            self.assertEqual(
                result,
                a,
                msg=(
                    f"Incorrect granular date conversion. Got: {result} instead of {a}"
                ),
            )

    def test_old_granular_dates(self) -> None:
        """Can we parse dates older than 1900 without strftime barfing?"""
        obj = DummyObject()
        d = datetime.date(year=1899, month=1, day=23)
        obj.date_start = d
        obj.date_granularity_start = GRANULARITY_DAY

        try:
            granular_date(obj, "date_start")
        except ValueError:
            self.fail("Granular date failed while parsing date prior to 1900.")

    def test_granularity_missing_date(self) -> None:
        """Does granularity code work with missing data?"""
        obj = DummyObject()
        d = ""
        obj.date_start = d
        obj.date_granularity_start = GRANULARITY_DAY

        # Missing date value
        self.assertEqual(granular_date(obj, "date_start"), "Unknown")

    def test_granularity_dict_or_obj(self) -> None:
        """Can you pass a dict or an object and will both work?

        This is important because some objects in Django templates are dicts...
        others are objects.
        """
        obj = {}
        d = ""
        obj["date_start"] = d
        obj["date_granularity_start"] = GRANULARITY_DAY

        self.assertEqual(granular_date(obj, "date_start"), "Unknown")
