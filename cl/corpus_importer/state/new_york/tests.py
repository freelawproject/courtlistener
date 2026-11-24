"""Tests for the New York Court of Appeals (Court-PASS) mergers."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any
from unittest.mock import patch

from django.conf import settings
from juriscraper.state.docket import PartyType as ScrapedPartyType
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    FilingDocType,
    FilingRole,
    FilingType,
    IssueCategory,
    IssueSubcategory,
)

from cl.corpus_importer.state.merger.tests import (
    merged_docket,
    merger_test,
    table_row,
)
from cl.corpus_importer.state.new_york.factories import (
    NYCoAAttorneyFactory,
    NYCoACaseFactory,
    NYCoAFileFactory,
    NYCoAFilingFactory,
    NYCoAIssueFactory,
    NYCoAPartyFactory,
)
from cl.corpus_importer.state.new_york.loader import NYCoACourtPassLoader
from cl.corpus_importer.state.new_york.mergers import (
    NYCoADocketMerger,
)
from cl.corpus_importer.state.new_york.nycourts_gov import (
    NYCoACase,
    NYCoAFile,
    NYCoAParty,
)
from cl.corpus_importer.state.new_york.storage import (
    PRIVATE_PREFIX,
)
from cl.corpus_importer.state.new_york.utils import NYCOA_COURT_ID
from cl.corpus_importer.state.storage import PublishOutcome
from cl.corpus_importer.state.utils import FileTally, MergeResult
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import Docket
from cl.search.state.new_york.models import (
    NYCoADocketEntry,
    NYCoADocketIssue,
    NYCoADocketMetadata,
    NYCoADocument,
)
from cl.search.state.new_york.vocabularies import UNASSIGNED, UNKNOWN
from cl.tests.cases import TestCase

DOCKET_NUMBER = "APL-2024-00177"
DOCKET_NUMBER_CORE = "apl202400177"


PRIVATE_BUCKET = settings.AWS_PRIVATE_STORAGE_BUCKET_NAME
PUBLIC_BUCKET = settings.AWS_STORAGE_BUCKET_NAME

UNVOUCHED_DOWNLOADS: tuple[tuple[str, dict[str, str]], ...] = (
    ("no hash", {"content_hash": ""}),
    ("outside the private bucket", {"local_path": "/tmp/brf.pdf"}),
)
"""The ways a scrape can report a download it cannot vouch for, as the `NYCoAFile` fields that make it so."""


def published_key(
    document: NYCoADocument,
    filed: date | None,
    extension: str = ".pdf",
    thumbs: bool = False,
) -> str:
    """Where publishing a document's file puts it.

    Spelled out rather than taken from `NYCoADocument` or the loader, so that
    a test asserting on a published path is checking the layout rather than
    agreeing with whatever the code just built.

    Args:
        document: The document the file belongs to.
        filed: The date the name should carry, or `None` for undated.
        extension: The file's extension.
        thumbs: Whether to give the thumbnail's key instead.

    Returns:
        The key the public bucket holds it under.
    """
    docket = document.docket_entry.docket
    root = "recap-thumbnails" if thumbs else "recap"
    bucket = f"gov.uscourts.{NYCOA_COURT_ID}.{docket.pk}"
    stamp = filed.isoformat() if filed else "undated"
    return f"{root}/{bucket}/{bucket}.{stamp}.{document.pk}{extension}"


class NYCoAMergerTestCase(TestCase):
    """Shared setup for the NYCoA merger tests.

    Stands in for S3 throughout: publishing copies files between buckets, and
    a merge that removes a document deletes its files, so either would
    otherwise reach for the network. `copied` and `deleted` record what was
    asked for, and `publish_outcome` makes the copy report whichever way of
    failing a test is after.
    """

    copied: list[tuple[str, str, str]]
    deleted: list[tuple[str, str]]
    publish_outcome: PublishOutcome

    @classmethod
    def setUpTestData(cls) -> None:
        cls.ny = CourtFactory.create(id="ny")

    def setUp(self) -> None:
        super().setUp()
        self.copied = []
        self.deleted = []
        self.publish_outcome = PublishOutcome.PUBLISHED

        def copy_file(
            source_bucket: str,
            source_key: str,
            published_key: str,
            content_type: str = "",
        ) -> PublishOutcome:
            if self.publish_outcome is not PublishOutcome.PUBLISHED:
                return self.publish_outcome
            self.copied.append((source_bucket, source_key, published_key))
            return PublishOutcome.PUBLISHED

        def delete_file(bucket: str, key: str) -> None:
            self.deleted.append((bucket, key))

        for target, double in (
            ("cl.corpus_importer.state.loader.copy_file", copy_file),
            ("cl.corpus_importer.state.loader.delete_file", delete_file),
            (
                "cl.corpus_importer.state.new_york.mergers.delete_file",
                delete_file,
            ),
        ):
            patcher = patch(target, double)
            patcher.start()
            self.addCleanup(patcher.stop)

    @contextmanager
    def table_row(self, label: str) -> Iterator[None]:
        """Run one row of a case table as its own subtest, starting from the database and S3 doubles as `setUp` left them.

        Each row's writes are rolled back when it ends, so rows that merge the
        same docket do not merge onto what an earlier row wrote.

        Args:
            label: The name the row is reported under.
        """
        self.copied.clear()
        self.deleted.clear()
        with table_row(self, label):
            yield

    @staticmethod
    def existing_docket() -> Docket:
        return DocketFactory.create(
            court_id="ny",
            docket_number=DOCKET_NUMBER,
            docket_number_raw=DOCKET_NUMBER,
            docket_number_core="",
            pacer_case_id=None,
            source=Docket.SCRAPER,
        )

    @staticmethod
    def case(**kwargs: Any) -> NYCoACase:
        """A scraped case on the docket these tests merge.

        Args:
            **kwargs: Overrides for `NYCoACaseFactory`. Filings and parties
                are left empty unless given; issues are the factory's.

        Returns:
            The case.
        """
        return NYCoACaseFactory.create(
            **{
                "docket_number": DOCKET_NUMBER,
                "entries": [],
                "parties": [],
                **kwargs,
            }
        )

    @classmethod
    def case_with_files(
        cls, *files: NYCoAFile, **filing_kwargs: Any
    ) -> NYCoACase:
        """A scraped case with one filing, listing the given files.

        Args:
            *files: The filing's files.
            **filing_kwargs: Overrides for `NYCoAFilingFactory`.

        Returns:
            The case.
        """
        filing = NYCoAFilingFactory.create(
            attachments=list(files), **filing_kwargs
        )
        return cls.case(entries=[filing])

    @classmethod
    def case_sharing_one_file(cls, local_path: str) -> NYCoACase:
        """A scraped case with two filings that each list the same downloaded file.

        The scraper names files by content, so one file listed under two
        filings is one key in the private bucket.

        Args:
            local_path: The key both filings' files were downloaded to.

        Returns:
            The case.
        """
        return cls.case(
            entries=[
                NYCoAFilingFactory.create(
                    docket_entry_id=f"e:appellant-brief:smith:{n}",
                    attachments=[
                        NYCoAFileFactory.create(
                            file_name="SmithvJones-app-Smith-brf.pdf",
                            local_path=local_path,
                        )
                    ],
                )
                for n in (1, 2)
            ]
        )

    @staticmethod
    def one_name_under_two_roles() -> list[NYCoAParty]:
        """The parties of a family case, where the Court lists one person as the child and again as a respondent, each with an attorney of their own.

        Returns:
            The two parties.
        """
        return [
            NYCoAPartyFactory.create(
                name="A. R.",
                party_role_raw="Child",
                representatives=[
                    NYCoAAttorneyFactory.create(name="Zoe Allen")
                ],
            ),
            NYCoAPartyFactory.create(
                name="A. R.",
                party_role_raw="Respondent",
                representatives=[
                    NYCoAAttorneyFactory.create(name="Mike Weinstein")
                ],
            ),
        ]

    def merge(self, case: NYCoACase) -> tuple[MergeResult, FileTally]:
        """Merge a case and reconcile its files, as a load's worker does before it publishes them.

        Args:
            case: The scraped case.

        Returns:
            What the merge did, and what became of the case's files.
        """
        merger = NYCoADocketMerger(case, params=None)
        with self.captureOnCommitCallbacks(execute=True):
            result = merger.merge()
        return result, NYCoACourtPassLoader.reconcile_files(case, merger)

    def load(self, case: NYCoACase) -> tuple[MergeResult, FileTally]:
        """Merge a case and publish its files, as a load's worker does.

        Args:
            case: The scraped case.

        Returns:
            What the merge and the publish did together, and what became
            of the case's files.
        """
        with self.captureOnCommitCallbacks(execute=True):
            return NYCoACourtPassLoader.merge_one(case)

    @staticmethod
    def publish(document: NYCoADocument) -> None:
        """Point a document at the published copy of its file, the way an earlier load would have left it.

        Args:
            document: The document, whose filing's date has not changed
                since.
        """
        document.filepath_local = published_key(
            document, document.docket_entry.date_filed
        )
        document.save()


class NYCoADocketMergerTest(NYCoAMergerTestCase):
    """Tests for merging the docket itself."""

    @merger_test(expected_query_count=7)
    def test_merge_creates_docket(self) -> None:
        """Does merging a case with no existing docket create one with the scrape's docket-level values?"""
        case = self.case(
            case_name="People v Padilla-Zuniga",
            case_name_full="The People of the State of New York v Padilla-Zuniga",
            case_name_short="Padilla-Zuniga",
            date_filed=date(2024, 3, 1),
            argument_date=date(2025, 1, 14),
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        docket = merged_docket(result)
        self.assertEqual(docket.court_id, "ny")
        self.assertEqual(docket.docket_number, DOCKET_NUMBER)
        self.assertEqual(docket.docket_number_raw, DOCKET_NUMBER)
        self.assertEqual(docket.docket_number_core, DOCKET_NUMBER_CORE)
        self.assertEqual(docket.case_name, "People v Padilla-Zuniga")
        self.assertEqual(
            docket.case_name_full,
            "The People of the State of New York v Padilla-Zuniga",
        )
        self.assertEqual(docket.case_name_short, "Padilla-Zuniga")
        self.assertEqual(docket.date_filed, date(2024, 3, 1))
        self.assertEqual(docket.date_argued, date(2025, 1, 14))
        self.assertEqual(
            docket.date_last_filing,
            date(2024, 3, 1),
            "With no dated filings, the case's own date stands in.",
        )
        self.assertEqual(docket.source, Docket.SCRAPER)

    @merger_test(expected_query_count=7)
    def test_merge_updates_existing_docket(self) -> None:
        """Does a docket that already exists get updated rather than duplicated?"""
        docket = self.existing_docket()
        case = self.case(
            case_name="Matter of Smith", argument_date=date(2025, 2, 11)
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertNotIn("Docket", result.creates)
        self.assertEqual(Docket.objects.filter(court_id="ny").count(), 1)
        docket.refresh_from_db()
        self.assertEqual(docket.case_name, "Matter of Smith")
        self.assertEqual(docket.date_argued, date(2025, 2, 11))

    @merger_test(expected_query_count=0)
    def test_merge_case_we_cannot_place_fails(self) -> None:
        """Is a case from a New York court we don't model, or one whose docket number we can't normalize, refused rather than merged onto a docket we can never match again?"""
        for label, case_kwargs in (
            ("unmodeled court", {"court_id": "nyappdiv1"}),
            ("unusable docket number", {"docket_number": "Motion No. 12"}),
        ):
            with self.table_row(label):
                case = NYCoACaseFactory.create(**case_kwargs)

                result = NYCoADocketMerger(case, params=None).merge()

                self.assertFalse(result.success)
                self.assertFalse(Docket.objects.exists())

    @merger_test(expected_query_count=7)
    def test_merge_keeps_existing_dates(self) -> None:
        """Court-PASS has no filing date of its own.

        Does a scrape leave a date another source established alone?
        """
        docket = self.existing_docket()
        docket.date_filed = date(2020, 5, 5)
        docket.date_argued = date(2021, 6, 6)
        docket.save()
        case = self.case(date_filed=None, argument_date=None)

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        docket.refresh_from_db()
        self.assertEqual(docket.date_filed, date(2020, 5, 5))
        self.assertEqual(docket.date_argued, date(2021, 6, 6))

    @merger_test(expected_query_count=14)
    def test_merge_date_last_filing_uses_latest_filing(self) -> None:
        """Is date_last_filing the most recent filing date on the docket?"""
        case = self.case(
            date_filed=date(2024, 3, 1),
            entries=[
                NYCoAFilingFactory.create(
                    date_filed=date(2024, 6, 1), attachments=[]
                ),
                NYCoAFilingFactory.create(
                    date_filed=date(2024, 9, 15), attachments=[]
                ),
                # Reconstructed filings carry no date and must not win.
                NYCoAFilingFactory.create(
                    date_filed=None, raw_filing_type="", attachments=[]
                ),
            ],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        docket = merged_docket(result)
        self.assertEqual(docket.date_last_filing, date(2024, 9, 15))


class NYCoADocketMetadataMergerTest(NYCoAMergerTestCase):
    """Tests for merging the NYCoA-only docket metadata, which hangs off `Docket` through a reverse one-to-one relation."""

    @merger_test(expected_query_count=5)
    def test_merge_creates_metadata(self) -> None:
        """Does merging a case create its metadata row?"""
        case = self.case(
            issues=[],
            decision_date=date(2025, 4, 17),
            official_citation="41 NY3d 1",
            lower_court_citation="102 AD3d 543",
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        # pyrefly:ignore[missing-attribute]
        metadata = merged_docket(result).nycoa_metadata
        self.assertEqual(metadata.decision_date, date(2025, 4, 17))
        self.assertEqual(metadata.official_citation, "41 NY3d 1")
        self.assertEqual(metadata.lower_court_citation, "102 AD3d 543")

    @merger_test(expected_query_count=5)
    def test_merge_updates_existing_metadata(self) -> None:
        """Does a case whose metadata already exists update it in place?"""
        docket = self.existing_docket()
        metadata = NYCoADocketMetadata.objects.create(
            docket=docket,
            official_citation="",
        )
        case = self.case(
            issues=[],
            decision_date=date(2025, 4, 17),
            official_citation="41 NY3d 1",
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(NYCoADocketMetadata.objects.count(), 1)
        metadata.refresh_from_db()
        self.assertEqual(metadata.official_citation, "41 NY3d 1")
        self.assertEqual(metadata.decision_date, date(2025, 4, 17))


class NYCoAIssueMergerTest(NYCoAMergerTestCase):
    """Tests for merging the issues the Court assigned to a case."""

    @merger_test(expected_query_count=21)
    def test_merge_creates_issue(self) -> None:
        """Does merging a case create an issue row with its category normalized and the Court's own string and description kept?

        A category the vocabulary doesn't cover is flagged rather than
        dropped, and an issue the Court states as a bare category has its
        subcategory left unknown.
        """
        for label, issue_kwargs, category, subcategory in (
            (
                "category and subcategory",
                {"category_raw": "Judgments--Confession of Judgment"},
                IssueCategory.JUDGMENTS.code,
                IssueSubcategory.CONFESSION_OF_JUDGMENT.code,
            ),
            (
                # The scraper could classify neither half of this one.
                "unrecognized category",
                {
                    "category_raw": "Cryptocurrency--Staking",
                    "category": None,
                    "subcategory": None,
                },
                UNASSIGNED,
                UNASSIGNED,
            ),
            (
                "bare category",
                {"category_raw": "Crimes"},
                IssueCategory.CRIMES.code,
                UNKNOWN,
            ),
        ):
            with self.table_row(label):
                scraped = NYCoAIssueFactory.create(**issue_kwargs)

                result = NYCoADocketMerger(
                    self.case(issues=[scraped]), params=None
                ).merge()

                self.assertTrue(result.success)
                # pyrefly:ignore[missing-attribute]
                issue = merged_docket(result).nycoa_metadata.issues.get()
                self.assertEqual(issue.category, category)
                self.assertEqual(issue.subcategory, subcategory)
                self.assertEqual(issue.category_raw, scraped.category_raw)
                self.assertEqual(issue.detail, scraped.detail)

    @merger_test(expected_query_count=8)
    def test_merge_creates_issues_sharing_a_category(self) -> None:
        """The Court assigns a case two distinct issues under one category and tells them apart only by what it says about each. Does each get its own row, rather than the second colliding with the first?"""
        case = self.case(
            issues=[
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Witnesses",
                    detail="Whether the rebuttal witness was properly allowed.",
                ),
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Witnesses",
                    detail="Whether the expert's testimony was admissible.",
                ),
            ],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        # pyrefly:ignore[missing-attribute]
        issues = merged_docket(result).nycoa_metadata.issues.all()
        self.assertEqual(
            {issue.detail for issue in issues},
            {
                "Whether the rebuttal witness was properly allowed.",
                "Whether the expert's testimony was admissible.",
            },
        )
        self.assertEqual(
            {issue.category for issue in issues},
            {IssueCategory.CRIMES.code},
            "Both are the same category; the detail is what separates them.",
        )

    @merger_test(expected_query_count=12)
    def test_remerge_issues_sharing_a_category_is_idempotent(self) -> None:
        """Re-scraping a case whose issues share a category must match both rows rather than replacing one with the other."""
        case = self.case(
            issues=[
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Witnesses", detail="First."
                ),
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Witnesses", detail="Second."
                ),
            ],
        )

        first = NYCoADocketMerger(case, params=None).merge()
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertNotIn("NYCoADocketIssue", second.creates)
        self.assertEqual(NYCoADocketIssue.objects.count(), 2)

    @merger_test(expected_query_count=12)
    def test_remerge_reworded_issue_updates_it_in_place(self) -> None:
        """The Court rewords a description it has already published.

        Does the issue keep its row, rather than the old one being replaced?
        """
        case = self.case(
            issues=[
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Right to Counsel",
                    detail="Whether counsel was waived.",
                )
            ],
        )
        first = NYCoADocketMerger(case, params=None).merge()
        original = NYCoADocketIssue.objects.get()

        case.issues[0].detail = "Whether the waiver of counsel was knowing."
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertNotIn("NYCoADocketIssue", second.creates)
        issue = NYCoADocketIssue.objects.get()
        self.assertEqual(issue.pk, original.pk)
        self.assertEqual(
            issue.detail, "Whether the waiver of counsel was knowing."
        )

    @merger_test(expected_query_count=13)
    def test_reworded_issue_sharing_a_category_takes_remaining_row(
        self,
    ) -> None:
        """Rewording one of two issues that share a category leaves one stored row that no scraped issue's description matches. Does the reworded issue take that row, leaving the issue the Court did not touch on its own?"""
        case = self.case(
            issues=[
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Witnesses", detail="Untouched."
                ),
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Witnesses", detail="Original."
                ),
            ],
        )
        first = NYCoADocketMerger(case, params=None).merge()
        untouched = NYCoADocketIssue.objects.get(detail="Untouched.")
        reworded = NYCoADocketIssue.objects.get(detail="Original.")

        case.issues[1].detail = "Reworded by the Court."
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(first.success)
        self.assertTrue(second.success, second.failures)
        self.assertNotIn("NYCoADocketIssue", second.creates)
        self.assertEqual(
            dict(NYCoADocketIssue.objects.values_list("detail", "pk")),
            {
                "Untouched.": untouched.pk,
                "Reworded by the Court.": reworded.pk,
            },
        )

    @merger_test(expected_query_count=12)
    def test_identical_issues_fail(self) -> None:
        """Two issues equal on category, subcategory and detail cannot be told apart. Do both fail and the stored issues stay unpruned?"""
        case = self.case(
            issues=[
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Witnesses", detail="First."
                ),
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Witnesses", detail="Second."
                ),
            ],
        )
        first = NYCoADocketMerger(case, params=None).merge()
        stored = dict(NYCoADocketIssue.objects.values_list("detail", "pk"))

        case.issues[1].detail = "First."
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(first.success)
        self.assertEqual(second.failures["NYCoADocketIssue"], [None, None])
        self.assertNotIn("NYCoADocketIssue", second.creates)
        self.assertNotIn("NYCoADocketIssue", second.updates)
        self.assertEqual(
            dict(NYCoADocketIssue.objects.values_list("detail", "pk")),
            stored,
        )

    @merger_test(expected_query_count=14)
    def test_remerge_drops_an_issue_sharing_a_category(self) -> None:
        """A case that stated two issues under one category now states one of them. Is the other pruned, and does the survivor keep its row?"""
        case = self.case(
            issues=[
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Witnesses", detail="Kept."
                ),
                NYCoAIssueFactory.create(
                    category_raw="Crimes--Witnesses", detail="Withdrawn."
                ),
            ],
        )
        first = NYCoADocketMerger(case, params=None).merge()
        kept = NYCoADocketIssue.objects.get(detail="Kept.")

        del case.issues[1]
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        issue = NYCoADocketIssue.objects.get()
        self.assertEqual(issue.pk, kept.pk)
        self.assertEqual(issue.detail, "Kept.")

    @merger_test(expected_query_count=9)
    def test_merge_prunes_issues_missing_from_scrape(self) -> None:
        """Does an issue the Court no longer lists get deleted?"""
        docket = self.existing_docket()
        metadata = NYCoADocketMetadata.objects.create(docket=docket)
        stale = NYCoADocketIssue.objects.create(
            metadata=metadata,
            category=IssueCategory.TAXATION.code,
            category_raw="Taxation--Sales Tax",
        )
        case = self.case(
            issues=[NYCoAIssueFactory.create(category_raw="Crimes--Sentence")],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertFalse(
            NYCoADocketIssue.objects.filter(pk=stale.pk).exists(),
            "An issue the scrape no longer reports should be pruned.",
        )
        self.assertEqual(
            metadata.issues.get().category_raw, "Crimes--Sentence"
        )

    @merger_test(expected_query_count=5)
    def test_merge_no_issues_keeps_existing(self) -> None:
        """A scrape with no issues at all is a partial scrape.

        Does it leave the issues already recorded alone?
        """
        docket = self.existing_docket()
        metadata = NYCoADocketMetadata.objects.create(docket=docket)
        existing = NYCoADocketIssue.objects.create(
            metadata=metadata,
            category=IssueCategory.TAXATION.code,
            category_raw="Taxation--Sales Tax",
        )
        case = self.case(issues=[])

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(metadata.issues.get().pk, existing.pk)


class NYCoADocketEntryMergerTest(NYCoAMergerTestCase):
    """Tests for merging a docket's filings."""

    @merger_test(expected_query_count=10)
    def test_merge_creates_filings(self) -> None:
        """Does merging a case create its filings with the scrape's values?"""
        filing = NYCoAFilingFactory.create(
            docket_entry_id="e:appellant-brief:smith:1",
            entry_index=3,
            raw_filing_type="Appellant Brief",
            party="Smith",
            date_filed=date(2024, 6, 1),
            date_due=date(2024, 5, 15),
            entry_role=FilingRole.APPELLANT,
            entry_doctype=FilingDocType.BRIEF,
            attachments=[],
        )
        case = self.case(entries=[filing])

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertIn("NYCoADocketEntry", result.creates)
        # pyrefly:ignore[missing-attribute]
        merged = merged_docket(result).nycoa_docket_entries.get()
        self.assertEqual(merged.docket_entry_id, "e:appellant-brief:smith:1")
        self.assertEqual(merged.entry_index, 3)
        self.assertEqual(merged.filing_type, FilingType.APPELLANT_BRIEF.code)
        self.assertEqual(merged.filing_type_raw, "Appellant Brief")
        self.assertEqual(merged.filing_role, FilingRole.APPELLANT.code)
        self.assertEqual(merged.filing_doctype, FilingDocType.BRIEF.code)
        self.assertIsNone(merged.party_id)
        self.assertEqual(merged.date_filed, date(2024, 6, 1))
        self.assertEqual(merged.date_due, date(2024, 5, 15))

    @merger_test(expected_query_count=10)
    def test_merge_unrecognized_filing_type(self) -> None:
        """Court-PASS listing a filing type this vocabulary doesn't cover is the drift signal. Is it stored as unassigned while the raw value survives?"""
        filing = NYCoAFilingFactory.create(
            raw_filing_type="Appellant Sur-Reply Brief",
            entry_role=FilingRole.APPELLANT,
            entry_doctype=FilingDocType.BRIEF,
            attachments=[],
        )
        case = self.case(entries=[filing])

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        # pyrefly:ignore[missing-attribute]
        merged = merged_docket(result).nycoa_docket_entries.get()
        self.assertEqual(merged.filing_type, UNASSIGNED)
        self.assertEqual(merged.filing_type_raw, "Appellant Sur-Reply Brief")
        self.assertEqual(merged.filing_role, FilingRole.APPELLANT.code)

    @merger_test(expected_query_count=9)
    def test_merge_filing_reconstructed_from_document(self) -> None:
        """Does a filing the scraper reconstructed from a document merge with no date and no raw filing type?"""
        filing = NYCoAFilingFactory.create(
            docket_entry_id="d:court:51opn21:_decision:1",
            raw_filing_type="",
            date_filed=None,
            date_due=None,
            entry_role=None,
            entry_doctype=FilingDocType.DECISION,
            party="",
            attachments=[],
        )
        case = self.case(entries=[filing])

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        # pyrefly:ignore[missing-attribute]
        merged = merged_docket(result).nycoa_docket_entries.get()
        self.assertEqual(
            merged.filing_type,
            UNKNOWN,
            "No FILINGS row named a reconstructed filing.",
        )
        self.assertEqual(merged.filing_type_raw, "")
        self.assertEqual(merged.filing_doctype, FilingDocType.DECISION.code)
        self.assertEqual(
            merged.filing_role,
            UNKNOWN,
            "The court's own output has no party role.",
        )
        self.assertIsNone(merged.date_filed)
        self.assertIsNone(merged.party_id)

    @merger_test(expected_query_count=19)
    def test_remerge_updates_filing_fields(self) -> None:
        """Does a filing matched by its entry ID pick up new values?"""
        filing = NYCoAFilingFactory.create(
            docket_entry_id="e:appellant-brief:smith:1",
            date_filed=None,
            entry_index=1,
            attachments=[],
        )
        case = self.case(entries=[filing])
        NYCoADocketMerger(case, params=None).merge()

        updated = filing.model_copy(
            update={"date_filed": date(2024, 6, 1), "entry_index": 2}
        )
        result = NYCoADocketMerger(
            # The same issues, because this is the same case scraped again and
            # an issue is identified by what the Court said about it.
            self.case(entries=[updated], issues=case.issues),
            params=None,
        ).merge()

        self.assertTrue(result.success)
        self.assertEqual(NYCoADocketEntry.objects.count(), 1)
        merged = NYCoADocketEntry.objects.get()
        self.assertEqual(merged.date_filed, date(2024, 6, 1))
        self.assertEqual(merged.entry_index, 2)

    @merger_test(expected_query_count=14)
    def test_merge_prunes_filings_missing_from_scrape(self) -> None:
        """Court-PASS lists a case's filings in full, so does a filing that is gone from the scrape get deleted?"""
        docket = self.existing_docket()
        stale = NYCoADocketEntry.objects.create(
            docket=docket,
            docket_entry_id="e:withdrawn-brief:jones:1",
            filing_type_raw="Withdrawn Brief",
        )
        filing = NYCoAFilingFactory.create(
            docket_entry_id="e:appellant-brief:smith:1", attachments=[]
        )
        case = self.case(entries=[filing])

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertFalse(
            NYCoADocketEntry.objects.filter(pk=stale.pk).exists(),
            "A filing the scrape no longer reports should be pruned.",
        )
        self.assertEqual(
            # pyrefly:ignore[missing-attribute]
            docket.nycoa_docket_entries.get().docket_entry_id,
            "e:appellant-brief:smith:1",
        )

    @merger_test(expected_query_count=30)
    def test_merge_links_filing_to_docket_party(self) -> None:
        """Is a filing's party resolved to a party on the docket, keeping the name the FILINGS table printed?

        A filer who isn't a party on the docket -- one with no attorney of
        record, or one the FILINGS table names in its own words -- has no
        party row to point at, so its FK is left null rather than the merge
        failing.
        """
        for label, filer, resolves in (
            ("party on the docket", "Smith", True),
            ("filer who is not a party", "Board of Elections", False),
        ):
            with self.table_row(label):
                case = self.case(
                    parties=[
                        NYCoAPartyFactory.create(
                            name="Smith", representatives=[]
                        )
                    ],
                    entries=[
                        NYCoAFilingFactory.create(party=filer, attachments=[])
                    ],
                )

                result = NYCoADocketMerger(case, params=None).merge()

                self.assertTrue(result.success)
                # pyrefly:ignore[missing-attribute]
                merged = merged_docket(result).nycoa_docket_entries.get()
                self.assertEqual(
                    merged.party,
                    Party.objects.get(name=filer) if resolves else None,
                )
                self.assertEqual(merged.party_name, filer)

    @merger_test(expected_query_count=18)
    def test_merge_links_filing_to_party_in_the_filing_role(self) -> None:
        """In a family case the Court lists one person under two roles, so a filing's party name finds two parties. Is the filing linked to the one whose role the filing itself states, rather than to whichever was written first?"""
        case = self.case(
            parties=[
                NYCoAPartyFactory.create(
                    name="A. R.", party_role_raw="Child", representatives=[]
                ),
                NYCoAPartyFactory.create(
                    name="A. R.",
                    party_role_raw="Respondent",
                    representatives=[],
                ),
            ],
            entries=[
                NYCoAFilingFactory.create(
                    party="A. R.",
                    entry_role=FilingRole.RESPONDENT,
                    attachments=[],
                )
            ],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(Party.objects.filter(name="A. R.").count(), 2)
        # pyrefly:ignore[missing-attribute]
        merged = merged_docket(result).nycoa_docket_entries.get()
        self.assertEqual(
            merged.party_id,
            PartyType.objects.get(name="Respondent").party_id,
        )

    @merger_test(expected_query_count=23)
    def test_remerge_keeps_resolved_filing_party(self) -> None:
        """Does a later scrape that can't resolve the party keep the party a previous scrape resolved?"""
        case = self.case(
            parties=[
                NYCoAPartyFactory.create(name="Smith", representatives=[])
            ],
            entries=[
                NYCoAFilingFactory.create(
                    docket_entry_id="e:appellant-brief:smith:1",
                    party="Smith",
                    attachments=[],
                )
            ],
        )
        NYCoADocketMerger(case, params=None).merge()

        # The same filing, with the party name dropped from the scrape.
        second = self.case(
            entries=[
                NYCoAFilingFactory.create(
                    docket_entry_id="e:appellant-brief:smith:1",
                    party="",
                    attachments=[],
                )
            ],
            issues=case.issues,
        )
        result = NYCoADocketMerger(second, params=None).merge()

        self.assertTrue(result.success)
        merged = NYCoADocketEntry.objects.get()
        self.assertEqual(merged.party, Party.objects.get(name="Smith"))
        # The name is kept for the same reason the FK is: a filing's party is
        # part of its `docket_entry_id`, so a blank means this scrape missed
        # the name, not that the Court withdrew it.
        self.assertEqual(merged.party_name, "Smith")


class NYCoADocumentMergerTest(NYCoAMergerTestCase):
    """Tests for merging the files published for a filing."""

    @merger_test(expected_query_count=12)
    def test_merge_creates_documents(self) -> None:
        """Does merging a filing create its documents with the values the file name yielded?"""
        file = NYCoAFileFactory.create(
            file_name="SmithvJones-app-Smith-Rec-vol3.pdf",
            content_type="application/pdf",
            available=True,
            doc_role="appellant",
            doc_party="Smith",
            doc_type=FilingDocType.RECORD,
            volume=3,
            part=2,
            local_path=f"{PRIVATE_PREFIX}smith-rec-vol3.pdf",
        )
        case = self.case_with_files(file)

        result, _ = self.merge(case)

        self.assertTrue(result.success)
        self.assertIn("NYCoADocument", result.creates)
        merged = (
            # pyrefly:ignore[missing-attribute]
            merged_docket(result).nycoa_docket_entries.get().documents.get()
        )
        self.assertEqual(
            merged.file_name, "SmithvJones-app-Smith-Rec-vol3.pdf"
        )
        self.assertEqual(merged.content_type, "application/pdf")
        self.assertEqual(merged.doc_role, FilingRole.APPELLANT)
        self.assertEqual(merged.doc_party, "Smith")
        self.assertEqual(merged.doc_type, FilingDocType.RECORD)
        self.assertEqual(merged.volume, 3)
        self.assertEqual(merged.part, 2)
        self.assertEqual(merged.sha256, file.content_hash)
        self.assertEqual(merged.file_size, file.file_size)
        self.assertEqual(
            merged.filepath_local,
            file.local_path,
            "The published name needs the document's primary key, so the "
            "merge stores the scraper's key and leaves the move to the load.",
        )
        self.assertEqual(self.copied, [], "Merging moves no file.")

    @merger_test(expected_query_count=12)
    def test_merge_oral_argument_recording(self) -> None:
        """Oral argument recordings are playlists, not PDFs.

        Does the content type survive the merge so the file pass can route
        them?
        """
        file = NYCoAFileFactory.create(
            file_name="SmithvJones-Webcast.asx",
            content_type="video/x-ms-asf",
            doc_role=None,
            doc_party="",
            doc_type=FilingDocType.ORAL_ARGUMENT_WEBCAST,
            local_path=f"{PRIVATE_PREFIX}smithvjones-webcast.asx",
        )
        case = self.case_with_files(
            file,
            docket_entry_id="d:court:smithvjones:_webcast:1",
            raw_filing_type="",
            entry_role=None,
            entry_doctype=FilingDocType.ORAL_ARGUMENT_WEBCAST,
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        merged = NYCoADocument.objects.get()
        self.assertEqual(merged.file_name, "SmithvJones-Webcast.asx")
        self.assertEqual(merged.content_type, "video/x-ms-asf")
        self.assertEqual(merged.doc_type, FilingDocType.ORAL_ARGUMENT_WEBCAST)
        self.assertEqual(merged.filepath_local, file.local_path)

    @merger_test(expected_query_count=12)
    def test_merge_unstorable_volume(self) -> None:
        """A volume is read out of the file name, and a name whose extension is digits reads as a number too large for the column. Does the file still merge, without its volume?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="PeoplevHeidgen-app-Heidgen-Appdx-Vol6.1910",
                doc_type=FilingDocType.APPENDIX,
                volume=61910,
            )
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(
            result.success,
            "One unreadable volume must not cost the docket its merge.",
        )
        merged = NYCoADocument.objects.get()
        self.assertEqual(
            merged.file_name, "PeoplevHeidgen-app-Heidgen-Appdx-Vol6.1910"
        )
        self.assertIsNone(merged.volume)

    @merger_test(expected_query_count=19)
    def test_remerge_documents_is_idempotent(self) -> None:
        """Does merging the same case twice avoid duplicating documents, and keep the text already extracted from a file that has not moved?"""
        case = self.case_with_files(NYCoAFileFactory.create())

        first = NYCoADocketMerger(case, params=None).merge()
        extracted = NYCoADocument.objects.get()
        extracted.ocr_status = NYCoADocument.OCR_COMPLETE
        extracted.save()
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertNotIn("NYCoADocument", second.creates)
        self.assertEqual(NYCoADocument.objects.count(), 1)
        self.assertEqual(
            NYCoADocument.objects.get().ocr_status,
            NYCoADocument.OCR_COMPLETE,
            "The file did not move, so its extracted text still stands.",
        )

    @merger_test(expected_query_count=14)
    def test_merge_prunes_documents_missing_from_scrape(self) -> None:
        """Is a document the scrape no longer lists deleted?"""
        docket = self.existing_docket()
        entry = NYCoADocketEntry.objects.create(
            docket=docket,
            docket_entry_id="e:appellant-brief:smith:1",
            filing_type=FilingType.APPELLANT_BRIEF.code,
            filing_type_raw="Appellant Brief",
        )
        stale = NYCoADocument.objects.create(
            docket_entry=entry, file_name="SmithvJones-app-Smith-oldbrf.pdf"
        )
        case = self.case_with_files(
            NYCoAFileFactory.create(file_name="SmithvJones-app-Smith-brf.pdf"),
            docket_entry_id="e:appellant-brief:smith:1",
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertFalse(
            NYCoADocument.objects.filter(pk=stale.pk).exists(),
            "A file the scrape no longer lists should be pruned.",
        )
        self.assertEqual(
            entry.documents.get().file_name, "SmithvJones-app-Smith-brf.pdf"
        )

    @merger_test(expected_query_count=10)
    def test_merge_file_the_court_will_not_serve(self) -> None:
        """A file the Court lists but declines to hand over has nothing to record -- no bytes, no hash, nothing to extract -- and a row for it would only be one every file sweep has to skip. Is it left out of the document table while its filing is still recorded?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(available=False, local_path="")
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(NYCoADocument.objects.count(), 0)
        self.assertEqual(
            NYCoADocketEntry.objects.count(),
            1,
            "The filing is still on the docket; only its file is not.",
        )

    @merger_test(expected_query_count=12)
    def test_merge_keeps_the_files_the_court_does_serve(self) -> None:
        """A filing can list a file the Court serves beside one it does not.

        Does the servable one still get a document row?
        """
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                available=True,
            ),
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-rec.txt",
                available=False,
                local_path="",
            ),
        )

        result, _ = self.merge(case)

        self.assertTrue(result.success)
        self.assertEqual(
            [document.file_name for document in NYCoADocument.objects.all()],
            ["SmithvJones-app-Smith-brf.pdf"],
        )

    def test_remerge_a_corrected_file_goes_back_for_publishing(self) -> None:
        """The Court reissues a document under the name it first used, and the published name is the document's, so the correction is published on top of the copy it replaces. Does a rescrape whose file hashes differently and sits at a new key -- whether or not the earlier copy was published yet -- point the document back at the scraper's copy, delete nothing for the move to overwrite, and send the document back for extraction?"""
        for label, published in (
            ("published", True),
            ("not yet published", False),
        ):
            with self.table_row(label):
                original = NYCoAFileFactory.create(
                    file_name="SmithvJones-app-Smith-brf.pdf",
                    local_path=f"{PRIVATE_PREFIX}brf.pdf",
                )
                case = self.case_with_files(
                    original, docket_entry_id="e:appellant-brief:smith:1"
                )
                self.merge(case)
                extracted = NYCoADocument.objects.get()
                if published:
                    self.publish(extracted)
                extracted.ocr_status = NYCoADocument.OCR_COMPLETE
                extracted.page_count = 12
                extracted.save()

                corrected = NYCoAFileFactory.create(
                    file_name="SmithvJones-app-Smith-brf.pdf",
                    local_path=f"{PRIVATE_PREFIX}brf-corrected.pdf",
                )
                second = self.case_with_files(
                    corrected, docket_entry_id="e:appellant-brief:smith:1"
                )
                second.issues = case.issues
                result, _ = self.merge(second)

                self.assertTrue(result.success)
                merged = NYCoADocument.objects.get()
                self.assertEqual(merged.filepath_local, corrected.local_path)
                self.assertEqual(merged.sha256, corrected.content_hash)
                self.assertEqual(merged.file_size, corrected.file_size)
                self.assertEqual(
                    self.deleted,
                    [],
                    "A published copy is overwritten, not deleted.",
                )
                self.assertIsNone(
                    merged.ocr_status,
                    "A replaced file has to be extracted again.",
                )
                self.assertIsNone(
                    merged.page_count,
                    "The pages were counted off the copy that has been "
                    "replaced.",
                )

    @merger_test(expected_query_count=21)
    def test_remerge_keeps_stored_path_when_scrape_reports_none(self) -> None:
        """Does a later scrape that did not fetch the file leave the path an earlier one recorded, rather than blanking it?

        The Court still lists the file, which is what tells this apart from
        the file it has stopped serving.
        """
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                available=True,
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        NYCoADocketMerger(case, params=None).merge()
        stored = NYCoADocument.objects.get().filepath_local.name

        second = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                available=True,
                local_path="",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        second.issues = case.issues
        result = NYCoADocketMerger(second, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(NYCoADocument.objects.get().filepath_local, stored)

    def test_remerge_of_a_published_file_keeps_the_published_path(
        self,
    ) -> None:
        """A later scrape downloads an unchanged file again, to a key of its own. Does re-merging the same file leave the document pointing at its published copy, and delete the scraper's new copy, which nothing will ever point at?"""
        file = NYCoAFileFactory.create(
            file_name="SmithvJones-app-Smith-brf.pdf",
            local_path=f"{PRIVATE_PREFIX}brf.pdf",
        )
        case = self.case_with_files(
            file, docket_entry_id="e:appellant-brief:smith:1"
        )
        self.merge(case)
        document = NYCoADocument.objects.get()
        self.publish(document)
        published = document.filepath_local.name
        file.local_path = f"{PRIVATE_PREFIX}rescraped/brf.pdf"

        result, files = self.merge(case)

        self.assertTrue(result.success)
        self.assertEqual(files, FileTally())
        self.assertEqual(NYCoADocument.objects.get().filepath_local, published)
        self.assertEqual(
            self.deleted,
            [(PRIVATE_BUCKET, f"{PRIVATE_PREFIX}rescraped/brf.pdf")],
        )

    def test_an_unvouched_file_is_not_missing_where_one_is_stored(
        self,
    ) -> None:
        """A re-scrape whose file has no hash, or a path outside the private bucket, leaves the document with the file it already has. Is that file kept and nothing counted as missing?"""
        for label, rescraped in UNVOUCHED_DOWNLOADS:
            with self.table_row(label):
                file = NYCoAFileFactory.create(
                    file_name="SmithvJones-app-Smith-brf.pdf",
                    local_path=f"{PRIVATE_PREFIX}brf.pdf",
                )
                case = self.case_with_files(
                    file, docket_entry_id="e:appellant-brief:smith:1"
                )
                self.merge(case)
                stored = NYCoADocument.objects.get().filepath_local.name
                for field_name, value in rescraped.items():
                    setattr(file, field_name, value)

                result, files = self.merge(case)

                self.assertTrue(result.success)
                self.assertEqual(files, FileTally())
                self.assertEqual(
                    NYCoADocument.objects.get().filepath_local, stored
                )

    def test_an_unvouched_download_is_not_stored(self) -> None:
        """A download with no hash cannot be told from a later correction, and one outside the private bucket is a file publishing cannot even look for. Does the merge store no file for it and count it as missing, since it will not appear on a re-run, while merging the rest of the case -- its own document among it -- rather than refusing the whole case over it?"""
        for label, unvouched_fields in UNVOUCHED_DOWNLOADS:
            with self.table_row(label):
                unvouched = NYCoAFileFactory.create(
                    **{
                        "file_name": "SmithvJones-app-Smith-brf.pdf",
                        "local_path": f"{PRIVATE_PREFIX}brf.pdf",
                        **unvouched_fields,
                    }
                )
                vouched = NYCoAFileFactory.create(
                    file_name="SmithvJones-resp-Jones-brf.pdf",
                    local_path=f"{PRIVATE_PREFIX}resp-brf.pdf",
                )
                case = self.case_with_files(unvouched, vouched)

                result, files = self.merge(case)

                self.assertTrue(
                    result.success,
                    "One untracked file must not fail the case.",
                )
                self.assertEqual(files, FileTally(missing=1))
                merged = NYCoADocument.objects.get(
                    file_name=unvouched.file_name
                )
                self.assertEqual(merged.filepath_local, "")
                self.assertEqual(merged.sha256, "")
                self.assertEqual(
                    NYCoADocument.objects.get(
                        file_name=vouched.file_name
                    ).filepath_local,
                    vouched.local_path,
                )

    @merger_test(expected_query_count=12)
    def test_a_file_the_scraper_never_fetched_needs_no_hash(self) -> None:
        """Only a download has a hash to record, and the Court offering a file is no guarantee the scraper came away with it. Does a document whose fetch produced nothing merge with no file, rather than being refused for a hash it was never going to have?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                available=True,
                local_path="",
            )
        )

        result, files = self.merge(case)

        self.assertTrue(result.success)
        self.assertFalse(files)
        self.assertEqual(NYCoADocument.objects.get().filepath_local, "")


class NYCoAFileDeletionTest(NYCoAMergerTestCase):
    """Tests for deleting the files of the documents a merge removes."""

    def test_remerge_deletes_the_files_of_a_document_the_court_stopped_serving(
        self,
    ) -> None:
        """A file the Court stops serving is listed with its download button disabled. Does the document go with it, published copy and thumbnail and all, so that nothing is left serving a file CourtListener may no longer publish?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                available=True,
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        self.merge(case)
        document = NYCoADocument.objects.get()
        self.publish(document)
        thumbnail = f"recap-thumbnails/{document.pk}.thumb.1068.png"
        document.thumbnail = thumbnail
        document.save()

        pulled = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                available=False,
                local_path="",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        pulled.issues = case.issues
        result, _ = self.merge(pulled)

        self.assertTrue(result.success)
        self.assertEqual(NYCoADocument.objects.count(), 0)
        self.assertEqual(
            NYCoADocketEntry.objects.count(),
            1,
            "The filing stays; only the document it can no longer serve goes.",
        )
        self.assertCountEqual(
            self.deleted,
            [
                (PUBLIC_BUCKET, document.filepath_local.name),
                (PUBLIC_BUCKET, thumbnail),
            ],
        )

    def test_remerge_deletes_the_files_of_a_dropped_filing(self) -> None:
        """A filing the scrape no longer lists is deleted outright, and its documents go with it in a cascade no document merger sees. Are their files still deleted?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        self.merge(case)
        document = NYCoADocument.objects.get()
        self.publish(document)

        withdrawn_filing = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-resp-Jones-brf.pdf",
                local_path=f"{PRIVATE_PREFIX}resp.pdf",
            ),
            docket_entry_id="e:respondent-brief:jones:1",
        )
        withdrawn_filing.issues = case.issues
        result, _ = self.merge(withdrawn_filing)

        self.assertTrue(result.success)
        self.assertEqual(NYCoADocketEntry.objects.count(), 1)
        self.assertEqual(
            self.deleted, [(PUBLIC_BUCKET, document.filepath_local.name)]
        )

    def test_an_unpublished_file_is_deleted_from_the_private_bucket(
        self,
    ) -> None:
        """A document removed before its file was published still leaves the scraper's copy behind. Is that deleted from the bucket it is in?"""
        file = NYCoAFileFactory.create(
            file_name="SmithvJones-app-Smith-oldbrf.pdf",
            local_path=f"{PRIVATE_PREFIX}oldbrf.pdf",
        )
        case = self.case_with_files(
            file, docket_entry_id="e:appellant-brief:smith:1"
        )
        self.merge(case)

        replaced = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        replaced.issues = case.issues
        self.merge(replaced)

        self.assertEqual(self.deleted, [(PRIVATE_BUCKET, file.local_path)])

    def test_a_private_file_another_document_still_uses_is_kept(self) -> None:
        """The scraper names files by content, so one file listed under two filings is one key. Is it kept while the other document still points at it?"""
        case = self.case_sharing_one_file(f"{PRIVATE_PREFIX}shared.pdf")
        self.merge(case)

        case.entries = case.entries[:1]
        self.merge(case)

        self.assertEqual(NYCoADocument.objects.count(), 1)
        self.assertEqual(self.deleted, [])


class NYCoAPublishFilesTest(NYCoAMergerTestCase):
    """Tests for the move a load makes after each merge, from the scraper's key to the one the document's primary keys name."""

    def test_a_thumbnail_parallels_its_document(self) -> None:
        """Is a thumbnail filed beside its document, under the thumbnail root instead and keeping the extension it was handed?"""
        filed = date(2024, 3, 1)
        self.merge(
            self.case_with_files(NYCoAFileFactory.create(), date_filed=filed)
        )
        document = NYCoADocument.objects.get()

        self.assertEqual(
            document.get_pdf_path("name.png", thumbs=True),
            published_key(document, filed, ".png", thumbs=True),
        )

    def test_a_scraped_file_is_published_under_its_document(self) -> None:
        """Is the file copied out of the private bucket to the name the docket, the filing's date and the document make, the document pointed at it, and the scraper's copy deleted?

        Court-PASS serves playlists beside PDFs, so the name keeps the file's
        own extension.
        """
        for file_name, extension in (
            ("SmithvJones-app-Smith-brf.pdf", ".pdf"),
            ("SmithvJones-Webcast.asx", ".asx"),
        ):
            with self.table_row(extension):
                file = NYCoAFileFactory.create(
                    file_name=file_name,
                    local_path=f"{PRIVATE_PREFIX}{file_name.lower()}",
                )
                case = self.case_with_files(file, date_filed=date(2024, 3, 1))

                result, files = self.load(case)

                document = NYCoADocument.objects.get()
                expected = published_key(document, date(2024, 3, 1), extension)
                self.assertEqual(document.filepath_local, expected)
                self.assertEqual(
                    self.copied, [(PRIVATE_BUCKET, file.local_path, expected)]
                )
                self.assertEqual(
                    self.deleted, [(PRIVATE_BUCKET, file.local_path)]
                )
                self.assertEqual(files, FileTally(moved=1))
                self.assertIn(document.pk, result.updates["NYCoADocument"])

    def test_documents_filed_the_same_day_are_named_apart(self) -> None:
        """Two files of one filing share a docket and a date.

        Does each still get a name of its own?
        """
        case = self.case_with_files(
            NYCoAFileFactory.create(file_name="brief.pdf"),
            NYCoAFileFactory.create(file_name="appendix.pdf"),
        )

        self.load(case)

        paths = set(
            NYCoADocument.objects.values_list("filepath_local", flat=True)
        )
        self.assertEqual(len(paths), 2, f"Two documents share a path: {paths}")

    def test_a_published_file_is_not_moved_again(self) -> None:
        """Re-loading an unchanged case has nothing to move.

        Is nothing copied or counted, and nothing deleted but the scraper's
        key, which a scrape that downloaded the file again would have left
        behind?
        """
        file = NYCoAFileFactory.create()
        case = self.case_with_files(file)
        self.load(case)
        self.copied.clear()
        self.deleted.clear()

        _, files = self.load(case)

        self.assertEqual(self.copied, [])
        self.assertEqual(self.deleted, [(PRIVATE_BUCKET, file.local_path)])
        self.assertFalse(files, f"Counted a move that did not happen: {files}")

    def test_a_file_whose_date_changed_is_moved(self) -> None:
        """A later scrape can date a filing an earlier one could not.

        Is the published file moved to the name that date makes, and the old
        copy deleted?
        """
        file = NYCoAFileFactory.create()
        case = self.case_with_files(
            file,
            date_filed=None,
            docket_entry_id="e:appellant-brief:smith:1",
        )
        self.load(case)
        document = NYCoADocument.objects.get()
        undated = published_key(document, None)
        self.assertEqual(document.filepath_local, undated)
        self.copied.clear()
        self.deleted.clear()

        case.entries[0].date_filed = date(2024, 3, 1)
        _, files = self.load(case)

        dated = published_key(document, date(2024, 3, 1))
        self.assertEqual(NYCoADocument.objects.get().filepath_local, dated)
        self.assertEqual(self.copied, [(PUBLIC_BUCKET, undated, dated)])
        self.assertCountEqual(
            self.deleted,
            [(PUBLIC_BUCKET, undated), (PRIVATE_BUCKET, file.local_path)],
        )
        self.assertEqual(files, FileTally(moved=1))

    def test_a_refused_copy_leaves_the_file_to_a_later_load(self) -> None:
        """The bucket refusing the copy says nothing about the file, which is still in the private bucket. Does the document keep pointing there, so re-running the load finishes the move, with nothing deleted?"""
        self.publish_outcome = PublishOutcome.FAILED
        file = NYCoAFileFactory.create(local_path=f"{PRIVATE_PREFIX}brf.pdf")

        result, files = self.load(self.case_with_files(file))

        self.assertTrue(
            result.success, "A file we could not move must not fail the case."
        )
        self.assertEqual(files, FileTally(failed=1))
        self.assertNotIn("NYCoADocument", result.updates)
        self.assertEqual(
            NYCoADocument.objects.get().filepath_local, file.local_path
        )
        self.assertEqual(self.deleted, [])

        self.publish_outcome = PublishOutcome.PUBLISHED
        _, files = NYCoACourtPassLoader.publish_files(Docket.objects.get())

        self.assertEqual(files, FileTally(moved=1))

    def test_a_missing_file_stops_being_pointed_at(self) -> None:
        """A file the private bucket does not hold will not appear on a re-run.

        Is the document left with no file rather than a path to nothing?
        """
        self.publish_outcome = PublishOutcome.MISSING

        _, files = self.load(self.case_with_files(NYCoAFileFactory.create()))

        self.assertEqual(files, FileTally(missing=1))
        self.assertEqual(NYCoADocument.objects.get().filepath_local, "")
        self.assertEqual(self.deleted, [])

    def test_a_file_shared_by_two_documents_is_deleted_once_both_moved(
        self,
    ) -> None:
        """One scraped file can stand for documents under two filings.

        Is each published under its own name, and the scraper's copy deleted
        only once neither still needs it?
        """
        shared = f"{PRIVATE_PREFIX}shared.pdf"
        case = self.case_sharing_one_file(shared)

        _, files = self.load(case)

        self.assertEqual(files, FileTally(moved=2))
        self.assertEqual(
            [source for _, source, _ in self.copied], [shared, shared]
        )
        self.assertEqual(self.deleted, [(PRIVATE_BUCKET, shared)])

    def test_a_document_changed_mid_move_is_left_alone(self) -> None:
        """Another merge of the same docket can repoint a document while its file is being copied. Is that write kept, and the file it was copied from left for the other merge?"""
        file = NYCoAFileFactory.create(local_path=f"{PRIVATE_PREFIX}brf.pdf")
        self.merge(self.case_with_files(file))
        newer = f"{PRIVATE_PREFIX}newer.pdf"

        def copy_then_repoint(
            *args: object, **kwargs: object
        ) -> PublishOutcome:
            NYCoADocument.objects.update(filepath_local=newer)
            return PublishOutcome.PUBLISHED

        with patch(
            "cl.corpus_importer.state.loader.copy_file", copy_then_repoint
        ):
            _, files = NYCoACourtPassLoader.publish_files(Docket.objects.get())

        self.assertEqual(NYCoADocument.objects.get().filepath_local, newer)
        self.assertFalse(files)
        self.assertEqual(self.deleted, [])


class NYCoAPartyMergerTest(NYCoAMergerTestCase):
    """Tests for merging the parties and attorneys of a docket."""

    @merger_test(expected_query_count=16)
    def test_merge_creates_party_with_attorney(self) -> None:
        """Does merging a case create its party, party type, attorney, and the role linking them?"""
        attorney = NYCoAAttorneyFactory.create(
            name="Jane Roe",
            firm="Roe & Roe LLP",
            address="1 Main St, Albany, NY",
            phone="(518) 555-1212",
        )
        case = self.case(
            parties=[
                NYCoAPartyFactory.create(
                    name="Smith",
                    party_role_raw="Appellant",
                    representatives=[attorney],
                )
            ]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        docket = merged_docket(result)
        party = docket.parties.get()
        self.assertEqual(party.name, "Smith")
        self.assertEqual(
            PartyType.objects.get(docket=docket, party=party).name, "Appellant"
        )
        role = Role.objects.get(docket=docket, party=party)
        self.assertEqual(role.attorney.name, "Jane Roe")
        self.assertEqual(
            role.attorney.contact_raw, "Roe & Roe LLP\n1 Main St, Albany, NY"
        )
        self.assertEqual(role.attorney.phone, "(518) 555-1212")

    @merger_test(expected_query_count=20)
    def test_merge_makes_the_first_attorney_listed_the_lead(self) -> None:
        """Court-PASS states no attorney's role.

        Is the first attorney it lists for a party stored as that party's lead,
        with the rest unknown?
        """
        case = self.case(
            parties=[
                NYCoAPartyFactory.create(
                    name="Smith",
                    representatives=[
                        NYCoAAttorneyFactory.create(name="Jane Roe"),
                        NYCoAAttorneyFactory.create(name="John Doe"),
                        NYCoAAttorneyFactory.create(name="Ada Poe"),
                    ],
                )
            ]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        roles = {
            role.attorney.name: role.role
            for role in Role.objects.filter(
                docket=merged_docket(result)
            ).select_related("attorney")
        }
        self.assertEqual(
            roles,
            {
                "Jane Roe": Role.ATTORNEY_LEAD,
                "John Doe": Role.UNKNOWN,
                "Ada Poe": Role.UNKNOWN,
            },
        )

    @merger_test(expected_query_count=32)
    def test_merge_attorney_phone_too_long_for_the_column(self) -> None:
        """Court-PASS writes a direct line as `(516) 222-6200 ext: 284`, which is longer than `Attorney.phone` allows. Is the number kept dialable, with the full phone repeated in the contact field only when shortening it lost something?

        A scraped phone also carries whatever whitespace the page's text node
        did, and trimming that is not shortening it.
        """
        for label, scraped_phone, phone, contact_raw in (
            (
                "extension",
                "(516) 222-6200 ext: 284",
                "(516) 222-6200",
                "Roe & Roe LLP\n1 Main St, Albany, NY\n(516) 222-6200 ext: 284",
            ),
            (
                "stray whitespace",
                "  (518) 555-1212\n",
                "(518) 555-1212",
                "Roe & Roe LLP\n1 Main St, Albany, NY",
            ),
        ):
            with self.table_row(label):
                case = self.case(
                    parties=[
                        NYCoAPartyFactory.create(
                            name="Smith",
                            representatives=[
                                NYCoAAttorneyFactory.create(
                                    name="Jane Roe",
                                    firm="Roe & Roe LLP",
                                    address="1 Main St, Albany, NY",
                                    phone=scraped_phone,
                                )
                            ],
                        )
                    ]
                )

                result = NYCoADocketMerger(case, params=None).merge()

                self.assertTrue(result.success)
                attorney = Role.objects.get(
                    docket=merged_docket(result)
                ).attorney
                self.assertEqual(attorney.phone, phone)
                self.assertEqual(attorney.contact_raw, contact_raw)

    @merger_test(expected_query_count=16)
    def test_merge_keeps_role_court_pass_prints(self) -> None:
        """The cross-state party vocabulary has no amicus value.

        Is the role Court-PASS printed kept verbatim?
        """
        case = self.case(
            parties=[
                NYCoAPartyFactory.create(
                    name="Concerned Citizens",
                    party_role_raw="Amicus Curiae",
                    representatives=[NYCoAAttorneyFactory.create()],
                )
            ]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(PartyType.objects.get().name, "Amicus Curiae")

    @merger_test(expected_query_count=12)
    def test_merge_party_type_falls_back_to_vocabulary(self) -> None:
        """With no printed role, does the party type come from the normalized vocabulary?"""
        case = self.case(
            parties=[
                NYCoAPartyFactory.create(
                    name="Smith",
                    party_role_raw="",
                    party_type=ScrapedPartyType.APPELLANT,
                    representatives=[],
                )
            ]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(PartyType.objects.get().name, "Appellant")

    @merger_test(expected_query_count=34)
    def test_remerge_one_name_under_two_roles(self) -> None:
        """In a family case the Court lists one person twice, as the child and as a party. Both are parties in their own right, and a name is all `PartyMerger` matches on, so re-merging must tell them apart by role rather than finding two and giving up on the docket."""
        case = self.case(parties=self.one_name_under_two_roles())

        first = NYCoADocketMerger(case, params=None).merge()
        parties = {
            pt.name: pt.party_id
            for pt in PartyType.objects.filter(party__name="A. R.")
        }
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(first.success)
        self.assertTrue(
            second.success,
            "The second merge must not fail on the shared name.",
        )
        self.assertEqual(Party.objects.filter(name="A. R.").count(), 2)
        self.assertEqual(
            {
                pt.name: pt.party_id
                for pt in PartyType.objects.filter(party__name="A. R.")
            },
            parties,
            "Each role must stay on the party row it was first written to.",
        )

    @merger_test(expected_query_count=38)
    def test_refusing_a_party_costs_only_that_party(self) -> None:
        """A shared name the role cannot separate is one the party merger refuses. That refusal is reported in the docket's own result, so does the rest of the case still merge and stay merged -- the docket merger being atomic notwithstanding?"""
        case = self.case(
            case_name="Matter of A. R.",
            parties=self.one_name_under_two_roles(),
            entries=[NYCoAFilingFactory.create(attachments=[])],
        )
        first = NYCoADocketMerger(case, params=None).merge()
        self.assertTrue(first.success)

        # Neither stored role is one this scrape states, so neither party can
        # be told from the other.
        case.parties[0].party_role_raw = "Appellant"
        case.parties[1].party_role_raw = "Appellee"
        case.case_name = "Matter of A. R. (No. 2)"
        case.decision_date = date(2025, 6, 12)
        case.entries.append(NYCoAFilingFactory.create(attachments=[]))
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertFalse(
            second.success, "The party the merger refused is a failure."
        )
        self.assertEqual(
            list(second.failures),
            ["Party"],
            "Only the party merge failed.",
        )
        docket = merged_docket(first)
        docket.refresh_from_db()
        self.assertEqual(
            docket.case_name,
            "Matter of A. R. (No. 2)",
            "The docket's own fields merged and were committed.",
        )
        self.assertEqual(
            # pyrefly:ignore[missing-attribute]
            docket.nycoa_metadata.decision_date,
            date(2025, 6, 12),
        )
        self.assertEqual(
            NYCoADocketEntry.objects.filter(docket=docket).count(),
            2,
            "The new filing merged alongside the refused party.",
        )
        # The parties the merger refused are left exactly as the first scrape
        # wrote them, rather than being re-roled, duplicated, or pruned.
        self.assertEqual(Party.objects.filter(name="A. R.").count(), 2)
        self.assertEqual(
            sorted(
                PartyType.objects.filter(party__name="A. R.").values_list(
                    "name", flat=True
                )
            ),
            ["Child", "Respondent"],
        )
        self.assertEqual(Role.objects.filter(docket=docket).count(), 2)

    @merger_test(expected_query_count=27)
    def test_remerge_party_whose_role_changed(self) -> None:
        """A respondent becomes a respondent-appellant when the other side cross-appeals. Is that the same party under a new role, rather than a second row?"""
        case = self.case(
            parties=[
                NYCoAPartyFactory.create(
                    name="Smith", party_role_raw="Respondent"
                )
            ]
        )
        first = NYCoADocketMerger(case, params=None).merge()
        original = Party.objects.get(name="Smith")

        case.parties[0].party_role_raw = "Respondent-Appellant"
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(Party.objects.filter(name="Smith").count(), 1)
        self.assertEqual(Party.objects.get(name="Smith").pk, original.pk)
        self.assertEqual(
            PartyType.objects.get(party=original).name, "Respondent-Appellant"
        )
        # The attorney and the role linking them are re-matched too, rather
        # than a second set being written on every scrape.
        self.assertEqual(Attorney.objects.count(), 1)
        self.assertEqual(Role.objects.count(), 1)


class NYCoAPartyMatchTest(NYCoAMergerTestCase):
    """Tests for matching scraped parties that share a name on one docket."""

    @classmethod
    def parties_case(cls, *roles: str) -> NYCoACase:
        """A case whose parties are all named "A. R.", one per role.

        Args:
            *roles: The role Court-PASS prints for each party.

        Returns:
            The scraped case.
        """
        return cls.case(
            parties=[
                NYCoAPartyFactory.create(
                    name="A. R.", party_role_raw=role, representatives=[]
                )
                for role in roles
            ],
            issues=[],
        )

    @staticmethod
    def stored_roles() -> dict[str, int]:
        """The role of each stored "A. R." party row, with the row's pk."""
        return {
            pt.name: pt.party_id
            for pt in PartyType.objects.filter(party__name="A. R.")
        }

    @merger_test(expected_query_count=20)
    def test_same_name_unstored_role_updates_last_row(self) -> None:
        """A party whose role is stored for no party of its name takes the one same-named row the other scraped party left unclaimed."""
        first = NYCoADocketMerger(
            self.parties_case("Child", "Respondent"), params=None
        ).merge()
        stored = self.stored_roles()

        second = NYCoADocketMerger(
            self.parties_case("Child", "Appellant"), params=None
        ).merge()

        self.assertTrue(first.success)
        self.assertTrue(second.success, second.failures)
        self.assertEqual(Party.objects.filter(name="A. R.").count(), 2)
        self.assertEqual(
            self.stored_roles(),
            {"Child": stored["Child"], "Appellant": stored["Respondent"]},
        )

    @merger_test(expected_query_count=18)
    def test_two_same_name_unstored_roles_are_refused(self) -> None:
        """Are two parties whose roles are stored for no party of their name, with the same rows left to both, refused and the stored parties left alone?"""
        first = NYCoADocketMerger(
            self.parties_case("Child", "Respondent"), params=None
        ).merge()
        stored = self.stored_roles()

        second = NYCoADocketMerger(
            self.parties_case("Appellant", "Appellee"), params=None
        ).merge()

        self.assertTrue(first.success)
        self.assertEqual(len(second.failures["Party"]), 2)
        self.assertEqual(Party.objects.filter(name="A. R.").count(), 2)
        self.assertEqual(self.stored_roles(), stored)

    @merger_test(expected_query_count=16)
    def test_two_same_name_parties_with_third_stored_role_are_refused(
        self,
    ) -> None:
        """Are two parties sharing a name refused when the one stored party of that name holds a third role, rather than both updating it?"""
        first = NYCoADocketMerger(
            self.parties_case("Child"), params=None
        ).merge()
        stored = self.stored_roles()

        second = NYCoADocketMerger(
            self.parties_case("Appellant", "Respondent"), params=None
        ).merge()

        self.assertTrue(first.success)
        self.assertEqual(len(second.failures["Party"]), 2)
        self.assertEqual(Party.objects.filter(name="A. R.").count(), 1)
        self.assertEqual(self.stored_roles(), stored)

    @merger_test(expected_query_count=19)
    def test_conflated_party_splits_on_rescrape(self) -> None:
        """When two scraped parties share a name and the one stored party holds the role of one of them, does the other get a party of its own and the first keep the stored one?"""
        first = NYCoADocketMerger(
            self.parties_case("Respondent"), params=None
        ).merge()
        stored = self.stored_roles()

        second = NYCoADocketMerger(
            self.parties_case("Child", "Respondent"), params=None
        ).merge()

        self.assertTrue(first.success)
        self.assertTrue(second.success, second.failures)
        self.assertEqual(Party.objects.filter(name="A. R.").count(), 2)
        roles = self.stored_roles()
        self.assertEqual(roles["Respondent"], stored["Respondent"])
        self.assertNotEqual(roles["Child"], stored["Respondent"])
        self.assertEqual(set(roles), {"Child", "Respondent"})

    @merger_test(expected_query_count=17)
    def test_party_with_two_roles_on_docket_is_one_candidate(self) -> None:
        """Is a party holding two roles on the docket a single candidate for its name, rather than an ambiguity between its two roles?"""
        first = NYCoADocketMerger(
            self.parties_case("Respondent"), params=None
        ).merge()
        original = Party.objects.get(name="A. R.")
        PartyType.objects.create(
            docket=merged_docket(first), party=original, name="Child"
        )

        second = NYCoADocketMerger(
            self.parties_case("Appellant"), params=None
        ).merge()

        # `PartyTypeMerger` keys a through row on the docket and the party
        # alone, so it cannot choose between the party's two roles; that is
        # its failure, not the party's.
        self.assertNotIn("Party", second.failures)
        self.assertEqual(
            list(
                Party.objects.filter(name="A. R.").values_list("pk", flat=True)
            ),
            [original.pk],
        )
