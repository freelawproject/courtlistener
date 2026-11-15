from django.urls import reverse
from nameparser import HumanName

from cl.people_db.factories import PersonFactory, PersonWithChildrenFactory
from cl.people_db.models import SUFFIX_LOOKUP, Person, Position
from cl.tests.cases import SimpleTestCase, TestCase, TransactionTestCase


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
        self.assertEqual(
            new_person_with_position.id, positions_in_db[0].person_id
        )


class PersonPageSearchButtons(TestCase):
    """Ensure that search buttons are displayed on the Person detail page."""

    @classmethod
    def setUpTestData(cls):
        cls.person = PersonFactory.create(name_last="Jones")

    async def test_person_detail_page_has_search_buttons(self) -> None:
        """Verify the person page shows search buttons with nofollow links."""
        response = await self.async_client.get(
            reverse(
                "view_person",
                args=[self.person.pk, self.person.slug],
            )
        )
        content = response.content.decode()

        # Section heading.
        self.assertIn("More Resources for Jones", content)

        # Search buttons.
        self.assertIn("Search Case Law", content)
        self.assertIn("Search Federal Dockets", content)
        self.assertIn("Search Oral Arguments", content)

    async def test_person_search_buttons_have_nofollow(self) -> None:
        """Verify all search buttons include rel=nofollow for SEO."""
        response = await self.async_client.get(
            reverse(
                "view_person",
                args=[self.person.pk, self.person.slug],
            )
        )
        content = response.content.decode()
        self.assertEqual(content.count('rel="nofollow"'), 3)


class HumanNameParseContractTest(SimpleTestCase):
    """Pin the `nameparser.HumanName` behaviour that judge lookups depend on.

    `lookup_judge_by_full_name` turns a parsed name into database filters
    (`Q(name_last__iexact=name.last)` and friends), so a change in how
    nameparser splits a string silently changes which judge is matched, or
    matches nobody at all. Nothing else in the suite exercises that contract,
    and the risky callers are management commands, so these assertions are the
    guard against a future nameparser upgrade regressing judge attribution.

    The expectations below were verified by diffing nameparser 1.1.3 against
    2.2.0 over a corpus of real judge names and real PACER `assigned_to_str`
    values. Only add a case here once you have confirmed the parse is the one
    the lookup actually needs -- not merely the one the current release emits.
    """

    def test_pacer_full_name_shapes(self) -> None:
        """`First M. Last` and `Last, First M.` must split as the lookup expects.

        These two shapes cover essentially all real PACER `assigned_to_str`
        values, which is what `cl.recap.mergers` feeds into the lookup.
        """
        cases = [
            # (input, first, middle, last, suffix)
            ("John Smith", "John", "", "Smith", ""),
            ("John M. Smith", "John", "M.", "Smith", ""),
            ("Gonzalo P. Curiel", "Gonzalo", "P.", "Curiel", ""),
            ("Smith, John", "John", "", "Smith", ""),
            ("Smith, John M.", "John", "M.", "Smith", ""),
            ("Ketanji Brown Jackson", "Ketanji", "Brown", "Jackson", ""),
            ("Hon. John M. Smith", "John", "M.", "Smith", ""),
            ("John Smith, Jr.", "John", "", "Smith", "Jr."),
            ("John M. Smith, Jr.", "John", "M.", "Smith", "Jr."),
        ]
        for name, first, middle, last, suffix in cases:
            with self.subTest(name=name):
                hn = HumanName(name)
                self.assertEqual(hn.first, first)
                self.assertEqual(hn.middle, middle)
                self.assertEqual(hn.last, last)
                self.assertEqual(hn.suffix, suffix)

    def test_particle_surnames_keep_the_particle(self) -> None:
        """A particle surname must stay whole when a first name is present.

        Real judges with these surnames are stored with the particle in
        `name_last` (e.g. "Van Dyke", "de Alba"), so dropping it from the
        parse would make `name_last__iexact` miss them entirely.
        """
        cases = [
            ("Lawrence Van Dyke", "Lawrence", "Van Dyke"),
            ("Judge Lawrence Van Dyke", "Lawrence", "Van Dyke"),
            ("Ana Isabel de Alba", "Ana", "de Alba"),
            ("Andre De La Cruz", "Andre", "De La Cruz"),
            ("Janis Van Meerveld", "Janis", "Van Meerveld"),
            ("Judith A. Vander Lans", "Judith", "Vander Lans"),
            ("Margaret McKeown", "Margaret", "McKeown"),
            ("Sandra Day O'Connor", "Sandra", "O'Connor"),
        ]
        for name, first, last in cases:
            with self.subTest(name=name):
                hn = HumanName(name)
                self.assertEqual(hn.first, first)
                self.assertEqual(hn.last, last)

    def test_trailing_judicial_role_is_not_a_first_name(self) -> None:
        """A trailing role must not be parsed into `first`.

        If the role lands in `first`, the lookup adds a bogus
        `name_first__iexact` filter and returns None instead of the judge.
        nameparser 1.1.3 put a bare "Judge" in `first` for all of these;
        2.2.0 reads the whole phrase as a title, which is what we rely on.
        """
        for name in [
            "Smith, District Judge",
            "Smith, Chief Judge",
            "Smith, Magistrate Judge",
            "Smith, Senior Judge",
        ]:
            with self.subTest(name=name):
                hn = HumanName(name)
                self.assertEqual(hn.last, "Smith")
                self.assertEqual(hn.first, "")

    def test_circuit_judge_role_is_still_misparsed(self) -> None:
        """Document that "Circuit Judge" is not recognised as a title.

        Both 1.1.3 and 2.2.0 parse "Smith, Circuit Judge" as first="Circuit",
        so this is a long-standing limitation rather than an upgrade
        regression. It is largely inert today because appellate bylines reach
        the database through `extract_judge_last_name`, which tokenises the
        string instead of parsing it as a full name. This test exists so that
        a future nameparser release fixing it shows up as a failure here
        rather than as a silent change in judge attribution.
        """
        hn = HumanName("Smith, Circuit Judge")
        self.assertEqual(hn.last, "Smith")
        self.assertEqual(hn.first, "Circuit")

    def test_assigning_last_name_leaves_other_fields_empty(self) -> None:
        """`HumanName()` plus a `last` assignment must set nothing else.

        `lookup_judge_by_last_name` and `lookup_judges_by_last_name_list` build
        a name this way from `extract_judge_last_name` output. Any other field
        that got populated would add an unintended filter to the query.
        """
        for last_name in [
            "smith",
            "van dyke",
            "o'brien",
            "de la cruz",
            "SMITH",
        ]:
            with self.subTest(last_name=last_name):
                hn = HumanName()
                hn.last = last_name
                self.assertEqual(hn.last, last_name)
                self.assertEqual(hn.first, "")
                self.assertEqual(hn.middle, "")
                self.assertEqual(hn.suffix, "")
                self.assertEqual(hn.title, "")

    def test_suffixes_map_to_the_suffix_lookup(self) -> None:
        """Parsed suffixes must be keys `SUFFIX_LOOKUP` recognises.

        `lookup_judge_by_full_name` only applies a suffix filter when
        `SUFFIX_LOOKUP.get(name.suffix.lower())` resolves, so a suffix parsed
        into an unexpected form silently drops that filter.
        """
        for name, expected in [
            ("John Smith Jr.", "jr."),
            ("John Smith, Jr.", "jr."),
            ("John Smith Sr.", "sr."),
            ("John Smith III", "iii"),
            ("John Smith, III", "iii"),
        ]:
            with self.subTest(name=name):
                hn = HumanName(name)
                self.assertEqual(hn.suffix.lower(), expected)
                self.assertIn(hn.suffix.lower(), SUFFIX_LOOKUP)
