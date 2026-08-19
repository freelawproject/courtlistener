"""Tests for the New York Court of Appeals (Court-PASS) scrape schema and the
vocabulary mapping between Juriscraper and CourtListener.

Two failure modes are covered here, because the whole design turns on telling
them apart:

* the Court stated nothing, which is stored as `UNKNOWN`;
* the Court stated something a vocabulary does not cover, which is stored as
  `UNASSIGNED` and is the signal that a member needs adding.

Juriscraper reports both as `None`, so the raw string stored beside the code is
the only thing separating them. Neither may ever cost a docket its merge.
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
)
from cl.corpus_importer.state.new_york.utils import (
    filing_doctype_value,
    filing_role_value,
    filing_type_value,
    issue_category_value,
    issue_subcategory_value,
    make_docket_number_core,
)
from cl.search.state.new_york.vocabularies import UNASSIGNED, UNKNOWN
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
    """Tests for the codes CourtListener stores for Juriscraper's readings."""

    def test_filing_type(self) -> None:
        """Is a filing type the FILINGS table named stored under its own code,
        an unnamed filing stored as `UNKNOWN`, and one the vocabulary does not
        cover stored as `UNASSIGNED`?"""
        for label, filing_type, raw, expected in (
            (
                "named and covered",
                FilingType.APPELLANT_BRIEF,
                "Appellant Brief",
                FilingType.APPELLANT_BRIEF.code,
            ),
            ("no table row named it", None, "", UNKNOWN),
            ("table row was blank", None, "   ", UNKNOWN),
            (
                "named but not covered",
                None,
                "Appellant Sur-Reply Brief",
                UNASSIGNED,
            ),
        ):
            with self.subTest(label):
                self.assertEqual(filing_type_value(filing_type, raw), expected)

    def test_filing_role(self) -> None:
        """Is a classified role stored under its code, and a filing implying no
        role stored as `UNKNOWN`?"""
        self.assertEqual(
            filing_role_value(FilingRole.APPELLANT), FilingRole.APPELLANT.code
        )
        self.assertEqual(filing_role_value(None), UNKNOWN)

    def test_filing_doctype(self) -> None:
        """Is a classified document type stored under its code, and a filing
        carrying no document stored as `UNKNOWN`?"""
        self.assertEqual(
            filing_doctype_value(FilingDocType.BRIEF),
            FilingDocType.BRIEF.code,
        )
        self.assertEqual(filing_doctype_value(None), UNKNOWN)

    def test_unmirrored_member_is_unassigned(self) -> None:
        """A member Juriscraper has and CourtListener has not mirrored yet must
        cost the field rather than raising, so the docket still merges."""
        self.assertEqual(
            filing_role_value(cast(FilingRole, _UnmirroredRole.NOT_MIRRORED)),
            UNASSIGNED,
        )

    def test_issue_category(self) -> None:
        """Is a covered category stored under its code, no issue at all stored
        as `UNKNOWN`, and an uncovered one as `UNASSIGNED`?"""
        for label, category, raw, expected in (
            (
                "covered",
                IssueCategory.CRIMES,
                "Crimes--Sentence",
                IssueCategory.CRIMES.code,
            ),
            ("the Court stated no issue", None, "", UNKNOWN),
            ("not covered", None, "Cryptocurrency--Staking", UNASSIGNED),
        ):
            with self.subTest(label):
                self.assertEqual(issue_category_value(category, raw), expected)

    def test_issue_subcategory(self) -> None:
        """The double dash the Court joins an issue's halves with is what
        separates a bare category from a subcategory that is not covered. Is
        each stored accordingly?"""
        for label, subcategory, raw, expected in (
            (
                "covered",
                IssueSubcategory.SENTENCE,
                "Crimes--Sentence",
                IssueSubcategory.SENTENCE.code,
            ),
            ("the Court stated a bare category", None, "Crimes", UNKNOWN),
            ("not covered", None, "Crimes--Staking", UNASSIGNED),
        ):
            with self.subTest(label):
                self.assertEqual(
                    issue_subcategory_value(subcategory, raw), expected
                )


class CoveredVocabularyTest(SimpleTestCase):
    """Tests for the scrape schema's handling of values the scraper's own
    vocabularies do not cover.

    Refusing such a value would fail the whole model, which costs every filing,
    party and issue on the case over one unrecognized string. The schema reports
    `None` instead, which is what the mergers already store as `UNASSIGNED`.
    """

    def test_entry_keeps_covered_values(self) -> None:
        """Does a filing stating values the vocabularies cover classify them?"""
        entry = NYCoDocketEntry(
            docket_entry_id="e:appellant-brief:smith:1",
            entry_type=DocketEntryType.UNKNOWN,
            attachments=[],
            entry_role="appellant",
            entry_doctype="brf",
        )

        self.assertEqual(entry.entry_role, FilingRole.APPELLANT)
        self.assertEqual(entry.entry_doctype, FilingDocType.BRIEF)

    def test_entry_survives_uncovered_values(self) -> None:
        """Does a filing stating a role and document type nobody has seen still
        validate, with both left unclassified?"""
        entry = NYCoDocketEntry(
            docket_entry_id="e:appellant-brief:smith:1",
            entry_type=DocketEntryType.UNKNOWN,
            attachments=[],
            raw_filing_type="Appellant Sur-Reply Brief",
            entry_role="sur-appellant",
            entry_doctype="surbrf",
        )

        self.assertIsNone(entry.entry_role)
        self.assertIsNone(entry.entry_doctype)
        self.assertEqual(
            entry.raw_filing_type,
            "Appellant Sur-Reply Brief",
            "The Court's own wording has to survive the failed reading.",
        )

    def test_file_survives_an_uncovered_doctype(self) -> None:
        """Roughly 6% of file names state a document type that cannot be read.
        Does the file still validate?"""
        file = NYCoAFile(
            file_name="SmithvJones-app-Smith-surbrf.pdf",
            doc_type="surbrf",
            doc_role="sur-appellant",
        )

        self.assertIsNone(file.doc_type)
        self.assertIsNone(file.doc_role)
        self.assertEqual(file.file_name, "SmithvJones-app-Smith-surbrf.pdf")

    def test_issue_survives_an_uncovered_category(self) -> None:
        """Does an issue in a category the vocabulary lacks still validate, with
        the Court's own wording kept?"""
        issue = NYCoAIssue(
            category_raw="Cryptocurrency--Staking",
            category="Cryptocurrency",
            subcategory="Staking",
        )

        self.assertIsNone(issue.category)
        self.assertIsNone(issue.subcategory)
        self.assertEqual(issue.category_raw, "Cryptocurrency--Staking")

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
