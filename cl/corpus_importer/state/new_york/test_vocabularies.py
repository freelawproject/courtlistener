"""Tests for the New York Court of Appeals (Court-PASS) scrape schema and the vocabulary mapping between Juriscraper and CourtListener.

Two failure modes are covered here, because the whole design turns on telling
them apart:

* the Court stated nothing, which is stored as `UNKNOWN`;
* the Court stated something a vocabulary does not cover, which is stored as
  `UNASSIGNED` and is the signal that a member needs adding.

Juriscraper reports both as `None`, so the schema is what separates them, using
the raw string the Court printed where the value alone cannot say. Neither may
ever cost a docket its merge.
"""

from typing import Any, cast

from django.db.models import IntegerChoices
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


_MIRRORS: tuple[
    tuple[str, type[IntegerChoices], type[CourtVocabulary]], ...
] = (
    ("filing type", MirroredFilingType, FilingType),
    ("filing role", MirroredFilingRole, FilingRole),
    ("document type", MirroredFilingDocType, FilingDocType),
)
"""Every Juriscraper vocabulary CourtListener mirrors, with its mirror."""


def _entry(**fields: Any) -> NYCoDocketEntry:
    """A Court-PASS filing with no documents, stating `fields`."""
    return NYCoDocketEntry(
        docket_entry_id="e:appellant-brief:smith:1",
        entry_type=DocketEntryType.UNKNOWN,
        attachments=[],
        entry_index=0,
        **fields,
    )


class DocketNumberTest(SimpleTestCase):
    """Tests for normalizing a Court of Appeals docket number."""

    def test_normalizes_a_docket_number(self) -> None:
        """Is the Court's own format reduced to a matchable core, and does a string holding no Court of Appeals number yield nothing, so the merger can refuse the docket rather than write one it can never match again?"""
        for stated, expected in (
            ("APL-2024-00177", "apl202400177"),
            ("apl-2024-00177", "apl202400177"),
            ("  APL-2024-00177  ", "apl202400177"),
            # The case type comes from a dropdown, so any short prefix goes.
            ("CTQ-2023-00004", "ctq202300004"),
            ("JCR-2022-000012", "jcr2022000012"),
            # Court-PASS prints the number inside a longer caption.
            ("Case No. APL-2024-00177 (Part 2)", "apl202400177"),
            ("Motion No. 12", ""),
            ("", ""),
            ("   ", ""),
            ("SC1983-2014", ""),
            ("garbage", ""),
        ):
            with self.subTest(stated=stated):
                self.assertEqual(make_docket_number_core(stated), expected)

    def test_picks_one_of_several_deterministically(self) -> None:
        """A caption naming two numbers has to resolve the same way on every scrape, or the docket moves between rows."""
        both = "APL-2024-00177 and APL-2023-00001"
        self.assertEqual(make_docket_number_core(both), "apl202300001")
        self.assertEqual(
            make_docket_number_core(both),
            make_docket_number_core(
                "APL-2023-00001 and APL-2024-00177",
            ),
            "The order the caption names them in must not matter.",
        )


class VocabularyMappingTest(SimpleTestCase):
    """Tests for the codes CourtListener stores for the schema's readings."""

    def test_mirrored_members(self) -> None:
        """Is every member of every mirrored vocabulary stored under its own published code?

        Every member, rather than a sample: a mirror maps by name, so a code
        renumbered or a member renamed upstream would otherwise store the wrong
        code, or `UNASSIGNED`, without anything raising. Whichever of the two it
        is, this is the only place it surfaces.
        """
        for label, mirror, vocabulary in _MIRRORS:
            for member in vocabulary:
                with self.subTest(label, member=member.name):
                    self.assertEqual(
                        mirrored_code(mirror, member),
                        member.code,
                        f"{vocabulary.__name__}.{member.name} is not mirrored "
                        f"under its own code. Add or correct it in "
                        f"cl.search.state.new_york.vocabularies."
                        f"{mirror.__name__}.",
                    )

    def test_mirrors_define_no_member_juriscraper_dropped(self) -> None:
        """The other direction: does every mirrored name still name a member upstream?

        A member renamed or removed upstream leaves a mirror entry nothing maps
        onto, so the codes already stored under it stop meaning anything.
        """
        for label, mirror, vocabulary in _MIRRORS:
            names = {member.name for member in vocabulary} | {
                "UNKNOWN",
                "UNASSIGNED",
            }
            with self.subTest(label):
                self.assertEqual(
                    {mirrored.name for mirrored in mirror} - names,
                    set(),
                    f"cl.search.state.new_york.vocabularies."
                    f"{mirror.__name__} mirrors names that "
                    f"{vocabulary.__name__} no longer defines.",
                )

    def test_mirrored_reserved_readings(self) -> None:
        """Both readings that name no member are stored under the code reserved for them, in every mirror. Are they?"""
        for label, mirror, _ in _MIRRORS:
            with self.subTest(label):
                self.assertEqual(
                    mirrored_code(mirror, Unclassified.UNKNOWN), UNKNOWN
                )
                self.assertEqual(
                    mirrored_code(mirror, Unclassified.UNASSIGNED), UNASSIGNED
                )

    def test_unmirrored_member_is_unassigned(self) -> None:
        """A member Juriscraper has and CourtListener has not mirrored yet must cost the field rather than raising, so the docket still merges."""
        self.assertEqual(
            mirrored_code(
                MirroredFilingRole,
                cast(CourtVocabulary, _UnmirroredRole.NOT_MIRRORED),
            ),
            UNASSIGNED,
        )

    def test_issue_codes(self) -> None:
        """The issue vocabularies are too large to mirror, so their codes are Juriscraper's own. Are those stored, with the reserved codes for the two readings that name no member?"""
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

    def test_entry_readings(self) -> None:
        """Does a filing classify the type, role and document type it states, mark each one the vocabularies do not cover as needing a member, and read one it never stated as `UNKNOWN`, keeping the Court's own wording throughout?"""
        cases: tuple[tuple[str, dict[str, Any], tuple[object, ...]], ...] = (
            (
                "covered values",
                {
                    "raw_filing_type": "Appellant Brief",
                    "entry_filing_type": "Appellant Brief",
                    "entry_role": "appellant",
                    "entry_doctype": "brf",
                },
                (
                    FilingType.APPELLANT_BRIEF,
                    FilingRole.APPELLANT,
                    FilingDocType.BRIEF,
                ),
            ),
            (
                "uncovered values",
                {
                    "raw_filing_type": "Appellant Sur-Reply Brief",
                    "entry_role": "sur-appellant",
                    "entry_doctype": "surbrf",
                },
                (Unclassified.UNASSIGNED,) * 3,
            ),
            # A filing type implying no role and carrying no document states
            # nothing rather than something unreadable.
            (
                "no role or document type",
                {
                    "raw_filing_type": "SCJC Determination",
                    "entry_role": None,
                    "entry_doctype": None,
                },
                (
                    Unclassified.UNASSIGNED,
                    Unclassified.UNKNOWN,
                    Unclassified.UNKNOWN,
                ),
            ),
            # A filing the scraper reconstructed from a document has no
            # FILINGS row behind it, which is the `UNKNOWN` case rather than
            # the `UNASSIGNED` one; a raw string with nothing in it decides it.
            (
                "no table row named it",
                {"raw_filing_type": ""},
                (Unclassified.UNKNOWN,) * 3,
            ),
            (
                "table row was blank",
                {"raw_filing_type": "   "},
                (Unclassified.UNKNOWN,) * 3,
            ),
        )
        for label, fields, expected in cases:
            with self.subTest(label):
                entry = _entry(**fields)

                for reading, member in zip(
                    (
                        entry.entry_filing_type,
                        entry.entry_role,
                        entry.entry_doctype,
                    ),
                    expected,
                    strict=True,
                ):
                    self.assertIs(reading, member)
                self.assertEqual(
                    entry.raw_filing_type,
                    fields["raw_filing_type"],
                    "The Court's own wording has to survive the reading.",
                )

    def test_file_readings(self) -> None:
        """Does a file whose name states a role and document type the vocabularies do not cover still validate, marked as needing members, and is a name following none of the Court's conventions read as stating nothing rather than as a failed reading?"""
        for label, file_name, fields, expected in (
            # Roughly 6% of file names state a document type that cannot be
            # read.
            (
                "uncovered",
                "SmithvJones-app-Smith-surbrf.pdf",
                {"doc_type": "surbrf", "doc_role": "sur-appellant"},
                Unclassified.UNASSIGNED,
            ),
            (
                "nothing stated",
                "SmithvJones-Webcast.asx",
                {},
                Unclassified.UNKNOWN,
            ),
        ):
            with self.subTest(label):
                file = NYCoAFile(file_name=file_name, **fields)

                self.assertIs(file.doc_role, expected)
                self.assertIs(file.doc_type, expected)
                self.assertEqual(file.file_name, file_name)

    def test_issue_readings(self) -> None:
        """Does an issue classify what the vocabularies cover, mark a category they lack as needing a member, and read a category stated alone as stating no subcategory, keeping the Court's own wording throughout?"""
        cases: tuple[
            tuple[str, str, dict[str, Any], tuple[object, ...]], ...
        ] = (
            (
                "uncovered category",
                "Cryptocurrency--Staking",
                {"category": "Cryptocurrency", "subcategory": "Staking"},
                (Unclassified.UNASSIGNED, Unclassified.UNASSIGNED),
            ),
            # The Court states roughly 13% of issues as a category alone. The
            # double dash it joins the two halves with is what separates that
            # from a subcategory it stated and the vocabulary lacks.
            (
                "bare category",
                "Crimes",
                {"category": "Crimes"},
                (IssueCategory.CRIMES, Unclassified.UNKNOWN),
            ),
            # A model built in Python rather than parsed from a scrape hands
            # the vocabulary members themselves, which are left alone.
            (
                "members passed in",
                "Crimes--Sentence",
                {
                    "category": IssueCategory.CRIMES,
                    "subcategory": IssueSubcategory.SENTENCE,
                },
                (IssueCategory.CRIMES, IssueSubcategory.SENTENCE),
            ),
        )
        for label, category_raw, fields, expected in cases:
            with self.subTest(label):
                issue = NYCoAIssue(category_raw=category_raw, **fields)

                for reading, member in zip(
                    (issue.category, issue.subcategory), expected, strict=True
                ):
                    self.assertIs(reading, member)
                self.assertEqual(issue.category_raw, category_raw)

    def test_readings_survive_a_round_trip(self) -> None:
        """Does a model dumped and read back state what it stated before?

        Both readings that name no member dump as their own strings, which no
        vocabulary covers, so reading one back has to recover it rather than
        take it for wording the Court stated. Getting that wrong would quietly
        turn every `UNKNOWN` into an `UNASSIGNED` -- a field nobody stated into
        the signal that a member needs adding -- on every trip.
        """
        for label, model in (
            (
                "nothing stated, alongside a type the vocabulary lacks",
                NYCoAFile(
                    file_name="SmithvJones-Webcast.asx", doc_type="surbrf"
                ),
            ),
            (
                "members the vocabularies cover",
                NYCoAFile(
                    file_name="SmithvJones-app-Smith-brf.pdf",
                    doc_role="appellant",
                    doc_type="brf",
                ),
            ),
            (
                "an issue stated as a bare category",
                NYCoAIssue(category_raw="Crimes", category="Crimes"),
            ),
            ("a filing no table row named", _entry(raw_filing_type="")),
        ):
            with self.subTest(label):
                self.assertEqual(
                    type(model).model_validate_json(model.model_dump_json()),
                    model,
                )
