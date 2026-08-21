"""Tests for the New York Court of Appeals (Court-PASS) scrape schema and the
vocabulary mapping between Juriscraper and CourtListener.

Two failure modes are covered here, because the whole design turns on telling
them apart:

* the Court stated nothing, which is stored as `UNKNOWN`;
* the Court stated something a vocabulary does not cover, which is stored as
  `UNASSIGNED` and is the signal that a member needs adding.

Juriscraper reports both as `None`, so the schema is what separates them, using
the raw string the Court printed where the value alone cannot say. Neither may
ever cost a docket its merge.
"""

from typing import cast

from juriscraper.state.docket import DocketEntryType
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    CourtVocabulary,
    FilingDocType,
    FilingRole,
    FilingType,
    IssueCategory,
    IssueSubcategory,
)

from cl.corpus_importer.state.new_york.nycourts_gov import (
    NYCoAFile,
    NYCoAIssue,
    NYCoDocketEntry,
    Unclassified,
)
from cl.corpus_importer.state.new_york.utils import (
    issue_code,
    make_docket_number_core,
    mirrored_code,
)
from cl.search.state.new_york.vocabularies import (
    UNASSIGNED,
    UNKNOWN,
)
from cl.search.state.new_york.vocabularies import (
    FilingDocType as MirroredFilingDocType,
)
from cl.search.state.new_york.vocabularies import (
    FilingRole as MirroredFilingRole,
)
from cl.search.state.new_york.vocabularies import (
    FilingType as MirroredFilingType,
)
from cl.tests.cases import SimpleTestCase


class _UnmirroredRole(CourtVocabulary):
    """A vocabulary member no CourtListener mirror defines.

    Stands for an upstream addition that has not been mirrored yet, which is
    the case `_mirrored_code` has to survive.
    """

    NOT_MIRRORED = "Not Mirrored", 900, "Not Mirrored"


class DocketNumberTest(SimpleTestCase):
    """Tests for normalizing a Court of Appeals docket number."""

    def test_normalizes_a_docket_number(self) -> None:
        """Is the Court's own format reduced to a matchable core?"""
        for stated, expected in (
            ("APL-2024-00177", "apl202400177"),
            ("apl-2024-00177", "apl202400177"),
            ("  APL-2024-00177  ", "apl202400177"),
            # The case type comes from a dropdown, so any short prefix goes.
            ("CTQ-2023-00004", "ctq202300004"),
            ("JCR-2022-000012", "jcr2022000012"),
        ):
            with self.subTest(stated=stated):
                self.assertEqual(make_docket_number_core(stated), expected)

    def test_finds_a_docket_number_in_surrounding_text(self) -> None:
        """Court-PASS prints the number inside a longer caption. Is it still
        found?"""
        self.assertEqual(
            make_docket_number_core("Case No. APL-2024-00177 (Part 2)"),
            "apl202400177",
        )

    def test_picks_one_of_several_deterministically(self) -> None:
        """A caption naming two numbers has to resolve the same way on every
        scrape, or the docket moves between rows."""
        both = "APL-2024-00177 and APL-2023-00001"
        self.assertEqual(make_docket_number_core(both), "apl202300001")
        self.assertEqual(
            make_docket_number_core(both),
            make_docket_number_core(
                "APL-2023-00001 and APL-2024-00177",
            ),
            "The order the caption names them in must not matter.",
        )

    def test_unusable_docket_number(self) -> None:
        """A string holding no Court of Appeals number yields nothing, so the
        merger can refuse the docket rather than write one it can never match
        again."""
        for stated in ("Motion No. 12", "", "   ", "SC1983-2014", "garbage"):
            with self.subTest(stated=stated):
                self.assertEqual(make_docket_number_core(stated), "")


class VocabularyMappingTest(SimpleTestCase):
    """Tests for the codes CourtListener stores for the schema's readings."""

    def test_mirrored_members(self) -> None:
        """Is each mirrored vocabulary's member stored under its own published
        code?"""
        for label, mirror, member in (
            ("filing type", MirroredFilingType, FilingType.APPELLANT_BRIEF),
            ("filing role", MirroredFilingRole, FilingRole.APPELLANT),
            ("document type", MirroredFilingDocType, FilingDocType.BRIEF),
        ):
            with self.subTest(label):
                self.assertEqual(mirrored_code(mirror, member), member.code)

    def test_mirrored_reserved_readings(self) -> None:
        """Both readings that name no member are stored under the code reserved
        for them, in every mirror. Are they?"""
        for mirror in (
            MirroredFilingType,
            MirroredFilingRole,
            MirroredFilingDocType,
        ):
            with self.subTest(mirror.__name__):
                self.assertEqual(
                    mirrored_code(mirror, Unclassified.UNKNOWN), UNKNOWN
                )
                self.assertEqual(
                    mirrored_code(mirror, Unclassified.UNASSIGNED), UNASSIGNED
                )

    def test_unmirrored_member_is_unassigned(self) -> None:
        """A member Juriscraper has and CourtListener has not mirrored yet must
        cost the field rather than raising, so the docket still merges."""
        self.assertEqual(
            mirrored_code(
                MirroredFilingRole,
                cast(CourtVocabulary, _UnmirroredRole.NOT_MIRRORED),
            ),
            UNASSIGNED,
        )

    def test_issue_codes(self) -> None:
        """The issue vocabularies are too large to mirror, so their codes are
        Juriscraper's own. Are those stored, with the reserved codes for the two
        readings that name no member?"""
        for label, member, expected in (
            ("category", IssueCategory.CRIMES, IssueCategory.CRIMES.code),
            (
                "subcategory",
                IssueSubcategory.SENTENCE,
                IssueSubcategory.SENTENCE.code,
            ),
            ("nothing stated", Unclassified.UNKNOWN, UNKNOWN),
            ("not covered", Unclassified.UNASSIGNED, UNASSIGNED),
        ):
            with self.subTest(label):
                self.assertEqual(issue_code(member), expected)


class ClassifiedVocabularyTest(SimpleTestCase):
    """Tests for the scrape schema's reading of Court-PASS's own wording.

    Refusing a value the scraper's vocabularies do not cover would fail the
    whole model, which costs every filing, party and issue on the case over one
    unrecognized string. The schema reports `UNASSIGNED` instead, which the
    mergers store as the signal that a member needs adding, and keeps `UNKNOWN`
    for what the Court never stated.
    """

    def test_entry_keeps_covered_values(self) -> None:
        """Does a filing stating values the vocabularies cover classify them?"""
        entry = NYCoDocketEntry(
            docket_entry_id="e:appellant-brief:smith:1",
            entry_type=DocketEntryType.UNKNOWN,
            attachments=[],
            raw_filing_type="Appellant Brief",
            entry_filing_type="Appellant Brief",
            entry_role="appellant",
            entry_doctype="brf",
        )

        self.assertEqual(entry.entry_filing_type, FilingType.APPELLANT_BRIEF)
        self.assertEqual(entry.entry_role, FilingRole.APPELLANT)
        self.assertEqual(entry.entry_doctype, FilingDocType.BRIEF)

    def test_entry_survives_uncovered_values(self) -> None:
        """Does a filing stating a type, role and document type nobody has seen
        still validate, with each of the three marked as needing a member?"""
        entry = NYCoDocketEntry(
            docket_entry_id="e:appellant-brief:smith:1",
            entry_type=DocketEntryType.UNKNOWN,
            attachments=[],
            raw_filing_type="Appellant Sur-Reply Brief",
            entry_role="sur-appellant",
            entry_doctype="surbrf",
        )

        self.assertIs(entry.entry_filing_type, Unclassified.UNASSIGNED)
        self.assertIs(entry.entry_role, Unclassified.UNASSIGNED)
        self.assertIs(entry.entry_doctype, Unclassified.UNASSIGNED)
        self.assertEqual(
            entry.raw_filing_type,
            "Appellant Sur-Reply Brief",
            "The Court's own wording has to survive the failed reading.",
        )

    def test_filing_type_the_court_never_named(self) -> None:
        """A filing the scraper reconstructed from a document has no FILINGS row
        behind it, which is the `UNKNOWN` case rather than the `UNASSIGNED` one.
        Does a raw string with nothing in it decide that?"""
        for label, raw in (
            ("no table row named it", ""),
            ("table row was blank", "   "),
        ):
            with self.subTest(label):
                entry = NYCoDocketEntry(
                    docket_entry_id="d:none:none:smith:1",
                    entry_type=DocketEntryType.UNKNOWN,
                    attachments=[],
                    raw_filing_type=raw,
                )

                self.assertIs(entry.entry_filing_type, Unclassified.UNKNOWN)

    def test_entry_stating_no_role_or_doctype(self) -> None:
        """A filing type implying no role and carrying no document states
        nothing rather than something unreadable. Is that `UNKNOWN`?"""
        entry = NYCoDocketEntry(
            docket_entry_id="e:appellant-brief:smith:1",
            entry_type=DocketEntryType.UNKNOWN,
            attachments=[],
            raw_filing_type="SCJC Determination",
            entry_role=None,
            entry_doctype=None,
        )

        self.assertIs(entry.entry_role, Unclassified.UNKNOWN)
        self.assertIs(entry.entry_doctype, Unclassified.UNKNOWN)

    def test_file_survives_an_uncovered_doctype(self) -> None:
        """Roughly 6% of file names state a document type that cannot be read.
        Does the file still validate?"""
        file = NYCoAFile(
            file_name="SmithvJones-app-Smith-surbrf.pdf",
            doc_type="surbrf",
            doc_role="sur-appellant",
        )

        self.assertIs(file.doc_type, Unclassified.UNASSIGNED)
        self.assertIs(file.doc_role, Unclassified.UNASSIGNED)
        self.assertEqual(file.file_name, "SmithvJones-app-Smith-surbrf.pdf")

    def test_file_whose_name_states_nothing(self) -> None:
        """A name that does not follow the Court's convention yields no role and
        no document type at all. Is that `UNKNOWN` rather than a failed
        reading?"""
        file = NYCoAFile(file_name="SmithvJones-Webcast.asx")

        self.assertIs(file.doc_role, Unclassified.UNKNOWN)
        self.assertIs(file.doc_type, Unclassified.UNKNOWN)

    def test_issue_survives_an_uncovered_category(self) -> None:
        """Does an issue in a category the vocabulary lacks still validate, with
        the Court's own wording kept?"""
        issue = NYCoAIssue(
            category_raw="Cryptocurrency--Staking",
            category="Cryptocurrency",
            subcategory="Staking",
        )

        self.assertIs(issue.category, Unclassified.UNASSIGNED)
        self.assertIs(issue.subcategory, Unclassified.UNASSIGNED)
        self.assertEqual(issue.category_raw, "Cryptocurrency--Staking")

    def test_issue_stated_as_a_bare_category(self) -> None:
        """The Court states roughly 13% of issues as a category alone. The
        double dash it joins the two halves with is what separates that from a
        subcategory it stated and the vocabulary lacks. Is it read that way?"""
        issue = NYCoAIssue(category_raw="Crimes", category="Crimes")

        self.assertEqual(issue.category, IssueCategory.CRIMES)
        self.assertIs(issue.subcategory, Unclassified.UNKNOWN)

    def test_members_pass_through_untouched(self) -> None:
        """A model built in Python rather than parsed from a scrape hands the
        vocabulary members themselves. Are they left alone?"""
        issue = NYCoAIssue(
            category_raw="Crimes--Sentence",
            category=IssueCategory.CRIMES,
            subcategory=IssueSubcategory.SENTENCE,
        )

        self.assertEqual(issue.category, IssueCategory.CRIMES)
        self.assertEqual(issue.subcategory, IssueSubcategory.SENTENCE)
