import datetime

from django import forms
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.template import Context, TemplateSyntaxError
from django.test import (
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)

from cl.custom_filters.decorators import check_honeypot
from cl.custom_filters.templatetags.component_tags import (
    _coerce_defer,
    _resolved_path,
)
from cl.custom_filters.templatetags.extras import (
    get_canonical_element,
    get_full_host,
    granular_date,
    humanize_number,
)
from cl.custom_filters.templatetags.partition_util import columns
from cl.custom_filters.templatetags.text_filters import (
    compress_whitespace,
    naturalduration,
    nbsp,
    oxford_join,
    underscore_to_space,
    v_wrapper,
)
from cl.custom_filters.templatetags.widget_tweaks import (
    add_class,
    append_attr,
    set_attr,
)
from cl.people_db.models import (
    GRANULARITY_DAY,
    GRANULARITY_MONTH,
    GRANULARITY_YEAR,
)


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
                msg=f"Could not convert {test} to dict.\n"
                f"  Got:      {actual_result}\n"
                f"  Expected: {expected_result}",
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
                msg=f"Error with weird value: {test}.\n"
                f"  Got:      {actual_result}\n"
                f"  Expected: {expected_result}",
            )


class DummyObject:
    date_start: object
    date_granularity_start: str


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

    def test_humanize_number(self) -> None:
        """Test multiple values for the humanize_number function

        Test cases includes multiple examples to see when the function rounds up or down a number, validate when a
        invalid value is passed and some edge cases.
        """
        test_cases: list[tuple[int | str, str]] = [
            # Input value, Expected output
            (500, "500"),
            (999, "999"),
            (1000, "1K"),
            (1040, "1K"),
            (1050, "1K"),
            (1060, "1.1K"),
            (1500, "1.5K"),
            (10987, "11K"),
            (999999, "1M"),  # Edge case for thousands
            (1000000, "1M"),
            (1500000, "1.5M"),
            (999999999, "1B"),  # Edge case for millions
            (1000000000, "1B"),
            (1500000000, "1.5B"),
            (2000000000, "2B"),
            ("3.1416", "3.1416"),
            ("abc", "abc"),
            ("", ""),
        ]

        for value, expected in test_cases:
            with self.subTest(value=value, expected=expected):
                result = humanize_number(value)
                self.assertEqual(
                    result,
                    expected,
                    msg=f"Number formatted incorrectly. Input: {value} - Result: {result} - Expected: {expected}",
                )


class TestTextFilters(SimpleTestCase):
    """Tests for text_filters.py template filters."""

    def test_nbsp_basic(self) -> None:
        """Test nbsp converts spaces to non-breaking spaces."""
        self.assertEqual(nbsp("hello world"), "hello&nbsp;world")
        self.assertEqual(nbsp("a b c"), "a&nbsp;b&nbsp;c")

    def test_nbsp_strips_whitespace(self) -> None:
        """Test nbsp strips leading/trailing whitespace."""
        self.assertEqual(nbsp("  hello  "), "hello")

    def test_nbsp_with_autoescape(self) -> None:
        """Test nbsp escapes HTML when autoescape is True."""
        result = nbsp("<script>alert('xss')</script>", autoescape=True)
        self.assertIn("&lt;script&gt;", result)
        self.assertNotIn("<script>", result)

    def test_nbsp_without_autoescape(self) -> None:
        """Test nbsp preserves HTML when autoescape is False."""
        result = nbsp("<b>bold</b>", autoescape=False)
        self.assertEqual(result, "<b>bold</b>")

    def test_v_wrapper_basic(self) -> None:
        """Test v_wrapper wraps ' v. ' with span."""
        result = v_wrapper("Smith v. Jones")
        self.assertIn('<span class="alt"> v. </span>', result)
        self.assertIn("Smith", result)
        self.assertIn("Jones", result)

    def test_v_wrapper_no_match(self) -> None:
        """Test v_wrapper with no ' v. ' pattern."""
        result = v_wrapper("Smith versus Jones")
        self.assertEqual(result, "Smith versus Jones")

    def test_v_wrapper_with_autoescape(self) -> None:
        """Test v_wrapper escapes HTML when autoescape is True."""
        result = v_wrapper("<b>Smith</b> v. Jones", autoescape=True)
        self.assertIn("&lt;b&gt;", result)

    def test_underscore_to_space_basic(self) -> None:
        """Test underscore_to_space replaces underscores."""
        self.assertEqual(underscore_to_space("hello_world"), "hello world")
        self.assertEqual(underscore_to_space("a_b_c"), "a b c")

    def test_underscore_to_space_with_autoescape(self) -> None:
        """Test underscore_to_space escapes HTML."""
        result = underscore_to_space("<script>_</script>", autoescape=True)
        self.assertIn("&lt;script&gt;", result)

    def test_compress_whitespace_basic(self) -> None:
        """Test compress_whitespace compresses multiple spaces."""
        self.assertEqual(compress_whitespace("hello   world"), "hello world")
        self.assertEqual(compress_whitespace("a  b  c"), "a b c")

    def test_compress_whitespace_newlines(self) -> None:
        """Test compress_whitespace handles newlines and tabs."""
        result = compress_whitespace("hello\n\n\tworld")
        self.assertEqual(result, "hello world")

    def test_compress_whitespace_with_autoescape(self) -> None:
        """Test compress_whitespace escapes HTML."""
        result = compress_whitespace("<b>hello</b>  world", autoescape=True)
        self.assertIn("&lt;b&gt;", result)


class TestComponentTags(SimpleTestCase):
    """Tests for component_tags.py template tags."""

    def test_coerce_defer_bool_true(self) -> None:
        """Test _coerce_defer with boolean True."""
        self.assertTrue(_coerce_defer(True, "test.js"))

    def test_coerce_defer_bool_false(self) -> None:
        """Test _coerce_defer with boolean False."""
        self.assertFalse(_coerce_defer(False, "test.js"))

    def test_coerce_defer_string_true(self) -> None:
        """Test _coerce_defer with string 'true'."""
        self.assertTrue(_coerce_defer("true", "test.js"))
        self.assertTrue(_coerce_defer("True", "test.js"))
        self.assertTrue(_coerce_defer("TRUE", "test.js"))

    def test_coerce_defer_string_false(self) -> None:
        """Test _coerce_defer with string 'false'."""
        self.assertFalse(_coerce_defer("false", "test.js"))
        self.assertFalse(_coerce_defer("False", "test.js"))

    def test_coerce_defer_invalid_value(self) -> None:
        """Test _coerce_defer raises error for invalid values."""
        with self.assertRaises(TemplateSyntaxError):
            _coerce_defer("yes", "test.js")
        with self.assertRaises(TemplateSyntaxError):
            _coerce_defer("1", "test.js")

    def test_resolved_path_with_extension(self) -> None:
        """Test _resolved_path preserves .js extension."""
        self.assertEqual(_resolved_path("test.js"), "test.js")
        self.assertEqual(_resolved_path("path/to/file.js"), "path/to/file.js")

    @override_settings(DEBUG=True)
    def test_resolved_path_without_extension_debug(self) -> None:
        """Test _resolved_path adds .js in debug mode."""
        self.assertEqual(_resolved_path("test"), "test.js")

    @override_settings(DEBUG=False)
    def test_resolved_path_without_extension_production(self) -> None:
        """Test _resolved_path adds .min.js in production mode."""
        self.assertEqual(_resolved_path("test"), "test.min.js")


class DummyForm(forms.Form):
    """A simple form for testing widget_tweaks filters."""

    name = forms.CharField()
    email = forms.EmailField()


class TestWidgetTweaks(SimpleTestCase):
    """Tests for widget_tweaks.py template filters."""

    def test_set_attr_basic(self) -> None:
        """Test set_attr adds an attribute to a field."""
        form = DummyForm()
        field = set_attr(form["name"], "placeholder:Enter name")
        html = field.as_widget()
        self.assertIn('placeholder="Enter name"', html)

    def test_set_attr_id(self) -> None:
        """Test set_attr can set the id attribute."""
        form = DummyForm()
        field = set_attr(form["name"], "id:custom-id")
        html = field.as_widget()
        self.assertIn('id="custom-id"', html)

    def test_append_attr_to_widget_attr(self) -> None:
        """Test append_attr appends to an existing widget attribute."""

        class FormWithClass(forms.Form):
            name = forms.CharField(
                widget=forms.TextInput(attrs={"class": "base"})
            )

        form = FormWithClass()
        field = append_attr(form["name"], "class:added")
        html = field.as_widget()
        self.assertIn("base added", html)

    def test_append_attr_new_attribute(self) -> None:
        """Test append_attr creates attribute if it doesn't exist."""
        form = DummyForm()
        field = append_attr(form["name"], "data-test:value")
        html = field.as_widget()
        self.assertIn('data-test="value"', html)

    def test_add_class_basic(self) -> None:
        """Test add_class adds a CSS class."""
        form = DummyForm()
        field = add_class(form["name"], "form-control")
        html = field.as_widget()
        self.assertIn("form-control", html)

    def test_add_class_multiple(self) -> None:
        """Test add_class can be chained."""
        form = DummyForm()
        field = add_class(form["name"], "class1")
        field = add_class(field, "class2")
        html = field.as_widget()
        self.assertIn("class1", html)
        self.assertIn("class2", html)


class TestPartitionUtil(SimpleTestCase):
    """Tests for partition_util.py template filters."""

    def test_columns_7_items_3_columns(self) -> None:
        """Test columns with 7 items into 3 columns."""
        result = columns(range(7), 3)
        expected = [[0, 3, 6], [1, 4], [2, 5]]
        self.assertEqual(result, expected)

    def test_columns_8_items_3_columns(self) -> None:
        """Test columns with 8 items into 3 columns."""
        result = columns(range(8), 3)
        expected = [[0, 3, 6], [1, 4, 7], [2, 5]]
        self.assertEqual(result, expected)

    def test_columns_9_items_3_columns(self) -> None:
        """Test columns with 9 items into 3 columns."""
        result = columns(range(9), 3)
        expected = [[0, 3, 6], [1, 4, 7], [2, 5, 8]]
        self.assertEqual(result, expected)

    def test_columns_10_items_3_columns(self) -> None:
        """Test columns with 10 items into 3 columns."""
        result = columns(range(10), 3)
        expected = [[0, 4, 8], [1, 5, 9], [2, 6], [3, 7]]
        self.assertEqual(result, expected)

    def test_columns_fewer_items_than_columns(self) -> None:
        """Test columns when items fewer than requested columns."""
        result = columns(range(4), 3)
        expected = [[0, 2], [1, 3]]
        self.assertEqual(result, expected)

    def test_columns_empty_list(self) -> None:
        """Test columns with empty list."""
        result: list[list[int]] = columns([], 3)
        self.assertEqual(result, [])

    def test_columns_single_item(self) -> None:
        """Test columns with single item."""
        result = columns([1], 3)
        self.assertEqual(result, [[1]])

    def test_columns_string_n(self) -> None:
        """Test columns accepts string for n parameter."""
        result = columns(range(6), "3")
        expected = [[0, 2, 4], [1, 3, 5]]
        self.assertEqual(result, expected)

    def test_columns_invalid_n(self) -> None:
        """Test columns with invalid n returns single column."""
        result = columns([1, 2, 3], "invalid")
        self.assertEqual(result, [[1, 2, 3]])


@override_settings(HONEYPOT_VALUE="")
class TestCheckHoneypot(TestCase):
    """Tests for check_honeypot decorator."""

    factory = RequestFactory()

    def test_valid_honeypot_passes(self) -> None:
        """Test that valid empty honeypot field passes."""

        @check_honeypot
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        request = self.factory.post("/", {"skip_me_if_alive": ""})
        response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")

    def test_missing_honeypot_field_returns_400(self) -> None:
        """Test that missing honeypot field returns 400 error."""

        @check_honeypot
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        request = self.factory.post("/", {"other_field": "value"})
        request.user = AnonymousUser()
        response = view(request)
        self.assertEqual(response.status_code, 400)

    def test_invalid_honeypot_value_returns_400(self) -> None:
        """Test that invalid honeypot value returns 400 error."""

        @check_honeypot
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        # POST with non-empty honeypot (bots fill this in)
        request = self.factory.post("/", {"skip_me_if_alive": "spam"})
        request.user = AnonymousUser()
        response = view(request)
        self.assertEqual(response.status_code, 400)

    def test_get_request_passes_through(self) -> None:
        """Test that GET requests pass through without honeypot check."""

        @check_honeypot
        def view(request: HttpRequest) -> HttpResponse:
            return HttpResponse("OK")

        request = self.factory.get("/")
        response = view(request)
        self.assertEqual(response.status_code, 200)

    def test_preserves_function_metadata(self) -> None:
        """Test that decorator preserves function name and docstring."""

        @check_honeypot
        def my_view(request: HttpRequest) -> HttpResponse:
            """My docstring."""
            return HttpResponse("OK")

        self.assertEqual(my_view.__name__, "my_view")
        self.assertEqual(my_view.__doc__, "My docstring.")
