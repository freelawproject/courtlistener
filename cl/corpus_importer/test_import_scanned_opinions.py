import re
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

from bs4 import BeautifulSoup
from django.core.management import call_command
from django.db.models.fields.files import FieldFile

from cl.corpus_importer.management.commands.import_scanned_opinions import (
    get_citation_strings,
    get_date_filed,
    get_docket_number,
    make_opinion,
    normalize_case_name_caps,
)
from cl.search.cluster_sources import ClusterSources
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionFactory,
)
from cl.search.models import (
    Citation,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
    OpinionContent,
)
from cl.tests.cases import SimpleTestCase, TestCase

COMMAND_MODULE = (
    "cl.corpus_importer.management.commands.import_scanned_opinions"
)
SCAN_XML_PATH = str(
    Path(__file__).parent / "test_assets" / "scanned_opinion.xml"
)


def make_soup(xml: str) -> BeautifulSoup:
    """Parse XML the same way the importer does."""
    return BeautifulSoup(xml, "lxml-xml")


class ScanXmlHelpersTest(SimpleTestCase):
    """Tests for the scanning project final XML parsing helpers."""

    def test_normalize_case_name_caps(self) -> None:
        """Are words printed in caps titlecased, keeping acronyms?"""
        cases = [
            (
                "Larry B. MERRITT v. STATE of Florida",
                "Larry B. Merritt v. State of Florida",
            ),
            ("In re ESTATE OF John SMITH", "In re Estate of John Smith"),
            ("IN RE ESTATE OF John SMITH", "In re Estate of John Smith"),
            ("Robert LEE v. Bobby COX", "Robert Lee v. Bobby Cox"),
            ("ACME LLC v. John DOE", "Acme LLC v. John Doe"),
            ("USA v. ONE 1990 FORD", "USA v. One 1990 Ford"),
            (
                "Mary O'BRIEN v. STATE'S ATTORNEY",
                "Mary O'Brien v. State's Attorney",
            ),
            (
                "Ann SMITH-JONES v. John McDONALD",
                "Ann Smith-Jones v. John McDonald",
            ),
            ("Jane Roe v. Richard Roe", "Jane Roe v. Richard Roe"),
        ]
        for case_name, expected in cases:
            with self.subTest(case_name=case_name):
                self.assertEqual(normalize_case_name_caps(case_name), expected)

    def test_get_date_filed(self) -> None:
        """Can we parse complete decision dates and reject partial ones?"""
        cases = [
            ("<decisiondate>[May 22, 2024]</decisiondate>", date(2024, 5, 22)),
            (
                "<decisiondate>Decided Dec. 18, 2009.</decisiondate>",
                date(2009, 12, 18),
            ),
            (
                "<decisiondate>Opinion filed Sept. 3, 2024</decisiondate>",
                date(2024, 9, 3),
            ),
            ("<decisiondate>5/22/2024</decisiondate>", date(2024, 5, 22)),
            (
                "<decisiondate>May 22, 2024. Rehearing Denied "
                "June 30, 2024.</decisiondate>",
                date(2024, 5, 22),
            ),
            (
                "<casebody><decisiondate>[May 22, 2024]</decisiondate>"
                "<decisiondate>[June 30, 2024]</decisiondate></casebody>",
                date(2024, 5, 22),
            ),
            (
                "<casebody><decisiondate>Undated</decisiondate>"
                "<decisiondate>June 30, 2024</decisiondate></casebody>",
                date(2024, 6, 30),
            ),
            ("<decisiondate>May 2024</decisiondate>", None),
            ("<decisiondate>2024</decisiondate>", None),
            ("<decisiondate>Feb. 30, 2024</decisiondate>", None),
            ("<decisiondate>Not a date</decisiondate>", None),
            ("<court>No date here</court>", None),
        ]
        for xml, expected in cases:
            with self.subTest(xml=xml):
                self.assertEqual(get_date_filed(make_soup(xml)), expected)

    def test_get_citation_strings(self) -> None:
        """Are citations read from the citation elements?"""
        cases = [
            (
                "<casebody><citation>388 So. 3d 7</citation>"
                "<citation>12 Fla. L. Weekly 3</citation></casebody>",
                ["388 So. 3d 7", "12 Fla. L. Weekly 3"],
            ),
            ("<casebody><citation> </citation></casebody>", []),
            ('<casebody firstpage="7"></casebody>', []),
        ]
        for xml, expected in cases:
            with self.subTest(xml=xml):
                self.assertEqual(
                    get_citation_strings(make_soup(xml)), expected
                )

    def test_get_docket_number(self) -> None:
        """Is the printed "No." prefix removed from docket numbers?"""
        cases = [
            ("<docketnumber>No. 4D2023-2459.</docketnumber>", "4D2023-2459"),
            (
                "<docketnumber>Nos. 1D22-1, 1D22-2</docketnumber>",
                "1D22-1, 1D22-2",
            ),
            ("<docketnumber>Case No. SC2024-1</docketnumber>", "SC2024-1"),
            ("<docketnumber>NOV-123</docketnumber>", "NOV-123"),
            (
                "<casebody><docketnumber>No. 1</docketnumber>"
                "<docketnumber>No. 2</docketnumber></casebody>",
                "1; 2",
            ),
            ("<casebody/>", ""),
        ]
        for xml, expected in cases:
            with self.subTest(xml=xml):
                self.assertEqual(get_docket_number(make_soup(xml)), expected)

    def test_make_opinion(self) -> None:
        """Are the author, per curiam and type read from the opinion?"""
        cases = [
            (
                "<opinion><author>Gerber, J.</author></opinion>",
                "Gerber",
                False,
                Opinion.COMBINED,
            ),
            (
                "<opinion><author>PER CURIAM.</author></opinion>",
                "Per Curiam",
                True,
                Opinion.COMBINED,
            ),
            (
                "<opinion><author>Per Curiam:</author></opinion>",
                "Per Curiam",
                True,
                Opinion.COMBINED,
            ),
            (
                '<opinion type="dissent"><author>WARNER, J.</author></opinion>',
                "Warner",
                False,
                Opinion.DISSENT,
            ),
            (
                "<opinion><p>No author.</p></opinion>",
                "",
                False,
                Opinion.COMBINED,
            ),
        ]
        for xml, author_str, per_curiam, op_type in cases:
            with self.subTest(xml=xml):
                op = make_soup(xml).select_one("opinion")
                if op is None:
                    self.fail(f"No opinion in {xml}")
                opinion = make_opinion(op, cluster_id=1)
                self.assertEqual(opinion.author_str, author_str)
                self.assertEqual(opinion.per_curiam, per_curiam)
                self.assertEqual(opinion.type, op_type)
                self.assertEqual(opinion.xml_scan, xml)


class ImportScannedOpinionsTest(TestCase):
    """Tests for the import_scanned_opinions command."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create(
            id="fladistctapp4", jurisdiction=Court.STATE_APPELLATE
        )
        with open(SCAN_XML_PATH, encoding="utf-8") as f:
            opinion = make_soup(f.read()).select_one("opinion")
        if opinion is None:
            raise ValueError("The test XML must have an opinion")
        cls.opinion_text = opinion.get_text(" ")
        with open(SCAN_XML_PATH, encoding="utf-8") as f:
            cls.scan_xml = f.read()

    def import_scan(self, **kwargs: str | None) -> None:
        """Run the command over the test XML."""
        options = {"court_id": self.court.pk, "path": SCAN_XML_PATH} | kwargs
        call_command("import_scanned_opinions", **options)

    def import_xml(self, xml: str, **kwargs: str | None) -> None:
        """Run the command over an XML written to a temporary directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "scan.xml").write_text(xml, encoding="utf-8")
            self.import_scan(path=tmp_dir, **kwargs)

    def make_matching_cluster(self, opinion_count: int = 1) -> OpinionCluster:
        """Make a court website cluster that matches the test XML."""
        docket = DocketFactory.create(
            court=self.court,
            source=Docket.SCRAPER,
            docket_number="4D2023-2459",
            case_name="Merritt v. State",
        )
        cluster = OpinionClusterFactory.create(
            docket=docket,
            case_name="Merritt v. State",
            date_filed=date(2024, 5, 22),
            source=ClusterSources.COURT_WEBSITE,
            attorneys="",
            judges="",
        )
        Citation.objects.create(
            cluster=cluster,
            volume=388,
            reporter="So. 3d",
            page="1",
            type=Citation.STATE_REGIONAL,
        )
        OpinionFactory.create_batch(
            opinion_count,
            cluster=cluster,
            plain_text=self.opinion_text,
            html="",
        )
        return cluster

    def test_import_new_case(self) -> None:
        """Does a new scanned opinion create its docket, cluster and opinion?"""
        self.import_scan()

        cluster = OpinionCluster.objects.get()
        self.assertEqual(
            cluster.case_name, "Larry B. Merritt v. State of Florida"
        )
        self.assertEqual(cluster.source, ClusterSources.SCANNING_PROJECT)
        self.assertEqual(cluster.date_filed, date(2024, 5, 22))
        self.assertIn("pro se", cluster.attorneys)
        self.assertIn("Reversed and remanded", cluster.disposition)
        self.assertIn("Palm Beach County", cluster.history)
        self.assertIn("Gerber", cluster.judges)
        self.assertRegex(
            cluster.filepath_xml_scan.name,
            r"/388-so-3d-1(_[A-Za-z0-9]+)?\.xml$",
        )

        docket = cluster.docket
        self.assertEqual(docket.source, Docket.SCANNING_PROJECT)
        self.assertEqual(docket.court_id, self.court.pk)
        self.assertEqual(docket.docket_number, "4D2023-2459")

        citation = Citation.objects.get(cluster=cluster)
        self.assertEqual(
            (citation.volume, citation.reporter, citation.page),
            ("388", "So. 3d", "1"),
        )

        opinion = Opinion.objects.get(cluster=cluster)
        self.assertTrue(opinion.xml_scan.startswith("<opinion>"))
        self.assertIn("confession of error", opinion.xml_scan)
        self.assertEqual(opinion.author_str, "Gerber")
        self.assertEqual(opinion.type, Opinion.COMBINED)
        self.assertTrue(opinion.extracted_by_ocr)

        content = OpinionContent.objects.get(opinion=opinion)
        self.assertEqual(content.content, opinion.xml_scan)
        self.assertEqual(content.source, OpinionContent.FLP_SCANNING)
        self.assertEqual(content.extraction_type, OpinionContent.LLM)
        self.assertTrue(content.is_main_version)
        self.assertEqual(len(content.sha1), 40)
        self.assertEqual(content.page_count, 4)

    def test_reimport_is_skipped(self) -> None:
        """Is an already imported scanned opinion skipped?"""
        self.import_scan()
        self.import_scan()
        self.assertEqual(OpinionCluster.objects.count(), 1)
        self.assertEqual(Opinion.objects.count(), 1)

    def test_merge_into_existing_cluster(self) -> None:
        """Is a scanned opinion merged into a matching cluster?"""
        cluster = self.make_matching_cluster()

        self.import_scan()

        self.assertEqual(OpinionCluster.objects.count(), 1)
        self.assertEqual(Opinion.objects.count(), 1)
        self.assertEqual(Citation.objects.count(), 1)
        cluster.refresh_from_db()
        self.assertEqual(
            cluster.source,
            ClusterSources.merge_sources(
                ClusterSources.COURT_WEBSITE, ClusterSources.SCANNING_PROJECT
            ),
        )
        self.assertIn("pro se", cluster.attorneys)
        self.assertIn("Gerber", cluster.judges)
        self.assertRegex(
            cluster.filepath_xml_scan.name,
            r"/388-so-3d-1(_[A-Za-z0-9]+)?\.xml$",
        )
        self.assertEqual(
            cluster.docket.source, Docket.SCRAPER_AND_SCANNING_PROJECT
        )
        opinion = cluster.sub_opinions.get()
        self.assertIn("confession of error", opinion.xml_scan)
        content = OpinionContent.objects.get(opinion=opinion)
        self.assertEqual(content.content, opinion.xml_scan)
        self.assertTrue(content.is_main_version)

    def test_merge_ignores_opinion_versions(self) -> None:
        """Is the scan merged into the main opinion, ignoring its versions?"""
        cluster = self.make_matching_cluster()
        main_opinion = cluster.sub_opinions.get()
        version = OpinionFactory.create(
            cluster=cluster,
            plain_text=self.opinion_text,
            html="",
            main_version=main_opinion,
        )

        self.import_scan()

        main_opinion.refresh_from_db()
        version.refresh_from_db()
        self.assertIn("confession of error", main_opinion.xml_scan)
        self.assertEqual(version.xml_scan, "")
        self.assertEqual(
            list(OpinionContent.objects.values_list("opinion_id", flat=True)),
            [main_opinion.pk],
        )

    def test_merge_skips_opinions_when_counts_differ(self) -> None:
        """Is the opinion text left alone when opinions can't be paired?"""
        cluster = self.make_matching_cluster(opinion_count=2)

        with mock.patch(f"{COMMAND_MODULE}.logger") as mock_logger:
            self.import_scan()

        cluster.refresh_from_db()
        self.assertTrue(cluster.filepath_xml_scan)
        self.assertFalse(cluster.sub_opinions.exclude(xml_scan="").exists())
        self.assertFalse(OpinionContent.objects.exists())
        self.assertIn(
            "Opinion content was not merged",
            mock_logger.warning.call_args[0][0],
        )

    def test_import_multiple_opinions(self) -> None:
        """Is each opinion element imported as an opinion with its type?"""
        xml = self.scan_xml.replace(
            "</opinion>",
            '</opinion><opinion type="dissent"><author>WARNER, J.</author>'
            "<p>I respectfully dissent.</p></opinion>",
        )

        self.import_xml(xml)

        opinions = Opinion.objects.order_by("pk")
        self.assertEqual(
            [(o.type, o.author_str) for o in opinions],
            [(Opinion.COMBINED, "Gerber"), (Opinion.DISSENT, "Warner")],
        )

    def test_reuse_existing_docket(self) -> None:
        """Is an existing docket without a matching cluster reused?"""
        docket = DocketFactory.create(
            court=self.court,
            source=Docket.SCRAPER,
            docket_number="4D2023-2459",
            docket_number_raw="4D2023-2459",
            case_name="Merritt v. State",
        )

        self.import_scan()

        self.assertEqual(Docket.objects.count(), 1)
        docket.refresh_from_db()
        self.assertEqual(docket.source, Docket.SCRAPER_AND_SCANNING_PROJECT)
        self.assertEqual(OpinionCluster.objects.get().docket_id, docket.pk)

    def test_scan_from_another_reporter_is_not_duplicated(self) -> None:
        """Is a scan of a case already imported from a scan detected by text?"""
        self.import_scan()
        xml = self.scan_xml.replace("388 So. 3d 1", "49 Fla. L. Weekly D1100")
        with mock.patch(f"{COMMAND_MODULE}.logger") as mock_logger:
            self.import_xml(xml)

        self.assertEqual(OpinionCluster.objects.count(), 1)
        self.assertIn(
            "which already has scan XML", mock_logger.warning.call_args[0][0]
        )

    def test_other_opinion_on_same_page_is_imported(self) -> None:
        """Is a different case with the same citation imported?"""
        self.import_scan()
        xml = """<?xml version="1.0" encoding="utf-8"?>
<casebody firstpage="1" lastpage="1">
  <citation>388 So. 3d 1</citation>
  <parties><party>John DOEWELL, Appellant,</party> <separator>v.</separator>
  <party>STATE of Florida, Appellee.</party></parties>
  <docketnumber>No. 4D2023-9999</docketnumber>
  <court>District Court of Appeal of Florida, Fourth District.</court>
  <decisiondate>[May 22, 2024]</decisiondate>
  <opinion><author>PER CURIAM.</author><p>Affirmed.</p></opinion>
</casebody>"""
        self.import_xml(xml)

        self.assertEqual(OpinionCluster.objects.count(), 2)
        new_cluster = OpinionCluster.objects.get(
            docket__docket_number="4D2023-9999"
        )
        self.assertEqual(
            new_cluster.case_name, "John Doewell v. State of Florida"
        )
        self.assertTrue(
            Citation.objects.filter(
                cluster=new_cluster, volume="388", reporter="So. 3d", page="1"
            ).exists()
        )

    def test_failed_import_is_rolled_back(self) -> None:
        """Is a failed import rolled back without uploading the XML?"""
        with (
            mock.patch(
                f"{COMMAND_MODULE}.make_opinion",
                side_effect=ValueError("boom"),
            ),
            mock.patch(f"{COMMAND_MODULE}.logger") as mock_logger,
            mock.patch.object(FieldFile, "save") as mock_file_save,
        ):
            self.import_scan()

        self.assertEqual(OpinionCluster.objects.count(), 0)
        self.assertEqual(Docket.objects.count(), 0)
        mock_file_save.assert_not_called()
        mock_logger.exception.assert_called_once()

    def test_failed_file_does_not_stop_the_run(self) -> None:
        """Does the command continue with the next file after a failure?"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            for name in ["1.xml", "2.xml"]:
                Path(tmp_dir, name).write_text("<casebody/>", encoding="utf-8")
            with (
                mock.patch(
                    f"{COMMAND_MODULE}.parse_scan_xml",
                    side_effect=[ValueError("boom"), None],
                ) as mock_parse,
                mock.patch(f"{COMMAND_MODULE}.logger") as mock_logger,
            ):
                self.import_scan(path=tmp_dir)

        self.assertEqual(mock_parse.call_count, 2)
        mock_logger.exception.assert_called_once()

    def test_court_lookup(self) -> None:
        """Is the court found from the court element when not given?"""
        self.import_scan(court_id=None)
        self.assertEqual(
            OpinionCluster.objects.get().docket.court_id, self.court.pk
        )

    def test_skip_invalid_files(self) -> None:
        """Are files lacking required data skipped with a warning?"""
        cases = [
            (
                "No valid citation",
                self.scan_xml.replace("<citation>388 So. 3d 1</citation>", ""),
                self.court.pk,
            ),
            (
                "No parties",
                re.sub(r"<parties>.*?</parties>", "", self.scan_xml),
                self.court.pk,
            ),
            (
                "No opinion",
                re.sub(
                    r"<opinion>.*</opinion>", "", self.scan_xml, flags=re.S
                ),
                self.court.pk,
            ),
            (
                "Can't parse date",
                self.scan_xml.replace("[May 22, 2024]", "Undated"),
                self.court.pk,
            ),
            (
                "Court not found",
                self.scan_xml.replace("Fourth District", "Tenth Circuit"),
                None,
            ),
        ]
        for message, xml, court_id in cases:
            with (
                self.subTest(message=message),
                mock.patch(f"{COMMAND_MODULE}.logger") as mock_logger,
            ):
                self.import_xml(xml, court_id=court_id)
                self.assertEqual(OpinionCluster.objects.count(), 0)
                self.assertIn(message, mock_logger.warning.call_args[0][0])
