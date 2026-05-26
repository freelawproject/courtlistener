"""SCOTUS docket-merger driver tests, targeting real PostgreSQL.

Driver = :mod:`cl.scrapers.mergers.federal.scotus.driver`; schemas =
:mod:`cl.scrapers.mergers.federal.scotus.scotus`. These tests run
against the production CL Django models, not the framework's
in-memory sqlite test models.

Mostly a port of ``cl.search.tests.test_scotus_content.ScotusDocketMergeTest``
with the same assertions wired up against the new driver's
``MergeOutcome`` return type. Skipped from the legacy port:

- Per-document API tests (``merge_scotus_document`` no longer exists
  as a standalone entry point — its behavior is exercised here via
  the full driver call).
- Standalone QP-PDF download tests (those test the downstream Celery
  task, not the merger).
- ``find_docket_object`` order-independence test (upstream of the
  driver — covered by the SCOTUS docket-number normalization tests
  in their original location).
"""

import datetime
from unittest import mock

from django.core.files.base import ContentFile

from cl.people_db.models import (
    Attorney,
    AttorneyOrganization,
    AttorneyOrganizationAssociation,
    Party,
    PartyType,
    Role,
)
from cl.scrapers.mergers.federal.scotus.driver import merge_scotus_docket
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    SCOTUSAttachmentDataFactory,
    SCOTUSAttorneyDataFactory,
    ScotusDocketDataFactory,
    SCOTUSDocketEntryDataFactory,
    SCOTUSPartyDataFactory,
)
from cl.search.models import (
    Docket,
    SCOTUSDocketEntry,
    ScotusDocketMetadata,
    SCOTUSDocument,
)
from cl.tests.cases import TestCase


_FOLLOWUP_DOWNLOAD = "scotus-document-download-and-extract"
_FOLLOWUP_QP = "scotus-qp-download"


class ScotusDriverTest(TestCase):
    """Driver tests against the real PG database. SCOTUS court and
    one lower-court ``Court`` row are created in ``setUpTestData``."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(id="scotus", jurisdiction="F")
        cls.lower_court = CourtFactory(
            id="ca2",
            full_name="United States Court of Appeals for the Second Circuit",
            jurisdiction="A",
        )

    # ---------------------------------------------------------------------
    # End-to-end creation
    # ---------------------------------------------------------------------

    def test_create_docket_with_metadata_oci_parties_entries_documents(
        self,
    ) -> None:
        """Comprehensive port of
        ``test_merge_scotus_docket_creates_docket_and_metadata``: a
        single merge of a realistic SCOTUS docket payload creates the
        full Docket tree — entries, documents, metadata, OCI, parties,
        attorneys, orgs, associations — and a re-merge is idempotent."""
        att_1 = SCOTUSAttachmentDataFactory(
            description="Main 1", document_number=23453
        )
        att_2 = SCOTUSAttachmentDataFactory(
            description="Attachment 2", document_number=23453
        )
        de_1 = SCOTUSDocketEntryDataFactory(
            description="lorem ipsum 1",
            date_filed=datetime.date(2015, 8, 19),
            document_number=23453,
            attachments=[att_1, att_2],
        )
        de_2 = SCOTUSDocketEntryDataFactory(
            description="lorem ipsum 2",
            date_filed=datetime.date(2015, 8, 21),
            document_number=23455,
            attachments=[
                SCOTUSAttachmentDataFactory(
                    description="Main 1.1", document_number=23455
                ),
                SCOTUSAttachmentDataFactory(
                    description="Attachment 2.1", document_number=23455
                ),
            ],
        )
        de_3 = SCOTUSDocketEntryDataFactory(
            description="Low after process.",
            date_filed=datetime.date(2015, 8, 22),
            document_number=None,
            attachments=[],
        )
        de_4 = SCOTUSDocketEntryDataFactory(
            description="Key street surface",
            date_filed=datetime.date(2015, 8, 22),
            document_number=None,
            attachments=[],
        )
        atty_1 = SCOTUSAttorneyDataFactory(
            name="Paul D. Clement",
            address="706 Duke Street",
            city="Alexandria",
            state="VA",
            zip="22314",
            phone="(202) 742-8900",
            email="PAUL.CLEMENT@CLEMENTMURPHY.COM",
            is_counsel_of_record=True,
            title="Clement & Murphy, LLC",
        )
        atty_2 = SCOTUSAttorneyDataFactory(
            name="Noel John Francisco",
            address="51 Louisiana Avenue, NW",
            city="Washington",
            state="DC",
            zip="20001",
            phone="(202) 879-3939",
            email="NJFRANCISCO@JONESDAY.COM",
            is_counsel_of_record=True,
            title="Law Firm Test LLC",
        )
        atty_3 = SCOTUSAttorneyDataFactory(
            name="Eric Nelson",
            address="54 Florence Street",
            city="Staten Island",
            state="NY",
            zip="10308",
            phone="(718) 356-0566",
            email=None,
            is_counsel_of_record=False,
            title=None,
        )
        party_1 = SCOTUSPartyDataFactory(
            name="Encino Motorcars, LLC",
            type="Petitioner",
            attorneys=[atty_1],
        )
        party_2 = SCOTUSPartyDataFactory(
            name="United States",
            type="Respondent",
            attorneys=[atty_2, atty_3],
        )
        data = ScotusDocketDataFactory(
            docket_number="23-1434",
            capital_case=False,
            lower_court="United States Court of Appeals for the Second Circuit",
            lower_court_case_numbers=["22-16375", "22-16622"],
            lower_court_case_numbers_raw="Docket Num. 22-16375, Docket Num. 22-16622",
            docket_entries=[de_1, de_2, de_3, de_4],
            parties=[party_1, party_2],
        )

        outcome = merge_scotus_docket(data, download_file=False)
        assert outcome.root is not None
        docket = outcome.root
        docket.refresh_from_db()

        # Docket fields
        self.assertEqual(docket.court_id, self.court.pk)
        self.assertTrue(docket.source & Docket.SCRAPER)
        self.assertEqual(docket.docket_number, data["docket_number"])
        self.assertEqual(docket.case_name, data["case_name"])
        self.assertEqual(docket.date_filed, data["date_filed"])
        self.assertEqual(docket.appeal_from_str, data["lower_court"])
        self.assertEqual(docket.appeal_from_id, self.lower_court.pk)

        # Docket entries
        des = SCOTUSDocketEntry.objects.filter(docket=docket)
        self.assertEqual(des.count(), 4, "Wrong number of Docket entries.")

        for de in (de_1, de_2, de_3, de_4):
            de_db = SCOTUSDocketEntry.objects.filter(
                docket=docket, description=de["description"]
            ).first()
            assert de_db is not None
            self.assertEqual(de["document_number"], de_db.entry_number)

        # Documents
        rds = SCOTUSDocument.objects.filter(docket_entry__docket=docket)
        self.assertEqual(rds.count(), 4, "Wrong number of Documents.")
        rds_pks = set(rds.values_list("pk", flat=True))
        rd_att_1 = SCOTUSDocument.objects.get(
            docket_entry__docket=docket, description="Main 1"
        )
        self.assertEqual(rd_att_1.url, att_1["document_url"])
        rd_att_2 = SCOTUSDocument.objects.get(
            docket_entry__docket=docket, description="Attachment 2"
        )
        self.assertEqual(rd_att_2.url, att_2["document_url"])

        # ScotusDocketMetadata fields
        metadata = docket.scotus_metadata
        self.assertFalse(metadata.capital_case)
        self.assertEqual(
            metadata.date_discretionary_court_decision,
            data["discretionary_court_decision"],
        )
        self.assertEqual(metadata.linked_with, data["links"])
        self.assertEqual(
            metadata.questions_presented_url, data["questions_presented"]
        )

        # OriginatingCourtInformation fields
        oci = docket.originating_court_information
        self.assertEqual(oci.docket_number, "22-16375, 22-16622")
        self.assertEqual(
            oci.docket_number_raw, data["lower_court_case_numbers_raw"]
        )
        self.assertEqual(
            oci.date_judgment, data["lower_court_decision_date"]
        )
        self.assertEqual(
            oci.date_rehearing_denied,
            data["lower_court_rehearing_denied_date"],
        )

        # Parties + PartyTypes
        self.assertEqual(
            Party.objects.filter(party_types__docket=docket).count(), 2
        )
        party_1_db = Party.objects.get(
            name="Encino Motorcars, LLC", party_types__docket=docket
        )
        self.assertEqual(
            PartyType.objects.get(docket=docket, party=party_1_db).name,
            "Petitioner",
        )
        party_2_db = Party.objects.get(
            name="United States", party_types__docket=docket
        )
        self.assertEqual(
            PartyType.objects.get(docket=docket, party=party_2_db).name,
            "Respondent",
        )

        # Attorneys + Roles
        attorneys = Attorney.objects.filter(roles__docket=docket).distinct()
        self.assertEqual(attorneys.count(), 3)

        atty_1_db = Attorney.objects.get(
            name="Paul D. Clement", roles__docket=docket
        )
        self.assertEqual(atty_1_db.phone, "(202) 742-8900")
        self.assertEqual(atty_1_db.email, "PAUL.CLEMENT@CLEMENTMURPHY.COM")
        self.assertIn("706 Duke Street", atty_1_db.contact_raw)
        self.assertEqual(
            Role.objects.get(
                attorney=atty_1_db, docket=docket, party=party_1_db
            ).role,
            Role.ATTORNEY_LEAD,
        )

        atty_2_db = Attorney.objects.get(
            name="Noel John Francisco", roles__docket=docket
        )
        self.assertEqual(atty_2_db.email, "NJFRANCISCO@JONESDAY.COM")
        self.assertEqual(
            Role.objects.get(
                attorney=atty_2_db, docket=docket, party=party_2_db
            ).role,
            Role.ATTORNEY_LEAD,
        )

        atty_3_db = Attorney.objects.get(
            name="Eric Nelson", roles__docket=docket
        )
        self.assertEqual(atty_3_db.email, "")
        self.assertEqual(
            Role.objects.get(
                attorney=atty_3_db, docket=docket, party=party_2_db
            ).role,
            Role.UNKNOWN,
        )

        # AttorneyOrganization rows — 3 distinct orgs (the third
        # falls back to the attorney's name when title=None).
        self.assertEqual(AttorneyOrganization.objects.count(), 3)
        org_1 = AttorneyOrganization.objects.get(name="Clement & Murphy, LLC")
        self.assertEqual(org_1.city, "Alexandria")
        self.assertEqual(org_1.state, "VA")
        self.assertEqual(org_1.zip_code, "22314")

        org_2 = AttorneyOrganization.objects.get(name="Law Firm Test LLC")
        self.assertEqual(org_2.city, "Washington")
        self.assertEqual(org_2.state, "DC")
        self.assertEqual(org_2.zip_code, "20001")

        org_3 = AttorneyOrganization.objects.get(name="Eric Nelson")
        self.assertEqual(org_3.city, "Staten Island")

        # AttorneyOrganizationAssociation rows
        self.assertTrue(
            AttorneyOrganizationAssociation.objects.filter(
                attorney=atty_1_db,
                attorney_organization=org_1,
                docket=docket,
            ).exists()
        )
        self.assertTrue(
            AttorneyOrganizationAssociation.objects.filter(
                attorney=atty_2_db,
                attorney_organization=org_2,
                docket=docket,
            ).exists()
        )
        self.assertTrue(
            AttorneyOrganizationAssociation.objects.filter(
                attorney=atty_3_db,
                attorney_organization=org_3,
                docket=docket,
            ).exists()
        )

        # Re-merge: idempotent — no duplicates.
        outcome_2 = merge_scotus_docket(data, download_file=False)
        assert outcome_2.root is not None
        self.assertEqual(outcome_2.root.pk, docket.pk)

        self.assertEqual(
            SCOTUSDocketEntry.objects.filter(docket=docket).count(), 4
        )
        rds_after = SCOTUSDocument.objects.filter(docket_entry__docket=docket)
        self.assertEqual(rds_after.count(), 4)
        self.assertEqual(set(rds_after.values_list("pk", flat=True)), rds_pks)

        self.assertEqual(
            Party.objects.filter(party_types__docket=docket).count(), 2
        )
        self.assertEqual(
            Attorney.objects.filter(roles__docket=docket).distinct().count(),
            3,
        )
        self.assertEqual(AttorneyOrganization.objects.count(), 3)

    # ---------------------------------------------------------------------
    # Update path
    # ---------------------------------------------------------------------

    def test_re_merge_updates_existing_docket(self) -> None:
        """Ported from ``test_merge_scotus_docket_updates_existing_docket``.
        Re-merging with new scalar values updates the docket + metadata;
        ``capital_case`` flips false→true."""
        first = ScotusDocketDataFactory(
            docket_number="23A1434",
            case_name="Old Name",
            capital_case=False,
            lower_court=self.lower_court.full_name,
            docket_entries=[],
            parties=[],
        )
        outcome_1 = merge_scotus_docket(first, download_file=False)
        assert outcome_1.root is not None
        docket = outcome_1.root
        self.assertEqual(Docket.objects.filter(court=self.court).count(), 1)
        self.assertEqual(ScotusDocketMetadata.objects.count(), 1)
        self.assertTrue(docket.source & Docket.SCRAPER)

        updated = ScotusDocketDataFactory(
            docket_number="23A1434",
            case_name="New SCOTUS Case Name",
            capital_case=True,
            linked_with="23-6433",
            lower_court=self.lower_court.full_name,
            lower_court_case_numbers=["23-6433"],
            docket_entries=[],
            parties=[],
        )
        outcome_2 = merge_scotus_docket(updated, download_file=False)
        assert outcome_2.root is not None
        self.assertEqual(outcome_2.root.pk, docket.pk)
        self.assertEqual(Docket.objects.filter(court=self.court).count(), 1)
        self.assertEqual(ScotusDocketMetadata.objects.count(), 1)

        docket.refresh_from_db()
        self.assertTrue(docket.source & Docket.SCRAPER)
        self.assertEqual(docket.case_name, "New SCOTUS Case Name")
        self.assertEqual(docket.date_filed, updated["date_filed"])

        metadata = docket.scotus_metadata
        self.assertTrue(metadata.capital_case)
        self.assertEqual(
            metadata.date_discretionary_court_decision,
            updated["discretionary_court_decision"],
        )
        self.assertEqual(metadata.linked_with, updated["links"])
        self.assertEqual(
            metadata.questions_presented_url, updated["questions_presented"]
        )

    # ---------------------------------------------------------------------
    # Source-bit OR compounding
    # ---------------------------------------------------------------------

    def test_source_compounds_with_harvard(self) -> None:
        """Ported from ``test_merge_scotus_docket_source_compounds_existing``."""
        existing = DocketFactory(
            court=self.court,
            docket_number="24-200",
            source=Docket.HARVARD,
        )
        data = ScotusDocketDataFactory(
            docket_number="24-200", docket_entries=[], parties=[]
        )
        outcome = merge_scotus_docket(data, download_file=False)
        assert outcome.root is not None
        self.assertEqual(outcome.root.pk, existing.pk)
        outcome.root.refresh_from_db()
        self.assertEqual(outcome.root.source, Docket.SCRAPER_AND_HARVARD)

    def test_source_compounds_with_recap(self) -> None:
        """Ported from ``test_merge_scotus_docket_source_compounds_recap``."""
        existing = DocketFactory(
            court=self.court,
            docket_number="24-400",
            source=Docket.RECAP,
        )
        data = ScotusDocketDataFactory(
            docket_number="24-400", docket_entries=[], parties=[]
        )
        outcome = merge_scotus_docket(data, download_file=False)
        assert outcome.root is not None
        self.assertEqual(outcome.root.pk, existing.pk)
        outcome.root.refresh_from_db()
        self.assertEqual(outcome.root.source, Docket.RECAP_AND_SCRAPER)

    # ---------------------------------------------------------------------
    # Validation
    # ---------------------------------------------------------------------

    def test_missing_docket_number_raises(self) -> None:
        """Ported from ``test_merge_scotus_docket_missing_docket_number``."""
        data = ScotusDocketDataFactory(
            case_name="X", docket_number=None, docket_entries=[], parties=[]
        )
        with self.assertRaisesMessage(
            ValueError, "Docket number can't be missing in SCOTUS dockets."
        ):
            merge_scotus_docket(data, download_file=False)

    # ---------------------------------------------------------------------
    # QP URL resolution + follow-up gating
    # ---------------------------------------------------------------------

    def test_resolves_relative_qp_url(self) -> None:
        """Ported from ``test_merge_scotus_docket_resolves_relative_qp_url``.
        Relative QP URLs (``../qp/14-00556qp.pdf`` etc.) are resolved
        against the SCOTUS base URL before being stored."""
        data = ScotusDocketDataFactory(
            questions_presented="../qp/14-00556qp.pdf",
            docket_entries=[],
            parties=[],
        )
        outcome = merge_scotus_docket(data, download_file=False)
        assert outcome.root is not None
        metadata = ScotusDocketMetadata.objects.get(docket=outcome.root)
        self.assertEqual(
            metadata.questions_presented_url,
            "https://www.supremecourt.gov/qp/14-00556qp.pdf",
        )

    def test_qp_followup_fires_for_new_docket_with_url(self) -> None:
        """A brand-new docket with a QP URL queues the
        ``scotus-qp-download`` follow-up (visible in
        ``outcome.follow_ups``) when ``download_file=True``."""
        data = ScotusDocketDataFactory(
            questions_presented="https://www.supremecourt.gov/x.pdf",
            docket_entries=[],
            parties=[],
        )
        outcome = merge_scotus_docket(data, download_file=True)
        qp_followups = [
            fu
            for fu in outcome.follow_ups
            if getattr(fu, "name", None) == _FOLLOWUP_QP
        ]
        self.assertEqual(len(qp_followups), 1)

    def test_qp_followup_skipped_when_file_already_present(self) -> None:
        """If the existing ``ScotusDocketMetadata`` already has a
        ``questions_presented_file``, a re-merge with the same URL
        does *not* re-queue the QP download."""
        docket = DocketFactory.create(
            court=self.court,
            docket_number="22-300",
        )
        scotus_meta = ScotusDocketMetadata.objects.create(
            docket=docket,
            questions_presented_url=(
                "https://www.supremecourt.gov/qp/22-00300qp.pdf"
            ),
        )
        scotus_meta.questions_presented_file.save(
            "existing.pdf",
            ContentFile(b"existing content"),
            save=True,
        )

        data = ScotusDocketDataFactory(
            docket_number="22-300",
            questions_presented=(
                "https://www.supremecourt.gov/qp/22-00300qp.pdf"
            ),
            docket_entries=[],
            parties=[],
        )
        outcome = merge_scotus_docket(data, download_file=True)
        qp_followups = [
            fu
            for fu in outcome.follow_ups
            if getattr(fu, "name", None) == _FOLLOWUP_QP
        ]
        self.assertEqual(qp_followups, [])

    # ---------------------------------------------------------------------
    # appeal_from fallback paths
    # ---------------------------------------------------------------------

    @mock.patch("cl.lib.courts.logger")
    def test_appeal_from_when_lower_court_not_found(self, mock_logger) -> None:
        """Ported from ``test_logs_error_when_lower_court_not_found``.
        Unknown lower-court name leaves ``appeal_from`` NULL but
        records the string."""
        data = ScotusDocketDataFactory(
            docket_number="23-1435",
            lower_court="Imaginary Court of The Dragons",
            lower_court_case_numbers=["10-1000"],
            docket_entries=[],
            parties=[],
        )
        outcome = merge_scotus_docket(data, download_file=False)
        assert outcome.root is not None
        outcome.root.refresh_from_db()

        self.assertEqual(outcome.root.appeal_from_str, data["lower_court"])
        self.assertIsNone(outcome.root.appeal_from)
        mock_logger.error.assert_called_with(
            "Could not find court IDs from name '%s'.",
            "Imaginary Court of The Dragons",
        )

    @mock.patch("cl.lib.courts.find_court")
    @mock.patch("cl.lib.courts.logger")
    def test_appeal_from_when_lookup_ambiguous(
        self,
        mock_logger,
        mock_find_court,
    ) -> None:
        """Ported from ``test_logs_error_when_lower_court_ambiguous``."""
        mock_find_court.return_value = ["mab", "mad"]
        data = ScotusDocketDataFactory(
            docket_number="23-1436",
            lower_court="District of Massachusetts",
            lower_court_case_numbers=["10-2000"],
            docket_entries=[],
            parties=[],
        )
        outcome = merge_scotus_docket(data, download_file=False)
        assert outcome.root is not None
        outcome.root.refresh_from_db()

        self.assertEqual(outcome.root.appeal_from_str, data["lower_court"])
        self.assertIsNone(outcome.root.appeal_from)
        mock_logger.error.assert_called_with(
            "Ambiguous court name '%s' in courts-db: %s",
            "District of Massachusetts",
            ["mab", "mad"],
        )

    @mock.patch("cl.lib.courts.find_court")
    @mock.patch("cl.lib.courts.logger")
    def test_appeal_from_when_resolved_id_missing_in_db(
        self,
        mock_logger,
        mock_find_court,
    ) -> None:
        """Ported from ``test_logs_error_when_lower_court_id_missing_in_db``."""
        mock_find_court.return_value = ["cadc123"]
        data = ScotusDocketDataFactory(
            docket_number="23-1437",
            lower_court="Non-existent Court",
            lower_court_case_numbers=["10-3000"],
            docket_entries=[],
            parties=[],
        )
        outcome = merge_scotus_docket(data, download_file=False)
        assert outcome.root is not None
        outcome.root.refresh_from_db()

        self.assertEqual(outcome.root.appeal_from_str, data["lower_court"])
        self.assertIsNone(outcome.root.appeal_from)
        mock_logger.error.assert_called_with(
            "Court object does not exist in DB for id '%s' (name: '%s').",
            "cadc123",
            "Non-existent Court",
        )

    # ---------------------------------------------------------------------
    # Document follow-up filtering
    # ---------------------------------------------------------------------

    def test_download_file_false_filters_document_followups(self) -> None:
        """Ported from
        ``test_merge_scotus_document_skips_download_when_flag_is_false``.
        With ``download_file=False``, the driver strips
        ``scotus-document-download-and-extract`` follow-ups out of the
        returned outcome so the caller never dispatches the chain."""
        att = SCOTUSAttachmentDataFactory(
            description="Main 1", document_number=23453
        )
        de = SCOTUSDocketEntryDataFactory(
            description="lorem ipsum 1",
            date_filed=datetime.date(2015, 8, 19),
            document_number=23453,
            attachments=[att],
        )
        data = ScotusDocketDataFactory(
            docket_number="23-1438",
            lower_court="United States Court of Appeals for the Second Circuit",
            docket_entries=[de],
            parties=[],
            questions_presented=None,
        )

        outcome = merge_scotus_docket(data, download_file=False)
        download_followups = [
            fu
            for fu in outcome.follow_ups
            if getattr(fu, "name", None) == _FOLLOWUP_DOWNLOAD
        ]
        self.assertEqual(download_followups, [])

        # Entry + document rows still get created — the framework runs
        # the merge; only the post-commit downloads are skipped.
        docket = Docket.objects.get(docket_number="23-1438")
        self.assertEqual(
            SCOTUSDocketEntry.objects.filter(docket=docket).count(), 1
        )
        self.assertEqual(
            SCOTUSDocument.objects.filter(
                docket_entry__docket=docket
            ).count(),
            1,
        )

    def test_download_file_true_keeps_document_followups(self) -> None:
        """The positive companion: default ``download_file=True``
        leaves document-download follow-ups intact so the caller can
        dispatch them post-commit."""
        att = SCOTUSAttachmentDataFactory(
            description="Main 1", document_number=23459
        )
        de = SCOTUSDocketEntryDataFactory(
            description="lorem ipsum 1",
            date_filed=datetime.date(2025, 1, 1),
            document_number=23459,
            attachments=[att],
        )
        data = ScotusDocketDataFactory(
            docket_number="25-9999",
            docket_entries=[de],
            parties=[],
            questions_presented=None,
        )

        outcome = merge_scotus_docket(data, download_file=True)
        download_followups = [
            fu
            for fu in outcome.follow_ups
            if getattr(fu, "name", None) == _FOLLOWUP_DOWNLOAD
        ]
        self.assertEqual(len(download_followups), 1)
