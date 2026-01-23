import datetime
from unittest import mock

from django.core.files.base import ContentFile
from django.test import TestCase

from cl.corpus_importer.tasks import (
    download_qp_scotus_pdf,
    ingest_scotus_docket,
    merge_scotus_docket,
)
from cl.people_db.models import (
    Attorney,
    AttorneyOrganization,
    AttorneyOrganizationAssociation,
    Party,
    PartyType,
    Role,
)
from cl.recap.tests.tests import mock_bucket_open
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    SCOTUSAttachmentFactory,
    SCOTUSAttorneyFactory,
    ScotusDocketDataFactory,
    SCOTUSDocketEntryFactory,
    SCOTUSPartyFactory,
)
from cl.search.models import (
    Docket,
    SCOTUSDocketEntry,
    ScotusDocketMetadata,
    SCOTUSDocument,
)


class ScotusDocketMergeTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory(id="scotus", jurisdiction="F")
        cls.lower_court = CourtFactory(
            id="ca2",
            full_name="United States Court of Appeals for the Second Circuit",
            jurisdiction="A",
        )

    @mock.patch("cl.corpus_importer.tasks.logger.info")
    @mock.patch(
        "cl.corpus_importer.tasks.requests.get",
    )
    def test_merge_scotus_docket_creates_docket_and_metadata(
        self, mock_get, mock_logger_info
    ) -> None:
        """Confirm SCOTUS data is merged into Docket and metadata."""

        att_1 = SCOTUSAttachmentFactory(
            description="Main 1", document_number=23453
        )
        att_2 = SCOTUSAttachmentFactory(
            description="Attachment 2", document_number=23453
        )
        de_1 = SCOTUSDocketEntryFactory(
            description="lorem ipsum 1",
            date_filed=datetime.date(2015, 8, 19),
            document_number=23453,
            attachments=[att_1, att_2],
        )
        de_2 = SCOTUSDocketEntryFactory(
            description="lorem ipsum 2",
            date_filed=datetime.date(2015, 8, 21),
            document_number=23455,
            attachments=[
                SCOTUSAttachmentFactory(
                    description="Main 1.1 ", document_number=23455
                ),
                SCOTUSAttachmentFactory(
                    description="Attachment 2.1 ", document_number=23455
                ),
            ],
        )
        de_3 = SCOTUSDocketEntryFactory(
            description="Low after process.",
            date_filed=datetime.date(2015, 8, 22),
            document_number=None,
            attachments=[],
        )
        de_4 = SCOTUSDocketEntryFactory(
            description="Key street surface",
            date_filed=datetime.date(2015, 8, 22),
            document_number=None,
            attachments=[],
        )
        atty_1 = SCOTUSAttorneyFactory(
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
        atty_2 = SCOTUSAttorneyFactory(
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
        atty_3 = SCOTUSAttorneyFactory(
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

        party_1 = SCOTUSPartyFactory(
            name="Encino Motorcars, LLC",
            type="Petitioner",
            attorneys=[atty_1],
        )
        party_2 = SCOTUSPartyFactory(
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

        mock_response = mock.Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        with mock_bucket_open("ocr_pdf_test.pdf", "rb") as f:
            pdf_content = f.read()
        mock_response.iter_content.return_value = [pdf_content]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value.__enter__.return_value = mock_response

        ingest_scotus_docket(data)
        docket = Docket.objects.all().first()
        docket.refresh_from_db()

        self.assertEqual(mock_logger_info.call_count, 6)

        # Docket fields
        self.assertEqual(docket.court_id, self.court.pk)
        self.assertEqual(docket.source, Docket.SCRAPER)
        self.assertEqual(docket.docket_number, data["docket_number"])
        self.assertEqual(docket.case_name, data["case_name"])
        self.assertEqual(docket.date_filed, data["date_filed"])
        self.assertEqual(docket.appeal_from_str, data["lower_court"])

        self.assertEqual(docket.appeal_from_str, data["lower_court"])
        self.assertEqual(docket.appeal_from_id, self.lower_court.pk)

        # Docket entries
        des = SCOTUSDocketEntry.objects.filter(docket=docket)
        self.assertEqual(des.count(), 4, "Wrong number of Docket entries.")

        des_tests = [de_1, de_2, de_3, de_4]
        for de in des_tests:
            de_db = SCOTUSDocketEntry.objects.filter(
                docket=docket, description=de["description"]
            ).first()
            self.assertEqual(de["document_number"], de_db.entry_number)

        rds = SCOTUSDocument.objects.filter(docket_entry__docket=docket)
        self.assertEqual(rds.count(), 4, "Wrong number of Documents.")
        rds_pks = set(rds.values_list("pk", flat=True))

        rd_att_1 = SCOTUSDocument.objects.filter(
            docket_entry__docket=docket, description="Main 1"
        ).first()

        self.assertEqual(rd_att_1.document_url, att_1["document_url"])
        self.assertTrue(rd_att_1.filepath_local)
        self.assertEqual(rd_att_1.page_count, 1)
        self.assertIsNotNone(rd_att_1.sha1)
        self.assertIn("UNITED", rd_att_1.plain_text)

        rd_att_2 = SCOTUSDocument.objects.filter(
            docket_entry__docket=docket, description="Attachment 2"
        ).first()
        self.assertEqual(rd_att_2.document_url, att_2["document_url"])
        self.assertTrue(rd_att_2.filepath_local)
        self.assertIn("UNITED", rd_att_2.plain_text)

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
        expected_numbers = "22-16375, 22-16622"
        self.assertEqual(oci.docket_number, expected_numbers)
        self.assertEqual(
            oci.docket_number_raw, data.get("lower_court_case_numbers_raw")
        )
        self.assertEqual(
            oci.date_judgment,
            data["lower_court_decision_date"],
        )
        self.assertEqual(
            oci.date_rehearing_denied,
            data["lower_court_rehearing_denied_date"],
        )

        # Assert parties were created
        parties = Party.objects.filter(party_types__docket=docket)
        self.assertEqual(parties.count(), 2, "Wrong number of parties.")

        # Assert party 1 - Petitioner
        party_1_db = Party.objects.filter(
            name="Encino Motorcars, LLC", party_types__docket=docket
        ).first()
        self.assertIsNotNone(party_1_db)

        party_type_1 = PartyType.objects.filter(
            docket=docket, party=party_1_db
        ).first()
        self.assertEqual(party_type_1.name, "Petitioner")

        # Assert party 2 - Respondent
        party_2_db = Party.objects.filter(
            name="United States", party_types__docket=docket
        ).first()
        self.assertIsNotNone(party_2_db)

        party_type_2 = PartyType.objects.filter(
            docket=docket, party=party_2_db
        ).first()
        self.assertEqual(party_type_2.name, "Respondent")

        # Assert attorneys were created
        attorneys = Attorney.objects.filter(roles__docket=docket).distinct()
        self.assertEqual(attorneys.count(), 3, "Wrong number of attorneys.")

        # Assert attorney 1 - Paul D. Clement
        atty_1_db = Attorney.objects.filter(
            name="Paul D. Clement", roles__docket=docket
        ).first()
        self.assertIsNotNone(atty_1_db)
        self.assertEqual(atty_1_db.phone, "(202) 742-8900")
        self.assertEqual(atty_1_db.email, "PAUL.CLEMENT@CLEMENTMURPHY.COM")
        self.assertIn("706 Duke Street", atty_1_db.contact_raw)
        self.assertIn("Alexandria", atty_1_db.contact_raw)

        # Assert attorney 1 has LEAD role (is_counsel_of_record=True)
        atty_1_role = Role.objects.filter(
            attorney=atty_1_db, docket=docket, party=party_1_db
        ).first()
        self.assertEqual(atty_1_role.role, Role.ATTORNEY_LEAD)

        # Assert attorney 2 - Noel John Francisco
        atty_2_db = Attorney.objects.filter(
            name="Noel John Francisco", roles__docket=docket
        ).first()
        self.assertIsNotNone(atty_2_db)
        self.assertEqual(atty_2_db.email, "NJFRANCISCO@JONESDAY.COM")

        atty_2_role = Role.objects.filter(
            attorney=atty_2_db, docket=docket, party=party_2_db
        ).first()
        self.assertEqual(atty_2_role.role, Role.ATTORNEY_LEAD)

        # Assert attorney 3 - Eric Nelson (not counsel of record)
        atty_3_db = Attorney.objects.filter(
            name="Eric Nelson", roles__docket=docket
        ).first()
        self.assertIsNotNone(atty_3_db)
        self.assertEqual(atty_3_db.email, "")  # email was None

        atty_3_role = Role.objects.filter(
            attorney=atty_3_db, docket=docket, party=party_2_db
        ).first()
        # Not counsel of record, so should not be ATTORNEY_LEAD
        self.assertEqual(atty_3_role.role, Role.UNKNOWN)

        # Assert AttorneyOrganization instances were created
        attorney_orgs = AttorneyOrganization.objects.all()

        # 3 orgs expected: "Clement & Murphy, LLC", "Law Firm Test LLC" and
        # Eric Nelson.
        self.assertEqual(
            attorney_orgs.count(), 3, "Wrong number of attorney organizations."
        )

        # Assert organization 1 - Clement & Murphy, LLC
        org_1 = AttorneyOrganization.objects.filter(
            name="Clement & Murphy, LLC"
        ).first()
        self.assertIsNotNone(org_1)
        self.assertEqual(org_1.address1, "706 Duke St.")
        self.assertEqual(org_1.city, "Alexandria")
        self.assertEqual(org_1.state, "VA")
        self.assertEqual(org_1.zip_code, "22314")

        # Assert organization 2 - Law Firm Test LLC
        org_2 = AttorneyOrganization.objects.filter(
            name="Law Firm Test LLC"
        ).first()
        self.assertIsNotNone(org_2)
        self.assertEqual(org_2.address1, "51 Louisiana Ave., NW")
        self.assertEqual(org_2.city, "Washington")
        self.assertEqual(org_2.state, "DC")
        self.assertEqual(org_2.zip_code, "20001")

        org_3 = AttorneyOrganization.objects.filter(name="Eric Nelson").first()
        self.assertIsNotNone(org_3)
        self.assertEqual(org_3.address1, "54 Florence St.")
        self.assertEqual(org_3.city, "Staten Island")
        self.assertEqual(org_3.state, "NY")
        self.assertEqual(org_3.zip_code, "10308")

        # Assert AttorneyOrganizationAssociation links attorneys to orgs
        assoc_1 = AttorneyOrganizationAssociation.objects.filter(
            attorney=atty_1_db, attorney_organization=org_1, docket=docket
        ).first()
        self.assertIsNotNone(
            assoc_1,
        )
        assoc_2 = AttorneyOrganizationAssociation.objects.filter(
            attorney=atty_2_db, attorney_organization=org_2, docket=docket
        ).first()
        self.assertIsNotNone(
            assoc_2,
        )
        assoc_3 = AttorneyOrganizationAssociation.objects.filter(
            attorney=atty_3_db, docket=docket
        ).first()
        self.assertIsNotNone(
            assoc_3,
        )

        # Merge again. Confirm objects are not duplicated.
        ingest_scotus_docket(data)
        docket.refresh_from_db()

        # No additional calls to the download methods’ loggers.
        self.assertEqual(mock_logger_info.call_count, 6)

        # Docket entries
        des = SCOTUSDocketEntry.objects.filter(docket=docket)
        self.assertEqual(des.count(), 4, "Wrong number of Docket entries.")

        rds = SCOTUSDocument.objects.filter(docket_entry__docket=docket)
        self.assertEqual(rds.count(), 4, "Wrong number of Documents")
        rds_pks_new = set(rds.values_list("pk", flat=True))
        self.assertEqual(rds_pks, rds_pks_new)

        rd_att_1_1 = SCOTUSDocument.objects.filter(
            docket_entry__docket=docket, description="Main 1"
        ).first()
        rd_att_2_1 = SCOTUSDocument.objects.filter(
            docket_entry__docket=docket, description="Attachment 2"
        ).first()
        self.assertEqual(rd_att_1.pk, rd_att_1_1.pk)
        self.assertEqual(rd_att_2.pk, rd_att_2_1.pk)

        # No more parties created.
        parties_after = Party.objects.filter(party_types__docket=docket)
        self.assertEqual(parties_after.count(), 2, "Parties were duplicated.")

        attorneys_after = Attorney.objects.filter(
            roles__docket=docket
        ).distinct()
        self.assertEqual(
            attorneys_after.count(), 3, "Attorneys were duplicated."
        )

        attorney_orgs = AttorneyOrganization.objects.all()

        self.assertEqual(
            attorneys_after.count(), 3, "AttorneysOrgs were duplicated."
        )

    def test_merge_scotus_docket_updates_existing_docket(self) -> None:
        """Confirm merging again updates an existing SCOTUS docket."""

        data = ScotusDocketDataFactory(
            docket_number="23A1434",
            case_name="Old Name",
            capital_case=False,
            lower_court=self.lower_court.full_name,
            docket_entries=[],
        )
        docket, _ = merge_scotus_docket(data)
        docket.refresh_from_db()

        dockets = Docket.objects.all()
        self.assertEqual(dockets.count(), 1)
        scotus_metadata = ScotusDocketMetadata.objects.all()
        self.assertEqual(scotus_metadata.count(), 1)

        # Updated data.
        data = ScotusDocketDataFactory(
            case_name="New SCOTUS Case Name",
            docket_number="23A1434",
            capital_case=True,
            linked_with="23-6433",
            lower_court=self.lower_court.full_name,
            lower_court_case_numbers=["23-6433"],
            docket_entries=[],
        )
        updated_docket, _ = merge_scotus_docket(data)
        updated_docket.refresh_from_db()
        self.assertEqual(dockets.count(), 1)
        self.assertEqual(scotus_metadata.count(), 1)

        self.assertEqual(updated_docket.pk, docket.pk)
        self.assertEqual(updated_docket.source, Docket.SCRAPER)
        self.assertEqual(updated_docket.case_name, "New SCOTUS Case Name")
        self.assertEqual(updated_docket.date_filed, data["date_filed"])

        # ScotusDocketMetadata fields
        metadata = updated_docket.scotus_metadata
        self.assertTrue(metadata.capital_case)
        self.assertEqual(
            metadata.date_discretionary_court_decision,
            data["discretionary_court_decision"],
        )
        self.assertEqual(metadata.linked_with, data["links"])
        self.assertEqual(
            metadata.questions_presented_url, data["questions_presented"]
        )

    def test_merge_scotus_docket_missing_docket_number(self) -> None:
        """Confirm ValueError is raised when docket_number is missing."""

        data = ScotusDocketDataFactory(
            case_name="New SCOTUS Case Name",
            docket_number=None,
            docket_entries=[],
        )

        with self.assertRaisesMessage(
            ValueError,
            "Docket number can't be missing in SCOTUS dockets.",
        ):
            merge_scotus_docket(data)

    @mock.patch("cl.corpus_importer.tasks.is_pdf", return_value=True)
    @mock.patch("cl.corpus_importer.tasks.requests.get")
    def test_download_qp_scotus_pdf_downloads_and_stores_file(
        self,
        mock_get,
        mock_is_pdf,
    ) -> None:
        """Confirm the SCOTUS QP PDF is downloaded and stored."""

        docket = DocketFactory.create(court=self.court)
        scotus_meta = ScotusDocketMetadata.objects.create(
            docket=docket,
            questions_presented_url="https://www.supremecourt.gov/qp.pdf",
        )
        self.assertFalse(scotus_meta.questions_presented_file)

        # Mock the response from requests.get
        mock_response = mock.Mock()
        mock_response.iter_content.return_value = [b"fake pdf content"]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value.__enter__.return_value = mock_response

        download_qp_scotus_pdf.delay(docket.id)

        mock_get.assert_called_once_with(
            scotus_meta.questions_presented_url,
            stream=True,
            timeout=60,
            headers={"User-Agent": "Free Law Project"},
        )

        scotus_meta.refresh_from_db()

        # Confirm the file was stored
        self.assertTrue(scotus_meta.questions_presented_file)
        self.assertTrue(
            scotus_meta.questions_presented_file.name.endswith("-qp.pdf")
        )

    @mock.patch("cl.corpus_importer.tasks.logger.info")
    @mock.patch("cl.corpus_importer.tasks.requests.get")
    def test_download_qp_scotus_pdf_skips_if_file_already_present(
        self,
        mock_get,
        mock_logger_info,
    ) -> None:
        """Confirm download is skipped when questions_presented_file exists."""

        docket = DocketFactory.create(court=self.court)
        scotus_meta = ScotusDocketMetadata.objects.create(
            docket=docket,
            questions_presented_url="https://www.supremecourt.gov/qp.pdf",
        )
        scotus_meta.questions_presented_file.save(
            "existing.pdf",
            ContentFile(b"existing content"),
            save=True,
        )

        download_qp_scotus_pdf.delay(docket.id)

        # No GET request should have been made
        mock_get.assert_not_called()

        mock_logger_info.assert_called_with(
            "SCOTUS PDF download: questions_presented_file already present "
            "for docket %s; skipping.",
            docket.id,
        )

    @mock.patch("cl.lib.courts.logger")
    def test_logs_error_when_lower_court_not_found(self, mock_logger) -> None:
        """Confirm merge logs error when lower court is not found in courts-db."""
        data = ScotusDocketDataFactory(
            docket_number="23-1435",
            lower_court="Imaginary Court of The Dragons",
            lower_court_case_numbers=["10-1000"],
            docket_entries=[],
        )

        docket, _ = merge_scotus_docket(data)
        docket.refresh_from_db()

        self.assertEqual(docket.appeal_from_str, data["lower_court"])
        self.assertIsNone(docket.appeal_from)

        mock_logger.error.assert_called_with(
            "Could not find court IDs from name '%s'.",
            "Imaginary Court of The Dragons",
        )

    @mock.patch("cl.lib.courts.find_court")
    @mock.patch("cl.lib.courts.logger")
    def test_logs_error_when_lower_court_ambiguous(
        self,
        mock_logger,
        mock_find_court,
    ) -> None:
        """Confirm merge logs error when lower courts-db lookup is ambiguous."""
        mock_find_court.return_value = ["mab", "mad"]

        data = ScotusDocketDataFactory(
            docket_number="23-1436",
            lower_court="District of Massachusetts",
            lower_court_case_numbers=["10-2000"],
            docket_entries=[],
        )

        docket, _ = merge_scotus_docket(data)
        docket.refresh_from_db()

        self.assertEqual(docket.appeal_from_str, data["lower_court"])
        self.assertIsNone(docket.appeal_from)

        mock_logger.error.assert_called_with(
            "Ambiguous court name '%s' in courts-db: %s",
            "District of Massachusetts",
            ["mab", "mad"],
        )

    @mock.patch("cl.lib.courts.find_court")
    @mock.patch("cl.lib.courts.logger")
    def test_logs_error_when_lower_court_id_missing_in_db(
        self,
        mock_logger,
        mock_find_court,
    ) -> None:
        """Confirm merge logs error when lower court_id does not exist in DB."""
        mock_find_court.return_value = ["cadc123"]

        data = ScotusDocketDataFactory(
            docket_number="23-1437",
            lower_court="Non-existent Court",
            lower_court_case_numbers=["10-3000"],
            docket_entries=[],
        )

        docket, _ = merge_scotus_docket(data)
        docket.refresh_from_db()

        self.assertEqual(docket.appeal_from_str, data["lower_court"])
        self.assertIsNone(docket.appeal_from)

        mock_logger.error.assert_called_with(
            "Court object does not exist in DB for id '%s' (name: '%s').",
            "cadc123",
            "Non-existent Court",
        )
