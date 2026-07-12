import datetime

from django import forms
from django.template import Context
from django.test import RequestFactory, SimpleTestCase

from cl.custom_filters.templatetags.extras import (
    get_canonical_element,
    get_full_host,
    get_item,
    granular_date,
    highlight_query,
    humanize_number,
    render_field_with_id,
)
from cl.custom_filters.templatetags.svg_tags import svg
from cl.custom_filters.templatetags.text_filters import (
    naturalduration,
    oxford_join,
)
from cl.people_db.models import (
    GRANULARITY_DAY,
    GRANULARITY_MONTH,
    GRANULARITY_YEAR,
)
from cl.search.forms import CorpusSearchForm


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
    pass


class SimpleForm(forms.Form):
    """Helper form for testing get_item and render_field_with_id"""

    name = forms.CharField()
    email = forms.EmailField()


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

    def test_humanize_number(self):
        """Test multiple values for the humanize_number function

        Test cases includes multiple examples to see when the function rounds up or down a number, validate when a
        invalid value is passed and some edge cases.
        """
        test_cases = [
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

    def test_get_item_with_various_types(self):
        """Test get_item retrieves values from different object types

        Validates:
        - Dict key access (string keys, returns value or empty string)
        - List index access (integer indices, returns item or empty string)
        - Form field access (returns BoundField object)
        - Invalid key handling (None returns empty string)
        """
        # Test with dict
        test_dict = {"foo": "bar", "num": 123}
        self.assertEqual(get_item(test_dict, "foo"), "bar")
        self.assertEqual(get_item(test_dict, "num"), 123)
        self.assertEqual(get_item(test_dict, "missing"), "")

        # Test with list
        test_list = ["a", "b", "c"]
        self.assertEqual(get_item(test_list, 0), "a")
        self.assertEqual(get_item(test_list, 2), "c")
        self.assertEqual(get_item(test_list, 10), "")

        # Test with form
        form = SimpleForm()
        name_field = get_item(form, "name")
        self.assertIsNotNone(name_field)
        self.assertEqual(name_field.name, "name")

        # Test with invalid key type
        self.assertEqual(get_item(test_dict, None), "")

    def test_render_field_with_custom_id(self):
        """Test render_field_with_id renders form fields with custom IDs

        Validates:
        - Custom ID attribute is applied to rendered HTML
        - Field name attribute is preserved
        - Field type attribute is correct (text, email, etc.)
        - Default Django ID (id_fieldname) is NOT present
        - Works with form_prefix pattern (desktop_namespace_field)
        """
        form = SimpleForm()

        # Test text input with custom ID
        rendered = render_field_with_id(form["name"], "custom_name_id")
        self.assertIn('id="custom_name_id"', rendered)
        self.assertIn('name="name"', rendered)
        self.assertIn('type="text"', rendered)

        # Test email input with custom ID
        rendered = render_field_with_id(form["email"], "my_email_field")
        self.assertIn('id="my_email_field"', rendered)
        self.assertIn('name="email"', rendered)
        self.assertIn('type="email"', rendered)

        # Test with prefix-style ID (like in our form_prefix pattern)
        rendered = render_field_with_id(form["name"], "desktop_opinions_name")
        self.assertIn('id="desktop_opinions_name"', rendered)

        # Ensure default ID is NOT present when custom ID is provided
        rendered = render_field_with_id(form["name"], "custom_id")
        self.assertNotIn('id="id_name"', rendered)

    def test_render_field_with_corpus_search_form(self):
        """Test render_field_with_id works with actual CorpusSearchForm

        Validates all field types used in corpus search:
        - TextInput fields (case_name, docket_number, etc.)
        - Select/ChoiceField (dob_state, selection_method, etc.)
        - CheckboxInput (available_only)

        Ensures custom IDs are applied and default Django IDs are removed.
        """
        form = CorpusSearchForm()

        # Test TextInput fields
        text_fields = [
            "case_name",
            "docket_number",
            "judge",
            "citation",
            "party_name",
            "atty_name",
            "name",
            "school",
            "appointer",
        ]

        for field_name in text_fields:
            with self.subTest(field=field_name):
                custom_id = f"test_{field_name}_id"
                rendered = render_field_with_id(form[field_name], custom_id)
                self.assertIn(f'id="{custom_id}"', rendered)
                self.assertIn(f'name="{field_name}"', rendered)
                # Ensure default Django ID is not present
                self.assertNotIn(f'id="id_{field_name}"', rendered)

        # Test Select/ChoiceField
        select_fields = [
            "dob_state",
            "selection_method",
            "political_affiliation",
        ]

        for field_name in select_fields:
            with self.subTest(field=field_name):
                custom_id = f"mobile_judges_{field_name}"
                rendered = render_field_with_id(form[field_name], custom_id)
                self.assertIn(f'id="{custom_id}"', rendered)
                self.assertIn(f'name="{field_name}"', rendered)
                self.assertIn("<select", rendered)

        # Test CheckboxInput
        checkbox_id = "desktop_recap_available_only"
        rendered = render_field_with_id(form["available_only"], checkbox_id)
        self.assertIn(f'id="{checkbox_id}"', rendered)
        self.assertIn('name="available_only"', rendered)
        self.assertIn('type="checkbox"', rendered)

    def test_get_item_with_corpus_search_form(self):
        """Test get_item filter works with actual CorpusSearchForm

        Validates field access for all field types in corpus search:
        - Text fields return BoundField with correct name
        - Select fields return BoundField with correct name
        - Checkbox fields return BoundField with correct name
        - Non-existent fields return empty string
        """
        form = CorpusSearchForm()

        # Test accessing various field types
        case_name_field = get_item(form, "case_name")
        self.assertIsNotNone(case_name_field)
        self.assertEqual(case_name_field.name, "case_name")

        # Test select field
        dob_state_field = get_item(form, "dob_state")
        self.assertIsNotNone(dob_state_field)
        self.assertEqual(dob_state_field.name, "dob_state")

        # Test checkbox field
        available_field = get_item(form, "available_only")
        self.assertIsNotNone(available_field)
        self.assertEqual(available_field.name, "available_only")

        # Test non-existent field
        missing_field = get_item(form, "non_existent_field")
        self.assertEqual(missing_field, "")


class TestHighlightQuery(SimpleTestCase):
    """Tests for the highlight_query template filter."""

    def test_quoted_phrase_highlighted(self) -> None:
        """Quoted phrases are highlighted as a unit."""
        result = highlight_query(
            "The court applied fair use analysis.",
            '"fair use"',
        )
        self.assertIn("<mark>fair use</mark>", result)

    def test_unquoted_words_not_highlighted(self) -> None:
        """Unquoted words are NOT highlighted (they drive semantic
        ranking, not keyword matching)."""
        result = highlight_query(
            "The copyright holder filed suit.",
            "copyright holder",
        )
        self.assertNotIn("<mark>", str(result))

    def test_case_insensitive(self) -> None:
        """Matching is case-insensitive."""
        result = highlight_query(
            "Fair Use is a defense.",
            '"fair use"',
        )
        self.assertIn("<mark>Fair Use</mark>", result)

    def test_html_tags_not_highlighted(self) -> None:
        """Phrases inside HTML tag attributes are left alone."""
        result = highlight_query(
            'Click <a href="fair use">here</a> for fair use info.',
            '"fair use"',
        )
        # The phrase in the tag attribute should be untouched
        self.assertIn('<a href="fair use">', result)
        # The phrase in text content should be highlighted
        self.assertIn("<mark>fair use</mark> info", result)

    def test_only_quoted_phrases_highlighted_in_mixed_query(self) -> None:
        """Only quoted phrases are highlighted; unquoted words ignored."""
        result = highlight_query(
            "The fair use doctrine protects transformative works.",
            '"fair use" transformative',
        )
        self.assertIn("<mark>fair use</mark>", result)
        self.assertNotIn("<mark>transformative</mark>", str(result))

    def test_empty_query_returns_unchanged(self) -> None:
        """Empty query returns text as-is."""
        text = "Some text here."
        result = highlight_query(text, "")
        self.assertEqual(str(result), text)

    def test_no_quotes_returns_safe_unchanged(self) -> None:
        """Query without quotes returns safe, unhighlighted text."""
        result = highlight_query("Nothing to see here.", "semantic only query")
        self.assertNotIn("<mark>", str(result))

    def test_html_entities_in_text(self) -> None:
        """Ampersands in text (already escaped) are handled properly."""
        result = highlight_query("AT&amp;T filed the brief.", '"AT&T"')
        self.assertIn("<mark>AT&amp;T</mark>", result)

    def test_read_more_html_preserved(self) -> None:
        """HTML from read_more filter is not corrupted."""
        text = (
            'word1 word2 <span class="read-more">&hellip;'
            '<a href="#"><i class="fa fa-plus-square gray"'
            ' title="Show All"></i></a></span>'
            '<span class="more hidden">fair use word4</span>'
        )
        result = highlight_query(text, '"fair use"')
        # The read_more structure should be intact
        self.assertIn('<span class="read-more">', result)
        self.assertIn('<span class="more hidden">', result)
        # The phrase inside the hidden span should be highlighted
        self.assertIn("<mark>fair use</mark>", result)

    def test_multiple_occurrences(self) -> None:
        """All occurrences of a quoted phrase are highlighted."""
        result = highlight_query(
            "Fair use applies. Courts consider fair use broadly.",
            '"fair use"',
        )
        self.assertEqual(str(result).count("<mark>"), 2)

    def test_whitespace_only_phrase_ignored(self) -> None:
        """Whitespace-only quoted phrases are not highlighted."""
        result = highlight_query(
            "The copyright holder filed suit.",
            'copyright " "',
        )
        self.assertNotIn("<mark>", str(result))

    def test_word_boundaries_prevent_partial_match(self) -> None:
        """Quoted phrases only match at word boundaries."""
        result = highlight_query(
            "She has experience in the field.",
            '"per"',
        )
        self.assertNotIn("<mark>", str(result))

    def test_word_boundaries_match_whole_word(self) -> None:
        """Whole-word matches at word boundaries still work."""
        result = highlight_query(
            "The per curiam opinion was brief.",
            '"per"',
        )
        self.assertIn("<mark>per</mark>", result)

    def test_longer_phrases_matched_first(self) -> None:
        """Longer phrases take priority over shorter sub-phrases."""
        result = highlight_query(
            "The married couple filed jointly.",
            '"married" "married couple"',
        )
        self.assertIn("<mark>married couple</mark>", result)


class TestSvgTag(SimpleTestCase):
    """Tests for the svg template tag."""

    def test_svg_renders_without_escaping(self) -> None:
        """Ensure svg tag returns unescaped SVG markup."""
        result = svg("heart")
        # Should contain actual SVG tags, not HTML-escaped versions
        self.assertIn("<svg", result)
        self.assertNotIn("&lt;svg", result)

    def test_svg_not_found_in_debug(self) -> None:
        """Missing SVG returns error message in debug mode."""
        with self.settings(DEBUG=True):
            result = svg("nonexistent_svg_that_does_not_exist")
            self.assertIn("not found", result)

    def test_svg_not_found_in_production(self) -> None:
        """Missing SVG returns empty string in production."""
        with self.settings(DEBUG=False):
            result = svg("nonexistent_svg_that_does_not_exist")
            self.assertEqual(result, "")
