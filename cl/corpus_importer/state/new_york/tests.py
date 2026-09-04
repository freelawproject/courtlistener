"""Tests for the New York Court of Appeals (Court-PASS) mergers."""

from datetime import date
from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils.text import slugify
from juriscraper.state.docket import PartyType as ScrapedPartyType
from juriscraper.state.new_york.nycourts_gov.vocabularies import (
    FilingDocType,
    FilingRole,
    FilingType,
    IssueCategory,
    IssueSubcategory,
)

from cl.corpus_importer.state.new_york.factories import (
    NYCoAAttorneyFactory,
    NYCoACaseFactory,
    NYCoAFileFactory,
    NYCoAFilingFactory,
    NYCoAIssueFactory,
    NYCoAPartyFactory,
)
from cl.corpus_importer.state.new_york.mergers import NYCoADocketMerger
from cl.corpus_importer.state.new_york.nycourts_gov import NYCoACase, NYCoAFile
from cl.corpus_importer.state.new_york.storage import (
    PRIVATE_PREFIX,
    PUBLISHED_PREFIX,
    copy_file,
    discard_private_file,
    withdraw_file,
)
from cl.corpus_importer.state.new_york.utils import NYCOA_COURT_ID
from cl.corpus_importer.state.tests import merger_test
from cl.corpus_importer.state.utils import MergeResult
from cl.lib.model_helpers import make_pdf_path
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import Docket
from cl.search.state.new_york.models import (
    RECAP_ROOT,
    RECAP_THUMBNAIL_ROOT,
    SHA256_NAME_LENGTH,
    NYCoADocketEntry,
    NYCoADocketIssue,
    NYCoADocketMetadata,
    NYCoADocument,
)
from cl.search.state.new_york.vocabularies import UNASSIGNED, UNKNOWN
from cl.tests.cases import SimpleTestCase, TestCase

DOCKET_NUMBER = "APL-2024-00177"
DOCKET_NUMBER_CORE = "apl202400177"


def published_key(file: NYCoAFile, docket_number: str = DOCKET_NUMBER) -> str:
    """Where publishing a scraped file puts it.

    Spelled out from the scrape rather than taken from `NYCoADocument`, so that
    a test asserting on a published path is checking the layout rather than
    agreeing with whatever the model just built.

    :param file: The file as the scraper handed it over.
    :param docket_number: The docket number of the case it belongs to, which
        names the directory it is filed in.
    :return: The key the public bucket holds it under.
    """
    stored = PurePosixPath(file.local_path)
    bucket = f"gov.uscourts.{NYCOA_COURT_ID}.{docket_number}"
    name = ".".join(
        [
            bucket,
            stored.stem.removeprefix(f"{docket_number}_"),
            file.content_hash[:SHA256_NAME_LENGTH],
        ]
    )
    return f"{RECAP_ROOT}/{bucket}/{name}{stored.suffix}"


class NYCoAMergerTestCase(TestCase):
    """Shared setup for the NYCoA merger tests.

    Stands in for S3 throughout: publishing a document moves its file between
    buckets, so every merge that touches a file would otherwise reach for the
    network. `published`, `discarded` and `withdrawn` record what the merge
    asked for, and `publish_fails` makes the copy report failure the way one
    the bucket refused would.
    """

    published: list[tuple[str, str]]
    discarded: list[str]
    withdrawn: list[str]
    publish_fails: bool

    @classmethod
    def setUpTestData(cls) -> None:
        cls.ny = CourtFactory.create(id="ny")

    def setUp(self) -> None:
        super().setUp()
        self.published = []
        self.discarded = []
        self.withdrawn = []
        self.publish_fails = False

        def copy_file(
            private_key: str, published_key: str, content_type: str = ""
        ) -> bool:
            if self.publish_fails:
                return False
            self.published.append((private_key, published_key))
            return True

        for name, double in (
            ("copy_file", copy_file),
            ("discard_private_file", self.discarded.append),
            ("withdraw_file", self.withdrawn.append),
        ):
            patcher = patch(
                f"cl.corpus_importer.state.new_york.mergers.{name}", double
            )
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def merged_docket(result: MergeResult) -> Docket:
        return Docket.objects.get(pk=next(iter(result.creates["Docket"])))

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


class NYCoADocketMergerTest(NYCoAMergerTestCase):
    """Tests for merging the docket itself."""

    @merger_test(expected_query_count=9)
    def test_merge_creates_docket(self) -> None:
        """Does merging a case with no existing docket create one with the
        scrape's docket-level values?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            case_name="People v Padilla-Zuniga",
            case_name_full="The People of the State of New York v Padilla-Zuniga",
            case_name_short="Padilla-Zuniga",
            date_filed=date(2024, 3, 1),
            argument_date=date(2025, 1, 14),
            entries=[],
            parties=[],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        docket = self.merged_docket(result)
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

    @merger_test(expected_query_count=9)
    def test_merge_updates_existing_docket(self) -> None:
        """Does a docket that already exists get updated rather than
        duplicated?"""
        docket = self.existing_docket()
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            case_name="Matter of Smith",
            argument_date=date(2025, 2, 11),
            entries=[],
            parties=[],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertNotIn("Docket", result.creates)
        self.assertEqual(Docket.objects.filter(court_id="ny").count(), 1)
        docket.refresh_from_db()
        self.assertEqual(docket.case_name, "Matter of Smith")
        self.assertEqual(docket.date_argued, date(2025, 2, 11))

    @merger_test(expected_query_count=0)
    def test_merge_unknown_court_fails(self) -> None:
        """Is a case from a New York court we don't model refused?"""
        case = NYCoACaseFactory.create(court_id="nyappdiv1")

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertFalse(result.success)
        self.assertFalse(Docket.objects.exists())

    @merger_test(expected_query_count=0)
    def test_merge_unusable_docket_number_fails(self) -> None:
        """Is a case whose docket number we can't normalize refused, rather
        than merged onto a docket we can never match again?"""
        case = NYCoACaseFactory.create(docket_number="Motion No. 12")

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertFalse(result.success)
        self.assertFalse(Docket.objects.exists())

    @merger_test(expected_query_count=9)
    def test_merge_keeps_existing_dates(self) -> None:
        """Court-PASS has no filing date of its own. Does a scrape leave a
        date another source established alone?"""
        docket = self.existing_docket()
        docket.date_filed = date(2020, 5, 5)
        docket.date_argued = date(2021, 6, 6)
        docket.save()
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            date_filed=None,
            argument_date=None,
            entries=[],
            parties=[],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        docket.refresh_from_db()
        self.assertEqual(docket.date_filed, date(2020, 5, 5))
        self.assertEqual(docket.date_argued, date(2021, 6, 6))

    @merger_test(expected_query_count=17)
    def test_merge_date_last_filing_uses_latest_filing(self) -> None:
        """Is date_last_filing the most recent filing date on the docket?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
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
            parties=[],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        docket = self.merged_docket(result)
        self.assertEqual(docket.date_last_filing, date(2024, 9, 15))


class NYCoADocketMetadataMergerTest(NYCoAMergerTestCase):
    """Tests for merging the NYCoA-only docket metadata, which hangs off
    `Docket` through a reverse one-to-one relation."""

    @merger_test(expected_query_count=6)
    def test_merge_creates_metadata(self) -> None:
        """Does merging a case create its metadata row?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
            issues=[],
            decision_date=date(2025, 4, 17),
            official_citation="41 NY3d 1",
            lower_court_citation="102 AD3d 543",
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        metadata = self.merged_docket(result).nycoa_metadata
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
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
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

    @merger_test(expected_query_count=9)
    def test_merge_creates_issue(self) -> None:
        """Does merging a case create an issue row with its category
        normalized and the Court's own string kept?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
            issues=[
                NYCoAIssueFactory.create(
                    category_raw="Judgments--Confession of Judgment",
                    detail="Whether the judgments were properly entered.",
                )
            ],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        issue = self.merged_docket(result).nycoa_metadata.issues.get()
        self.assertEqual(issue.category, IssueCategory.JUDGMENTS.code)
        self.assertEqual(
            issue.subcategory, IssueSubcategory.CONFESSION_OF_JUDGMENT.code
        )
        self.assertEqual(
            issue.category_raw, "Judgments--Confession of Judgment"
        )
        self.assertEqual(
            issue.detail, "Whether the judgments were properly entered."
        )

    @merger_test(expected_query_count=11)
    def test_merge_creates_issues_sharing_a_category(self) -> None:
        """The Court assigns a case two distinct issues under one category and
        tells them apart only by what it says about each. Does each get its own
        row, rather than the second colliding with the first?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
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
        issues = self.merged_docket(result).nycoa_metadata.issues.all()
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

    @merger_test(expected_query_count=17)
    def test_remerge_issues_sharing_a_category_is_idempotent(self) -> None:
        """Re-scraping a case whose issues share a category must match both
        rows rather than replacing one with the other."""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
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

    @merger_test(expected_query_count=15)
    def test_remerge_reworded_issue_updates_it_in_place(self) -> None:
        """The Court rewords a description it has already published. Does the
        issue keep its row, rather than the old one being replaced?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
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

    @merger_test(expected_query_count=19)
    def test_remerge_rewords_an_issue_sharing_a_category(self) -> None:
        """Rewording one of two issues that share a category is the one case
        the merger cannot resolve: with the description gone, nothing says which
        of the two the Court restated. Is it replaced rather than matched to
        either row, leaving the issue the Court did not touch alone?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
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
        self.assertTrue(second.success)
        self.assertEqual(NYCoADocketIssue.objects.count(), 2)
        self.assertEqual(
            NYCoADocketIssue.objects.get(detail="Untouched.").pk,
            untouched.pk,
        )
        self.assertFalse(
            NYCoADocketIssue.objects.filter(pk=reworded.pk).exists(),
            "The reworded issue is a new row; the old one is pruned.",
        )

    @merger_test(expected_query_count=17)
    def test_remerge_drops_an_issue_sharing_a_category(self) -> None:
        """A case that stated two issues under one category now states one of
        them. Is the other pruned, and does the survivor keep its row?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
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
    def test_merge_unrecognized_issue_category(self) -> None:
        """Is a category this vocabulary doesn't cover flagged rather than
        dropped, so the raw value survives?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
            issues=[
                # The scraper could classify neither half of this one.
                NYCoAIssueFactory.create(
                    category_raw="Cryptocurrency--Staking",
                    category=None,
                    subcategory=None,
                )
            ],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        issue = self.merged_docket(result).nycoa_metadata.issues.get()
        self.assertEqual(issue.category, UNASSIGNED)
        self.assertEqual(issue.subcategory, UNASSIGNED)
        self.assertEqual(issue.category_raw, "Cryptocurrency--Staking")

    @merger_test(expected_query_count=9)
    def test_merge_issue_without_subcategory(self) -> None:
        """The Court states some issues as a bare category. Is the subcategory
        left unknown?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
            issues=[NYCoAIssueFactory.create(category_raw="Crimes")],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        issue = self.merged_docket(result).nycoa_metadata.issues.get()
        self.assertEqual(issue.category, IssueCategory.CRIMES.code)
        self.assertEqual(issue.subcategory, UNKNOWN)
        self.assertEqual(issue.category_raw, "Crimes")

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
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            entries=[],
            parties=[],
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
        """A scrape with no issues at all is a partial scrape. Does it leave
        the issues already recorded alone?"""
        docket = self.existing_docket()
        metadata = NYCoADocketMetadata.objects.create(docket=docket)
        existing = NYCoADocketIssue.objects.create(
            metadata=metadata,
            category=IssueCategory.TAXATION.code,
            category_raw="Taxation--Sales Tax",
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[], parties=[], issues=[]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(metadata.issues.get().pk, existing.pk)


class NYCoADocketEntryMergerTest(NYCoAMergerTestCase):
    """Tests for merging a docket's filings."""

    @merger_test(expected_query_count=13)
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
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing], parties=[]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertIn("NYCoADocketEntry", result.creates)
        merged = self.merged_docket(result).nycoa_docket_entries.get()
        self.assertEqual(merged.docket_entry_id, "e:appellant-brief:smith:1")
        self.assertEqual(merged.entry_index, 3)
        self.assertEqual(merged.filing_type, FilingType.APPELLANT_BRIEF.code)
        self.assertEqual(merged.filing_type_raw, "Appellant Brief")
        self.assertEqual(merged.filing_role, FilingRole.APPELLANT.code)
        self.assertEqual(merged.filing_doctype, FilingDocType.BRIEF.code)
        self.assertIsNone(merged.party_id)
        self.assertEqual(merged.date_filed, date(2024, 6, 1))
        self.assertEqual(merged.date_due, date(2024, 5, 15))

    @merger_test(expected_query_count=13)
    def test_merge_unrecognized_filing_type(self) -> None:
        """Court-PASS listing a filing type this vocabulary doesn't cover is
        the drift signal. Is it stored as unassigned while the raw value
        survives?"""
        filing = NYCoAFilingFactory.create(
            raw_filing_type="Appellant Sur-Reply Brief",
            entry_role=FilingRole.APPELLANT,
            entry_doctype=FilingDocType.BRIEF,
            attachments=[],
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing], parties=[]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        merged = self.merged_docket(result).nycoa_docket_entries.get()
        self.assertEqual(merged.filing_type, UNASSIGNED)
        self.assertEqual(merged.filing_type_raw, "Appellant Sur-Reply Brief")
        self.assertEqual(merged.filing_role, FilingRole.APPELLANT.code)

    @merger_test(expected_query_count=12)
    def test_merge_filing_reconstructed_from_document(self) -> None:
        """Does a filing the scraper reconstructed from a document merge with
        no date and no raw filing type?"""
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
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing], parties=[]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        merged = self.merged_docket(result).nycoa_docket_entries.get()
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

    @merger_test(expected_query_count=23)
    def test_remerge_updates_filing_fields(self) -> None:
        """Does a filing matched by its entry ID pick up new values?"""
        filing = NYCoAFilingFactory.create(
            docket_entry_id="e:appellant-brief:smith:1",
            date_filed=None,
            entry_index=1,
            attachments=[],
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing], parties=[]
        )
        NYCoADocketMerger(case, params=None).merge()

        updated = filing.model_copy(
            update={"date_filed": date(2024, 6, 1), "entry_index": 2}
        )
        result = NYCoADocketMerger(
            # The same issues, because this is the same case scraped again and
            # an issue is identified by what the Court said about it.
            NYCoACaseFactory.create(
                docket_number=DOCKET_NUMBER,
                entries=[updated],
                parties=[],
                issues=case.issues,
            ),
            params=None,
        ).merge()

        self.assertTrue(result.success)
        self.assertEqual(NYCoADocketEntry.objects.count(), 1)
        merged = NYCoADocketEntry.objects.get()
        self.assertEqual(merged.date_filed, date(2024, 6, 1))
        self.assertEqual(merged.entry_index, 2)

    @merger_test(expected_query_count=15)
    def test_merge_prunes_filings_missing_from_scrape(self) -> None:
        """Court-PASS lists a case's filings in full, so does a filing that is
        gone from the scrape get deleted?"""
        docket = self.existing_docket()
        stale = NYCoADocketEntry.objects.create(
            docket=docket,
            docket_entry_id="e:withdrawn-brief:jones:1",
            filing_type_raw="Withdrawn Brief",
        )
        filing = NYCoAFilingFactory.create(
            docket_entry_id="e:appellant-brief:smith:1", attachments=[]
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing], parties=[]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertFalse(
            NYCoADocketEntry.objects.filter(pk=stale.pk).exists(),
            "A filing the scrape no longer reports should be pruned.",
        )
        self.assertEqual(
            docket.nycoa_docket_entries.get().docket_entry_id,
            "e:appellant-brief:smith:1",
        )

    @merger_test(expected_query_count=18)
    def test_merge_links_filing_to_docket_party(self) -> None:
        """Is a filing's party resolved to a party on the docket?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[
                NYCoAPartyFactory.create(name="Smith", representatives=[])
            ],
            entries=[NYCoAFilingFactory.create(party="Smith", attachments=[])],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        merged = self.merged_docket(result).nycoa_docket_entries.get()
        self.assertEqual(merged.party, Party.objects.get(name="Smith"))
        self.assertEqual(merged.party_name, "Smith")

    @merger_test(expected_query_count=22)
    def test_merge_links_filing_to_party_in_the_filing_role(self) -> None:
        """In a family case the Court lists one person under two roles, so a
        filing's party name finds two parties. Is the filing linked to the one
        whose role the filing itself states, rather than to whichever was
        written first?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
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
        merged = self.merged_docket(result).nycoa_docket_entries.get()
        self.assertEqual(
            merged.party_id,
            PartyType.objects.get(name="Respondent").party_id,
        )

    @merger_test(expected_query_count=18)
    def test_merge_unknown_filing_party_leaves_fk_null(self) -> None:
        """A filer who isn't a party on the docket -- one with no attorney of
        record, or one the FILINGS table names in its own words -- has no party
        row to point at. Is the FK left null rather than the merge failing?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[
                NYCoAPartyFactory.create(name="Smith", representatives=[])
            ],
            entries=[
                NYCoAFilingFactory.create(
                    party="Board of Elections", attachments=[]
                )
            ],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        merged = self.merged_docket(result).nycoa_docket_entries.get()
        self.assertIsNone(merged.party_id)
        # The name the FILINGS table printed survives the unresolved FK.
        self.assertEqual(merged.party_name, "Board of Elections")

    @merger_test(expected_query_count=27)
    def test_remerge_keeps_resolved_filing_party(self) -> None:
        """Does a later scrape that can't resolve the party keep the party a
        previous scrape resolved?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
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
        second = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[],
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

    @staticmethod
    def case_with_files(*files, **filing_kwargs) -> NYCoACase:
        filing = NYCoAFilingFactory.create(
            attachments=list(files), **filing_kwargs
        )
        return NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing], parties=[]
        )

    @merger_test(expected_query_count=16)
    def test_merge_creates_documents(self) -> None:
        """Does merging a filing create its documents with the values the file
        name yielded?"""
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

        with self.captureOnCommitCallbacks(execute=True):
            result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertIn("NYCoADocument", result.creates)
        merged = (
            self.merged_docket(result)
            .nycoa_docket_entries.get()
            .documents.get()
        )
        self.assertEqual(
            merged.file_name, "SmithvJones-app-Smith-Rec-vol3.pdf"
        )
        self.assertEqual(merged.content_type, "application/pdf")
        self.assertTrue(merged.available)
        self.assertEqual(merged.doc_role, FilingRole.APPELLANT)
        self.assertEqual(merged.doc_party, "Smith")
        self.assertEqual(merged.doc_type, FilingDocType.RECORD)
        self.assertEqual(merged.volume, 3)
        self.assertEqual(merged.part, 2)
        # The scraper left the file in the bucket it writes its raw responses
        # to, so the merge moves it into the one CourtListener serves, under
        # the name the scraper gave it -- rather than the Court's own -- with
        # the file's hash appended.
        self.assertEqual(merged.sha256, file.content_hash)
        self.assertEqual(merged.file_size, file.file_size)
        self.assertEqual(merged.filepath_local, published_key(file))
        self.assertEqual(
            self.published,
            [
                (
                    f"{PRIVATE_PREFIX}smith-rec-vol3.pdf",
                    merged.filepath_local.name,
                )
            ],
        )

    @merger_test(expected_query_count=16)
    def test_merge_oral_argument_recording(self) -> None:
        """Oral argument recordings are playlists, not PDFs. Does the content
        type survive the merge so the file pass can route them?"""
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
        self.assertEqual(
            merged.filepath_local,
            published_key(file),
            "A playlist is published like any other file, keeping its own "
            "extension; the extraction sweep leaves it alone because it is "
            "not a PDF.",
        )

    @merger_test(expected_query_count=16)
    def test_merge_unstorable_volume(self) -> None:
        """A volume is read out of the file name, and a name whose extension is
        digits reads as a number too large for the column. Does the file still
        merge, without its volume?"""
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
    def test_the_path_a_document_is_stored_at_is_unique(self) -> None:
        """`get_pdf_path` files a whole case in one directory, so no two of a
        filing's files may publish under the same name.

        Stated with the names the scraper really gives them -- the docket
        number, the Court's own name slugified, and an ordinal -- against the
        two things that make Court-PASS names hard to keep apart: a case name
        with a dot in it, which a stem would cut the volume off of, and two
        names differing only in punctuation, which slugify flattens together.

        The published name takes the scraper's name as it stands rather than
        slugifying it again, so it is the scraper that has to have kept these
        apart. That is what this asserts on: `slugify` here stands in for what
        the scraper did before storing the file, not for anything the merge
        does afterwards."""
        court_names = [
            "IKB v. Wells Fargo-app-Wells Fargo-rec-Volume1",
            "IKB v. Wells Fargo-app-Wells Fargo-rec-Volume2",
            "CortlandtvBonderman-app-TPG APAX-appdx-vol1",
            "CortlandtvBonderman-app-TPG, APAX-appdx-vol1",
        ]
        files = [
            NYCoAFileFactory.create(
                file_name=name,
                local_path=f"{PRIVATE_PREFIX}nycourts_gov/"
                f"{DOCKET_NUMBER}_{slugify(name)}_{index}.pdf",
            )
            for index, name in enumerate(court_names)
        ]
        case = self.case_with_files(*files)

        with self.captureOnCommitCallbacks(execute=True):
            result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        paths = set(
            NYCoADocument.objects.values_list("filepath_local", flat=True)
        )
        self.assertEqual(
            len(paths),
            len(court_names),
            f"Two documents share a path: {paths}",
        )
        self.assertIn(
            published_key(files[1]),
            paths,
            f"The volume has to survive into the path: {paths}",
        )
        self.assertIn(
            "ikb-v-wells-fargo-app-wells-fargo-rec-volume2",
            published_key(files[1]),
            "The readable part of the name has to survive the hash being "
            "appended to it.",
        )

    @merger_test(expected_query_count=27)
    def test_remerge_documents_is_idempotent(self) -> None:
        """Does merging the same case twice avoid duplicating documents?"""
        case = self.case_with_files(NYCoAFileFactory.create())

        first = NYCoADocketMerger(case, params=None).merge()
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertNotIn("NYCoADocument", second.creates)
        self.assertEqual(NYCoADocument.objects.count(), 1)

    @merger_test(expected_query_count=17)
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

    @merger_test(expected_query_count=16)
    def test_merge_file_the_scraper_could_not_fetch(self) -> None:
        """A sealed file is listed but never served, so the scraper has no path
        to report. Is the document still recorded, with no stored file?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(available=False, local_path="")
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        merged = NYCoADocument.objects.get()
        self.assertFalse(merged.available)
        self.assertEqual(merged.filepath_local, "")
        self.assertIsNone(
            merged.ocr_status,
            "Nothing was stored, so nothing is waiting to be extracted.",
        )
        self.assertEqual(
            (merged.sha256, merged.file_size),
            ("", None),
            "Nothing read the bytes, so nothing can describe them.",
        )

    @merger_test(expected_query_count=30)
    def test_remerge_a_corrected_file_replaces_the_published_copy(
        self,
    ) -> None:
        """The Court reissues a document under the name it first used, so the
        published name carries the file's hash to keep the correction from
        landing on top of the copy it replaces. Does a rescrape whose file
        hashes differently publish beside the old one, take the old one down,
        and send the document back for extraction?"""
        original = NYCoAFileFactory.create(
            file_name="SmithvJones-app-Smith-brf.pdf",
            available=True,
            local_path=f"{PRIVATE_PREFIX}brf.pdf",
        )
        case = self.case_with_files(
            original, docket_entry_id="e:appellant-brief:smith:1"
        )
        with self.captureOnCommitCallbacks(execute=True):
            NYCoADocketMerger(case, params=None).merge()
        extracted = NYCoADocument.objects.get()
        extracted.ocr_status = NYCoADocument.OCR_COMPLETE
        extracted.page_count = 12
        extracted.save()

        corrected = NYCoAFileFactory.create(
            file_name="SmithvJones-app-Smith-brf.pdf",
            available=True,
            local_path=f"{PRIVATE_PREFIX}brf-corrected.pdf",
        )
        second = self.case_with_files(
            corrected, docket_entry_id="e:appellant-brief:smith:1"
        )
        second.issues = case.issues
        with self.captureOnCommitCallbacks(execute=True):
            result = NYCoADocketMerger(second, params=None).merge()

        self.assertTrue(result.success)
        merged = NYCoADocument.objects.get()
        self.assertNotEqual(
            published_key(original),
            published_key(corrected),
            "Two different files must not share a published name.",
        )
        self.assertEqual(merged.filepath_local, published_key(corrected))
        self.assertEqual(merged.sha256, corrected.content_hash)
        self.assertEqual(merged.file_size, corrected.file_size)
        self.assertEqual(
            self.withdrawn,
            [published_key(original)],
            "The copy the correction replaces is no longer served.",
        )
        self.assertIsNone(
            merged.ocr_status, "A replaced file has to be extracted again."
        )
        self.assertIsNone(
            merged.page_count,
            "The pages were counted off the copy that has been replaced.",
        )

    @merger_test(expected_query_count=29)
    def test_remerge_keeps_stored_path_when_scrape_reports_none(self) -> None:
        """Does a later scrape that did not fetch the file leave the path an
        earlier one recorded, rather than blanking it?

        The Court still lists the file, which is what tells this apart from
        the file it has stopped serving."""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                available=True,
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        NYCoADocketMerger(case, params=None).merge()
        published = NYCoADocument.objects.get().filepath_local.name

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
        self.assertEqual(
            NYCoADocument.objects.get().filepath_local,
            published,
            "The file is still where the first merge published it.",
        )

    @merger_test(expected_query_count=30)
    def test_remerge_at_a_new_path_sends_the_file_back_for_extraction(
        self,
    ) -> None:
        """The scraper fetching a file again means what was extracted came from
        a copy that has been replaced. Does the document go back in front of the
        extraction sweep?

        Stated with the scraper writing straight into the public bucket, which
        is where it is headed and the only kind of new path a published
        document takes; see `_keep_stored_file`."""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path=f"{PUBLISHED_PREFIX}first.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        NYCoADocketMerger(case, params=None).merge()
        extracted = NYCoADocument.objects.get()
        extracted.ocr_status = NYCoADocument.OCR_COMPLETE
        extracted.save()

        second = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path=f"{PUBLISHED_PREFIX}second.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        second.issues = case.issues
        with self.captureOnCommitCallbacks(execute=True):
            result = NYCoADocketMerger(second, params=None).merge()

        self.assertTrue(result.success)
        merged = NYCoADocument.objects.get()
        self.assertEqual(
            merged.filepath_local, f"{PUBLISHED_PREFIX}second.pdf"
        )
        self.assertEqual(
            self.published,
            [],
            "The scraper published it, so there is nothing to move.",
        )
        self.assertEqual(
            self.withdrawn,
            [f"{PUBLISHED_PREFIX}first.pdf"],
            "The copy it replaced is no longer served.",
        )
        self.assertIsNone(
            merged.ocr_status,
            "A replaced file has to be extracted again.",
        )

    @merger_test(expected_query_count=27)
    def test_remerge_at_a_stale_scrape_key_keeps_the_published_file(
        self,
    ) -> None:
        """The scrape key a document was published from names nothing once the
        move has run. Does re-loading the same run leave the published copy
        alone rather than pointing the document back at a file that is gone?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        with self.captureOnCommitCallbacks(execute=True):
            NYCoADocketMerger(case, params=None).merge()
        published = NYCoADocument.objects.get().filepath_local.name

        with self.captureOnCommitCallbacks(execute=True):
            result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(NYCoADocument.objects.get().filepath_local, published)
        self.assertEqual(
            len(self.published), 1, "The file is only ever moved once."
        )
        self.assertEqual(self.withdrawn, [])

    @merger_test(expected_query_count=29)
    def test_remerge_at_the_same_path_leaves_extraction_alone(self) -> None:
        """Re-scraping a file that has not moved must not throw away text
        already extracted from it."""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        NYCoADocketMerger(case, params=None).merge()
        extracted = NYCoADocument.objects.get()
        extracted.ocr_status = NYCoADocument.OCR_COMPLETE
        extracted.save()

        second = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        second.issues = case.issues
        result = NYCoADocketMerger(second, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(
            NYCoADocument.objects.get().ocr_status,
            NYCoADocument.OCR_COMPLETE,
            "The file did not move, so its extracted text still stands.",
        )


class NYCoAStorageTest(SimpleTestCase):
    """Tests for the bucket-to-bucket move publishing is built on.

    The merger tests stand in for this module, so this is where the S3 calls
    it makes are pinned down.
    """

    PRIVATE_KEY = f"{PRIVATE_PREFIX}abc123.pdf"
    PUBLISHED_KEY = f"{PUBLISHED_PREFIX}42-brief.pdf"

    def setUp(self) -> None:
        super().setUp()
        self.storage = MagicMock()
        self.storage.exists.return_value = False
        self.storage.get_object_parameters.return_value = {
            "CacheControl": "max-age=315360000"
        }
        self.client = self.storage.connection.meta.client
        patcher = patch(
            "cl.corpus_importer.state.new_york.storage._document_storage",
            return_value=self.storage,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def refusal() -> ClientError:
        return ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "nope"}},
            "CopyObject",
        )

    @staticmethod
    def missing_source() -> ClientError:
        return ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "gone"}},
            "CopyObject",
        )

    def test_copy_describes_how_the_file_should_be_served(self) -> None:
        """Does the copy land in the public bucket with the ACL, cache headers
        and content type a file served from there needs?"""
        self.assertTrue(
            copy_file(self.PRIVATE_KEY, self.PUBLISHED_KEY, "application/pdf")
        )

        self.client.copy_object.assert_called_once_with(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=self.PUBLISHED_KEY,
            CopySource={
                "Bucket": settings.AWS_PRIVATE_STORAGE_BUCKET_NAME,
                "Key": self.PRIVATE_KEY,
            },
            MetadataDirective="REPLACE",
            CacheControl="max-age=315360000",
            ACL=settings.AWS_DEFAULT_ACL,
            ContentType="application/pdf",
        )

    def test_copy_leaves_the_private_original_alone(self) -> None:
        """Copying is the half of the move that runs inside the merge's
        transaction, so it must not be the half that deletes anything."""
        copy_file(self.PRIVATE_KEY, self.PUBLISHED_KEY)

        self.client.delete_object.assert_not_called()

    def test_copy_without_a_content_type_leaves_it_to_s3(self) -> None:
        """Court-PASS does not always state a MIME type. Is the argument left
        off rather than sent empty, which would serve the file as nothing?"""
        copy_file(self.PRIVATE_KEY, self.PUBLISHED_KEY)

        self.assertNotIn(
            "ContentType", self.client.copy_object.call_args.kwargs
        )

    def test_copy_reports_a_refusal(self) -> None:
        """A copy that did not happen must not be reported as published."""
        self.client.copy_object.side_effect = self.refusal()

        self.assertFalse(copy_file(self.PRIVATE_KEY, self.PUBLISHED_KEY))

    def test_copy_accepts_a_file_that_is_already_published(self) -> None:
        """The move deletes the original, so a merge that published a file and
        then rolled back leaves nothing to copy from. Is finding the file
        already where it belongs treated as the move finishing rather than as
        a failure?"""
        self.client.copy_object.side_effect = self.missing_source()
        self.storage.exists.return_value = True

        self.assertTrue(copy_file(self.PRIVATE_KEY, self.PUBLISHED_KEY))
        self.storage.exists.assert_called_once_with(self.PUBLISHED_KEY)

    def test_discard_deletes_from_the_private_bucket(self) -> None:
        """Does dropping the original take it out of the private bucket, and
        only the private one?"""
        discard_private_file(self.PRIVATE_KEY)

        self.client.delete_object.assert_called_once_with(
            Bucket=settings.AWS_PRIVATE_STORAGE_BUCKET_NAME,
            Key=self.PRIVATE_KEY,
        )

    def test_discard_swallows_a_refusal(self) -> None:
        """The file is published either way, so an original that will not
        delete is a duplicate in a bucket nothing serves, not a failure."""
        self.client.delete_object.side_effect = self.refusal()

        discard_private_file(self.PRIVATE_KEY)

    def test_withdraw_deletes_from_the_public_bucket(self) -> None:
        """Does withdrawing a file take it out of the bucket the site serves?"""
        withdraw_file(self.PUBLISHED_KEY)

        self.storage.delete.assert_called_once_with(self.PUBLISHED_KEY)

    def test_withdraw_swallows_a_refusal(self) -> None:
        """The row is already gone by the time this runs, so a file left
        behind must not fail the load."""
        self.storage.delete.side_effect = self.refusal()

        withdraw_file(self.PUBLISHED_KEY)


class NYCoADocumentPublishTest(NYCoAMergerTestCase):
    """Tests for moving a scraped file into the bucket CourtListener serves,
    and for taking it back down again."""

    @staticmethod
    def case_with_files(*files, **filing_kwargs) -> NYCoACase:
        filing = NYCoAFilingFactory.create(
            attachments=list(files), **filing_kwargs
        )
        return NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing], parties=[]
        )

    #: A scrape key in the shape the scraper really writes: the docket number,
    #: the Court's own name slugified, and an ordinal. The published name is
    #: built from this verbatim rather than slugified again, so a fixture that
    #: was not already slug-safe would test a name the scraper cannot produce.
    STORED_PATH = (
        f"{PRIVATE_PREFIX}nycourts_gov/"
        f"{DOCKET_NUMBER}_smithvjones-app-smith-brf_1.pdf"
    )
    #: What survives of that name once the docket number the bucket already
    #: states has been taken off it.
    STORED_STEM = "smithvjones-app-smith-brf_1"

    def stored_document(self, **overrides) -> NYCoADocument:
        """A document whose file is still where the scraper left it, which is
        the path and hash `make_filename` reads.

        :param overrides: Fields to set on the document.
        :return: The saved document.
        """
        entry = NYCoADocketEntry.objects.create(
            docket=self.existing_docket(),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        return NYCoADocument.objects.create(
            **{
                "docket_entry": entry,
                "file_name": "SmithvJones-app-Smith-brf.pdf",
                "filepath_local": self.STORED_PATH,
            }
            | overrides
        )

    @merger_test(expected_query_count=0)
    def test_published_prefix_matches_pdf_path(self) -> None:
        """`PUBLISHED_PREFIX` is written out rather than derived, so it can
        drift from the layout `get_pdf_path` actually builds. Does a
        document's own path still start with it?

        Pinned against the whole path as well, because the prefix stops at the
        court and everything that tells one document from another comes after
        it. The published name is built from a scrape key, so `get_pdf_path` is
        applied to one once rather than re-applied to a path it has already
        built."""
        document = self.stored_document(sha256="a" * 64)

        built = make_pdf_path(document, document.make_filename())

        self.assertTrue(
            built.startswith(PUBLISHED_PREFIX),
            f"{built} does not start with {PUBLISHED_PREFIX}",
        )
        self.assertEqual(
            built,
            f"{RECAP_ROOT}/gov.uscourts.{NYCOA_COURT_ID}.{DOCKET_NUMBER}/"
            f"gov.uscourts.{NYCOA_COURT_ID}.{DOCKET_NUMBER}"
            f".{self.STORED_STEM}.{'a' * 16}.pdf",
            "A document is filed in its case's directory, under a name that "
            "names the case too.",
        )

    @merger_test(expected_query_count=0)
    def test_the_docket_number_is_named_once(self) -> None:
        """The scraper prefixes the docket number to the name it stores a file
        under, and the published name states it as a field of its own. Is it
        taken off the scraper's name rather than being said twice?"""
        document = self.stored_document(sha256="a" * 64)

        name = document.make_filename()

        self.assertEqual(
            name.count(DOCKET_NUMBER),
            1,
            f"The docket number is repeated in {name}",
        )
        self.assertNotIn(f"{DOCKET_NUMBER}_", name)

    @merger_test(expected_query_count=0)
    def test_a_name_the_scraper_did_not_prefix_is_kept_whole(self) -> None:
        """Only the docket number the bucket has already stated comes off the
        scraper's name. Does a file the scraper named some other way keep the
        name it was given, rather than losing a leading field to the strip?"""
        document = self.stored_document(
            filepath_local=f"{PRIVATE_PREFIX}nycourts_gov/webcast_1.pdf",
            sha256="a" * 64,
        )

        self.assertEqual(
            document.make_filename(),
            f"gov.uscourts.{NYCOA_COURT_ID}.{DOCKET_NUMBER}"
            f".webcast_1.{'a' * 16}.pdf",
        )

    @merger_test(expected_query_count=0)
    def test_a_document_with_no_hash_is_named_without_one(self) -> None:
        """A file the archive recorded no hash for still has to be publishable.
        Does the name simply end after the scraper's, rather than carrying a
        stray separator where the hash would have gone?"""
        document = self.stored_document()

        self.assertEqual(
            make_pdf_path(document, document.make_filename()),
            f"{RECAP_ROOT}/gov.uscourts.{NYCOA_COURT_ID}.{DOCKET_NUMBER}/"
            f"gov.uscourts.{NYCOA_COURT_ID}.{DOCKET_NUMBER}"
            f".{self.STORED_STEM}.pdf",
        )

    @merger_test(expected_query_count=0)
    def test_a_thumbnail_cannot_collide_with_its_document(self) -> None:
        """Thumbnails are named after the document they were made from, so
        they need a root of their own. Do the two land apart?"""
        document = self.stored_document(sha256="a" * 64)
        name = document.make_filename()

        self.assertNotEqual(
            document.get_pdf_path(name),
            document.get_pdf_path(name, thumbs=True),
        )
        self.assertTrue(
            document.get_pdf_path(name, thumbs=True).startswith(
                f"{RECAP_THUMBNAIL_ROOT}/"
            )
        )

    @merger_test(expected_query_count=16)
    def test_a_published_document_is_written_once(self) -> None:
        """The merge moves the file out of the private bucket before it stores
        anything, so a document that had to be published costs one write, not
        a write followed by a correction. Nothing reading the table ever sees
        `filepath_local` naming a key the public bucket does not hold."""
        file = NYCoAFileFactory.create(
            file_name="SmithvJones-app-Smith-brf.pdf",
            local_path=f"{PRIVATE_PREFIX}brf.pdf",
        )
        case = self.case_with_files(file)

        with CaptureQueriesContext(connection) as captured:
            with self.captureOnCommitCallbacks(execute=True):
                NYCoADocketMerger(case, params=None).merge()

        writes = [
            query["sql"]
            for query in captured.captured_queries
            if "search_nycoadocument" in query["sql"]
            and query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE"))
        ]
        self.assertEqual(len(writes), 1, f"Wrote the document twice: {writes}")
        self.assertIn(
            published_key(file),
            writes[0],
            "The one write is the published path.",
        )

    def test_publish_failure_stores_no_path_at_all(self) -> None:
        """A copy the bucket refuses leaves the document with no file rather
        than a path into a bucket `filepath_local` is never read against. The
        original is still in the private bucket, so the next merge of the case
        tries again."""
        self.publish_fails = True
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            )
        )

        with self.captureOnCommitCallbacks(execute=True):
            result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(
            result.success, "A file we could not move must not fail the case."
        )
        self.assertEqual(NYCoADocument.objects.get().filepath_local, "")
        self.assertEqual(
            self.discarded, [], "The only copy of the file has to survive."
        )

    @merger_test(expected_query_count=30)
    def test_remerge_withdraws_a_file_the_court_stopped_serving(self) -> None:
        """A file the Court seals stops being listed as available. Does
        CourtListener stop serving its copy?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                available=True,
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        NYCoADocketMerger(case, params=None).merge()
        served = NYCoADocument.objects.get()
        published = served.filepath_local.name
        served.page_count = 12
        served.save()

        sealed = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                available=False,
                local_path="",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        sealed.issues = case.issues
        with self.captureOnCommitCallbacks(execute=True):
            result = NYCoADocketMerger(sealed, params=None).merge()

        self.assertTrue(result.success)
        merged = NYCoADocument.objects.get()
        self.assertFalse(merged.available)
        self.assertEqual(
            merged.filepath_local,
            "",
            "The document is still recorded; only its file is gone.",
        )
        self.assertEqual(self.withdrawn, [published])
        self.assertEqual(
            (merged.sha256, merged.file_size, merged.page_count),
            ("", None, None),
            "Nothing is left to describe once the file is withdrawn.",
        )

    @merger_test(expected_query_count=31)
    def test_remerge_withdraws_a_file_the_scrape_no_longer_lists(self) -> None:
        """Court-PASS lists every file it has for a case, so a file that has
        dropped off the list is one CourtListener should stop serving. Does the
        row's deletion take its published copy with it?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-oldbrf.pdf",
                local_path=f"{PRIVATE_PREFIX}oldbrf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        NYCoADocketMerger(case, params=None).merge()
        published = NYCoADocument.objects.get().filepath_local.name

        replaced = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        replaced.issues = case.issues
        with self.captureOnCommitCallbacks(execute=True):
            result = NYCoADocketMerger(replaced, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(
            NYCoADocument.objects.get().file_name,
            "SmithvJones-app-Smith-brf.pdf",
        )
        self.assertEqual(self.withdrawn, [published])

    @merger_test(expected_query_count=33)
    def test_remerge_withdraws_the_files_of_a_dropped_filing(self) -> None:
        """A filing the scrape no longer lists is deleted outright, and its
        documents go with it in a cascade no document merger sees. Are their
        published files still withdrawn?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path=f"{PRIVATE_PREFIX}brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        NYCoADocketMerger(case, params=None).merge()
        published = NYCoADocument.objects.get().filepath_local.name

        withdrawn_filing = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-resp-Jones-brf.pdf",
                local_path=f"{PRIVATE_PREFIX}resp.pdf",
            ),
            docket_entry_id="e:respondent-brief:jones:1",
        )
        withdrawn_filing.issues = case.issues
        with self.captureOnCommitCallbacks(execute=True):
            result = NYCoADocketMerger(withdrawn_filing, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(NYCoADocketEntry.objects.count(), 1)
        self.assertEqual(self.withdrawn, [published])


class NYCoAPartyMergerTest(NYCoAMergerTestCase):
    """Tests for merging the parties and attorneys of a docket."""

    @merger_test(expected_query_count=19)
    def test_merge_creates_party_with_attorney(self) -> None:
        """Does merging a case create its party, party type, attorney, and the
        role linking them?"""
        attorney = NYCoAAttorneyFactory.create(
            name="Jane Roe",
            firm="Roe & Roe LLP",
            address="1 Main St, Albany, NY",
            phone="(518) 555-1212",
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[
                NYCoAPartyFactory.create(
                    name="Smith",
                    party_role_raw="Appellant",
                    representatives=[attorney],
                )
            ],
            entries=[],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        docket = self.merged_docket(result)
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
        self.assertEqual(
            role.role,
            Role.ATTORNEY_LEAD,
            "Court-PASS states no attorney role, so the first attorney it "
            "lists is the party's lead.",
        )

    @merger_test(expected_query_count=25)
    def test_merge_makes_the_first_attorney_listed_the_lead(self) -> None:
        """Court-PASS states no attorney's role. Is the first attorney it lists
        for a party stored as that party's lead, with the rest unknown?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[
                NYCoAPartyFactory.create(
                    name="Smith",
                    representatives=[
                        NYCoAAttorneyFactory.create(name="Jane Roe"),
                        NYCoAAttorneyFactory.create(name="John Doe"),
                        NYCoAAttorneyFactory.create(name="Ada Poe"),
                    ],
                )
            ],
            entries=[],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        roles = {
            role.attorney.name: role.role
            for role in Role.objects.filter(
                docket=self.merged_docket(result)
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

    @merger_test(expected_query_count=19)
    def test_merge_attorney_phone_with_extension(self) -> None:
        """Court-PASS writes a direct line as `(516) 222-6200 ext: 284`, which
        is longer than `Attorney.phone` allows. Is the number kept dialable
        without losing the extension entirely?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[
                NYCoAPartyFactory.create(
                    name="Smith",
                    representatives=[
                        NYCoAAttorneyFactory.create(
                            name="Jane Roe",
                            firm="Roe & Roe LLP",
                            address="1 Main St, Albany, NY",
                            phone="(516) 222-6200 ext: 284",
                        )
                    ],
                )
            ],
            entries=[],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        attorney = Role.objects.get(docket=self.merged_docket(result)).attorney
        self.assertEqual(attorney.phone, "(516) 222-6200")
        self.assertEqual(
            attorney.contact_raw,
            "Roe & Roe LLP\n1 Main St, Albany, NY\n(516) 222-6200 ext: 284",
            "The extension survives in the free-text contact field.",
        )

    @merger_test(expected_query_count=19)
    def test_merge_attorney_phone_with_stray_whitespace(self) -> None:
        """A scraped phone number carries whatever whitespace the page's text
        node did. Trimming it is not shortening it, so does the number stay out
        of the contact field?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[
                NYCoAPartyFactory.create(
                    name="Smith",
                    representatives=[
                        NYCoAAttorneyFactory.create(
                            name="Jane Roe",
                            firm="Roe & Roe LLP",
                            address="1 Main St, Albany, NY",
                            phone="  (518) 555-1212\n",
                        )
                    ],
                )
            ],
            entries=[],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        attorney = Role.objects.get(docket=self.merged_docket(result)).attorney
        self.assertEqual(attorney.phone, "(518) 555-1212")
        self.assertEqual(
            attorney.contact_raw,
            "Roe & Roe LLP\n1 Main St, Albany, NY",
            "Nothing was lost from the phone, so it is not repeated here.",
        )

    @merger_test(expected_query_count=19)
    def test_merge_keeps_role_court_pass_prints(self) -> None:
        """The cross-state party vocabulary has no amicus value. Is the role
        Court-PASS printed kept verbatim?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[
                NYCoAPartyFactory.create(
                    name="Concerned Citizens",
                    party_role_raw="Amicus Curiae",
                    representatives=[NYCoAAttorneyFactory.create()],
                )
            ],
            entries=[],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(PartyType.objects.get().name, "Amicus Curiae")

    @merger_test(expected_query_count=14)
    def test_merge_party_type_falls_back_to_vocabulary(self) -> None:
        """With no printed role, does the party type come from the normalized
        vocabulary?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[
                NYCoAPartyFactory.create(
                    name="Smith",
                    party_role_raw="",
                    party_type=ScrapedPartyType.APPELLANT,
                    representatives=[],
                )
            ],
            entries=[],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(PartyType.objects.get().name, "Appellant")

    @merger_test(expected_query_count=47)
    def test_remerge_one_name_under_two_roles(self) -> None:
        """In a family case the Court lists one person twice, as the child and
        as a party. Both are parties in their own right, and a name is all
        `PartyMerger` matches on, so re-merging must tell them apart by role
        rather than finding two and giving up on the docket."""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[
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
            ],
            entries=[],
        )

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

    @merger_test(expected_query_count=49)
    def test_refusing_a_party_costs_only_that_party(self) -> None:
        """A shared name the role cannot separate is one the party merger
        refuses. That refusal is reported in the docket's own result, so does
        the rest of the case still merge and stay merged -- the docket merger
        being atomic notwithstanding?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            case_name="Matter of A. R.",
            parties=[
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
            ],
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
        docket = self.merged_docket(first)
        docket.refresh_from_db()
        self.assertEqual(
            docket.case_name,
            "Matter of A. R. (No. 2)",
            "The docket's own fields merged and were committed.",
        )
        self.assertEqual(
            docket.nycoa_metadata.decision_date, date(2025, 6, 12)
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

    @merger_test(expected_query_count=32)
    def test_remerge_party_whose_role_changed(self) -> None:
        """A respondent becomes a respondent-appellant when the other side
        cross-appeals. Is that the same party under a new role, rather than a
        second row?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            parties=[
                NYCoAPartyFactory.create(
                    name="Smith", party_role_raw="Respondent"
                )
            ],
            entries=[],
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
