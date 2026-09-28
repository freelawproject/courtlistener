import tempfile
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup
from django.core.management import call_command

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
from cl.search.models import Citation, Court, Docket, Opinion, OpinionCluster
from cl.tests.cases import SimpleTestCase, TestCase

SCAN_XML_PATH = str(
    Path(__file__).parent / "test_assets" / "scanned_opinion.xml"
)


def make_soup(xml: str) -> BeautifulSoup:
    """Parse XML the same way the importer does."""
    return BeautifulSoup(xml, "lxml-xml")


class ScanXmlHelpersTest(SimpleTestCase):
    """Tests for the scanning project final XML parsing helpers."""

    def test_normalize_case_name_caps(self) -> None:
        """Are words printed in caps titlecased, keeping short acronyms?"""
        cases = [
            (
                "Larry B. MERRITT v. STATE of Florida",
                "Larry B. Merritt v. State of Florida",
            ),
            ("In re ESTATE OF John SMITH", "In re Estate of John Smith"),
            ("ACME LLC v. John ROBERTS", "Acme LLC v. John Roberts"),
            ("Jane Roe v. Richard Roe", "Jane Roe v. Richard Roe"),
        ]
        for case_name, expected in cases:
            with self.subTest(case_name=case_name):
                self.assertEqual(normalize_case_name_caps(case_name), expected)

    def test_get_date_filed(self) -> None:
        """Can we parse bracketed, prefixed and missing decision dates?"""
        cases = [
            ("<decisiondate>[May 22, 2024]</decisiondate>", date(2024, 5, 22)),
            (
                "<decisiondate>Decided Dec. 18, 2009.</decisiondate>",
                date(2009, 12, 18),
            ),
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

    def import_scan(self, **kwargs) -> None:
        """Run the command over the test XML."""
        options = {"court_id": self.court.pk, "path": SCAN_XML_PATH} | kwargs
        call_command("import_scanned_opinions", **options)

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

    def test_reimport_is_skipped(self) -> None:
        """Is an already imported scanned opinion skipped?"""
        self.import_scan()
        self.import_scan()
        self.assertEqual(OpinionCluster.objects.count(), 1)
        self.assertEqual(Opinion.objects.count(), 1)

    def test_merge_into_existing_cluster(self) -> None:
        """Is a scanned opinion merged into a matching cluster?"""
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
        )
        Citation.objects.create(
            cluster=cluster,
            volume=388,
            reporter="So. 3d",
            page="1",
            type=Citation.STATE_REGIONAL,
        )
        opinion = OpinionFactory.create(
            cluster=cluster, plain_text=self.opinion_text, html=""
        )

        self.import_scan()

        self.assertEqual(OpinionCluster.objects.count(), 1)
        self.assertEqual(Opinion.objects.count(), 1)
        cluster.refresh_from_db()
        docket.refresh_from_db()
        opinion.refresh_from_db()
        self.assertEqual(cluster.source, "CS")
        self.assertIn("pro se", cluster.attorneys)
        self.assertRegex(
            cluster.filepath_xml_scan.name,
            r"/388-so-3d-1(_[A-Za-z0-9]+)?\.xml$",
        )
        self.assertEqual(docket.source, Docket.SCRAPER_AND_SCANNING_PROJECT)
        self.assertIn("confession of error", opinion.xml_scan)

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

    def test_court_lookup(self) -> None:
        """Is the court found from the court element when not given?"""
        self.import_scan(court_id=None)
        self.assertEqual(
            OpinionCluster.objects.get().docket.court_id, self.court.pk
        )

    def test_skip_without_citation(self) -> None:
        """Is a scanned opinion without citation skipped?"""
        with open(SCAN_XML_PATH, encoding="utf-8") as f:
            xml = f.read().replace("<citation>388 So. 3d 1</citation>", "")
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "no_citation.xml").write_text(xml, encoding="utf-8")
            self.import_scan(path=tmp_dir)
        self.assertEqual(OpinionCluster.objects.count(), 0)
