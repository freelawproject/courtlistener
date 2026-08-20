"""Tests for the New York Court of Appeals (Court-PASS) mergers."""

from datetime import date

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
from cl.corpus_importer.state.tests import merger_test
from cl.corpus_importer.state.utils import MergeResult
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


class NYCoAMergerTestCase(TestCase):
    """Shared setup for the NYCoA merger tests."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.ny = CourtFactory.create(id="ny")

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

    @merger_test(expected_query_count=8)
    def test_merge_updates_existing_docket(self) -> None:
        """Does a docket that already exists get updated rather than
        duplicated?"""
        docket = self.existing_docket()
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            case_name="Matter of Smith",
            argument_date=date(2025, 2, 11),
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

    @merger_test(expected_query_count=8)
    def test_merge_keeps_existing_date_filed(self) -> None:
        """Court-PASS has no filing date of its own. Does a scrape without one
        leave a date another source established alone?"""
        docket = self.existing_docket()
        docket.date_filed = date(2020, 5, 5)
        docket.save()
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, date_filed=None
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        docket.refresh_from_db()
        self.assertEqual(docket.date_filed, date(2020, 5, 5))

    @merger_test(expected_query_count=17)
    def test_merge_date_last_filing_uses_latest_filing(self) -> None:
        """Is date_last_filing the most recent filing date on the docket?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
            date_filed=date(2024, 3, 1),
            entries=[
                NYCoAFilingFactory.create(date_filed=date(2024, 6, 1)),
                NYCoAFilingFactory.create(date_filed=date(2024, 9, 15)),
                # Reconstructed filings carry no date and must not win.
                NYCoAFilingFactory.create(date_filed=None, raw_filing_type=""),
            ],
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

    @merger_test(expected_query_count=4)
    def test_merge_updates_existing_metadata(self) -> None:
        """Does a case whose metadata already exists update it in place?"""
        docket = self.existing_docket()
        metadata = NYCoADocketMetadata.objects.create(
            docket=docket,
            official_citation="",
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
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

    @merger_test(expected_query_count=16)
    def test_remerge_issues_sharing_a_category_is_idempotent(self) -> None:
        """Re-scraping a case whose issues share a category must match both
        rows rather than replacing one with the other."""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
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

    @merger_test(expected_query_count=14)
    def test_remerge_reworded_issue_updates_it_in_place(self) -> None:
        """The Court rewords a description it has already published. Does the
        issue keep its row, rather than the old one being replaced?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
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

    @merger_test(expected_query_count=18)
    def test_remerge_rewords_an_issue_sharing_a_category(self) -> None:
        """Rewording one of two issues that share a category is the one case
        the merger cannot resolve: with the description gone, nothing says which
        of the two the Court restated. Is it replaced rather than matched to
        either row, leaving the issue the Court did not touch alone?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
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

    @merger_test(expected_query_count=16)
    def test_remerge_drops_an_issue_sharing_a_category(self) -> None:
        """A case that stated two issues under one category now states one of
        them. Is the other pruned, and does the survivor keep its row?"""
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER,
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
            issues=[NYCoAIssueFactory.create(category_raw="Crimes")],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        issue = self.merged_docket(result).nycoa_metadata.issues.get()
        self.assertEqual(issue.category, IssueCategory.CRIMES.code)
        self.assertEqual(issue.subcategory, UNKNOWN)
        self.assertEqual(issue.category_raw, "Crimes")

    @merger_test(expected_query_count=8)
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

    @merger_test(expected_query_count=4)
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
        case = NYCoACaseFactory.create(docket_number=DOCKET_NUMBER, issues=[])

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
            filing_type_recognized=True,
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing]
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
        self.assertTrue(merged.filing_type_recognized)

    @merger_test(expected_query_count=13)
    def test_merge_unrecognized_filing_type(self) -> None:
        """Court-PASS listing a filing type this vocabulary doesn't cover is
        the drift signal. Is it flagged while the raw value survives?"""
        filing = NYCoAFilingFactory.create(
            raw_filing_type="Appellant Sur-Reply Brief",
            entry_role=FilingRole.APPELLANT,
            entry_doctype=FilingDocType.BRIEF,
            filing_type_recognized=False,
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        merged = self.merged_docket(result).nycoa_docket_entries.get()
        self.assertEqual(merged.filing_type, UNASSIGNED)
        self.assertEqual(merged.filing_type_raw, "Appellant Sur-Reply Brief")
        self.assertEqual(merged.filing_role, FilingRole.APPELLANT.code)
        self.assertFalse(merged.filing_type_recognized)

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
            filing_type_recognized=True,
            party="",
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing]
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

    @merger_test(expected_query_count=22)
    def test_remerge_updates_filing_fields(self) -> None:
        """Does a filing matched by its entry ID pick up new values?"""
        filing = NYCoAFilingFactory.create(
            docket_entry_id="e:appellant-brief:smith:1",
            date_filed=None,
            filing_type_recognized=False,
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing]
        )
        NYCoADocketMerger(case, params=None).merge()

        updated = filing.model_copy(
            update={
                "date_filed": date(2024, 6, 1),
                "filing_type_recognized": True,
            }
        )
        result = NYCoADocketMerger(
            # The same issues, because this is the same case scraped again and
            # an issue is identified by what the Court said about it.
            NYCoACaseFactory.create(
                docket_number=DOCKET_NUMBER,
                entries=[updated],
                issues=case.issues,
            ),
            params=None,
        ).merge()

        self.assertTrue(result.success)
        self.assertEqual(NYCoADocketEntry.objects.count(), 1)
        merged = NYCoADocketEntry.objects.get()
        self.assertEqual(merged.date_filed, date(2024, 6, 1))
        self.assertTrue(merged.filing_type_recognized)

    @merger_test(expected_query_count=14)
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
            docket_entry_id="e:appellant-brief:smith:1"
        )
        case = NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing]
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
            entries=[NYCoAFilingFactory.create(party="Smith")],
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
                    party="A. R.", entry_role=FilingRole.RESPONDENT
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
            entries=[NYCoAFilingFactory.create(party="Board of Elections")],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        merged = self.merged_docket(result).nycoa_docket_entries.get()
        self.assertIsNone(merged.party_id)
        # The name the FILINGS table printed survives the unresolved FK.
        self.assertEqual(merged.party_name, "Board of Elections")

    @merger_test(expected_query_count=26)
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
                    docket_entry_id="e:appellant-brief:smith:1", party="Smith"
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
                    docket_entry_id="e:appellant-brief:smith:1", party=""
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
    def case_with_files(*files, **filing_kwargs) -> "NYCoACaseFactory":
        filing = NYCoAFilingFactory.create(
            attachments=list(files), **filing_kwargs
        )
        return NYCoACaseFactory.create(
            docket_number=DOCKET_NUMBER, entries=[filing]
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
            local_path="us/state/ny/ny/scraped/smith-rec-vol3.pdf",
        )
        case = self.case_with_files(file)

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
        # The scraper wrote the file into the bucket this field is stored in,
        # so the merge points at it rather than fetching or copying anything.
        self.assertEqual(
            merged.filepath_local,
            "us/state/ny/ny/scraped/smith-rec-vol3.pdf",
        )

    @merger_test(expected_query_count=16)
    def test_merge_oral_argument_recording(self) -> None:
        """Oral argument recordings are playlists, not PDFs. Does the content
        type survive the merge so the file pass can route them?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-Webcast.asx",
                content_type="video/x-ms-asf",
                doc_role=None,
                doc_party="",
                doc_type=FilingDocType.ORAL_ARGUMENT_WEBCAST,
                local_path="us/state/ny/ny/scraped/smithvjones-webcast.asx",
            ),
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
            "us/state/ny/ny/scraped/smithvjones-webcast.asx",
            "A playlist is stored like any other file; the extraction sweep "
            "leaves it alone because it is not a PDF.",
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
        """Whoever uploads a file puts it where `get_pdf_path` says, so no two
        files on one filing may name the same path.

        Both of the ways Court-PASS makes that hard are represented: a case name
        with a dot in it, which a filename's stem would cut the volume off of,
        and two names differing only in punctuation, which slugify flattens
        together."""
        names = [
            "IKB v. Wells Fargo-app-Wells Fargo-rec-Volume1",
            "IKB v. Wells Fargo-app-Wells Fargo-rec-Volume2",
            "CortlandtvBonderman-app-TPG APAX-appdx-vol1",
            "CortlandtvBonderman-app-TPG, APAX-appdx-vol1",
        ]
        case = self.case_with_files(
            *[NYCoAFileFactory.create(file_name=name) for name in names]
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        documents = list(
            NYCoADocument.objects.select_related("docket_entry__docket")
        )
        self.assertEqual(len(documents), len(names))
        paths = {
            document.get_pdf_path(f"{document.make_filename()}.pdf")
            for document in documents
        }
        self.assertEqual(
            len(paths), len(names), f"Two documents share a path: {paths}"
        )
        self.assertTrue(
            any(path.endswith("-rec-volume2.pdf") for path in paths),
            f"The volume has to survive into the path: {paths}",
        )

    @merger_test(expected_query_count=25)
    def test_remerge_documents_is_idempotent(self) -> None:
        """Does merging the same case twice avoid duplicating documents?"""
        case = self.case_with_files(NYCoAFileFactory.create())

        first = NYCoADocketMerger(case, params=None).merge()
        second = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertNotIn("NYCoADocument", second.creates)
        self.assertEqual(NYCoADocument.objects.count(), 1)

    @merger_test(expected_query_count=16)
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

    @merger_test(expected_query_count=27)
    def test_remerge_keeps_stored_path_when_scrape_reports_none(self) -> None:
        """Does a later scrape that did not fetch the file leave the path an
        earlier one recorded, rather than blanking it?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path="us/state/ny/ny/scraped/brf.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        NYCoADocketMerger(case, params=None).merge()

        second = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf", local_path=""
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        second.issues = case.issues
        result = NYCoADocketMerger(second, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(
            NYCoADocument.objects.get().filepath_local,
            "us/state/ny/ny/scraped/brf.pdf",
            "The file is still where the scraper left it last time.",
        )

    @merger_test(expected_query_count=28)
    def test_remerge_at_a_new_path_sends_the_file_back_for_extraction(
        self,
    ) -> None:
        """The scraper fetching a file again means what was extracted came from
        a copy that has been replaced. Does the document go back in front of the
        extraction sweep, without the scraper's own file being deleted?"""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path="us/state/ny/ny/scraped/first.pdf",
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
                local_path="us/state/ny/ny/scraped/second.pdf",
            ),
            docket_entry_id="e:appellant-brief:smith:1",
        )
        second.issues = case.issues
        result = NYCoADocketMerger(second, params=None).merge()

        self.assertTrue(result.success)
        merged = NYCoADocument.objects.get()
        self.assertEqual(
            merged.filepath_local, "us/state/ny/ny/scraped/second.pdf"
        )
        self.assertIsNone(
            merged.ocr_status,
            "A replaced file has to be extracted again.",
        )

    @merger_test(expected_query_count=27)
    def test_remerge_at_the_same_path_leaves_extraction_alone(self) -> None:
        """Re-scraping a file that has not moved must not throw away text
        already extracted from it."""
        case = self.case_with_files(
            NYCoAFileFactory.create(
                file_name="SmithvJones-app-Smith-brf.pdf",
                local_path="us/state/ny/ny/scraped/brf.pdf",
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
                local_path="us/state/ny/ny/scraped/brf.pdf",
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
            Role.UNKNOWN,
            "Court-PASS states no attorney role, and the role is not nullable.",
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
                    name="Smith", party_role_raw="", representatives=[]
                )
            ],
        )

        result = NYCoADocketMerger(case, params=None).merge()

        self.assertTrue(result.success)
        self.assertEqual(PartyType.objects.get().name, "Appellant")

    @merger_test(expected_query_count=46)
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

    @merger_test(expected_query_count=31)
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
