"""Tests for the state document storage paths and the NYCoA factories."""

from cl.search.state.florida.factories import FloridaDocumentFactory
from cl.search.state.new_york.factories import (
    NYCoADocketEntryFactory,
    NYCoADocketIssueFactory,
    NYCoADocketMetadataFactory,
    NYCoADocumentFactory,
)
from cl.search.state.shared import state_pdf_path
from cl.search.state.texas.factories import TexasDocumentFactory
from cl.tests.cases import SimpleTestCase, TestCase


class StatePdfPathTest(SimpleTestCase):
    """Tests for the path helper the state document models share."""

    def test_builds_the_same_layout_for_every_state(self):
        """One layout, varying only by state code."""
        for code in ("ny", "fl", "tx"):
            with self.subTest(code=code):
                self.assertEqual(
                    state_pdf_path(code, "xyz", "A B.pdf"),
                    f"us/state/{code}/xyz/gov.{code}.xyz.a-b.pdf",
                )

    def test_thumbnails_get_a_sibling_directory(self):
        """Thumbnails must not collide with the document itself."""
        self.assertEqual(
            state_pdf_path("ny", "nycoa", "A B.pdf", thumbs=True),
            "us/state/ny/nycoa-thumbnails/gov.ny.nycoa.a-b.pdf",
        )

    def test_preserves_non_pdf_extensions(self):
        """TAMES serves .html and .wpd, and Court-PASS serves playlists."""
        self.assertEqual(
            state_pdf_path("tx", "tex", "brief.wpd"),
            "us/state/tx/tex/gov.tx.tex.brief.wpd",
        )

    def test_defaults_a_missing_extension_to_pdf(self):
        self.assertEqual(
            state_pdf_path("fl", "fla", "brief"),
            "us/state/fl/fla/gov.fl.fla.brief.pdf",
        )


class StateDocumentPathTest(TestCase):
    """Each state document model must resolve its own storage path.

    These pin the paths that `make_pdf_path` produced before the polymorphism
    moved onto the models, so existing objects stay reachable.
    """

    def assertDelegatesToHelper(self, document, code: str) -> None:
        """Assert a document resolves to the shared layout for `code`.

        Each state gets its own test method rather than a `subTest` loop:
        building two entries in one test trips `AttorneyOrganizationFactory`'s
        blank-`lookup_key` collision, which predates these models.
        """
        court_id = document.docket_entry.docket.court_id
        self.assertEqual(
            document.get_pdf_path("Foo Bar.pdf"),
            f"us/state/{code}/{court_id}/gov.{code}.{court_id}.foo-bar.pdf",
        )
        self.assertEqual(
            document.get_pdf_path("Foo Bar.pdf", thumbs=True),
            f"us/state/{code}/{court_id}-thumbnails/"
            f"gov.{code}.{court_id}.foo-bar.pdf",
        )

    def test_nycoa_document_path(self):
        self.assertDelegatesToHelper(NYCoADocumentFactory(), "ny")

    def test_florida_document_path(self):
        self.assertDelegatesToHelper(FloridaDocumentFactory(), "fl")

    def test_texas_document_path(self):
        self.assertDelegatesToHelper(TexasDocumentFactory(), "tx")

    def test_nycoa_filenames_do_not_collide(self):
        """Court-PASS serves every document from one POST endpoint, so the
        base implementation's URL-derived name would collapse to one value."""
        entry = NYCoADocketEntryFactory()
        first = NYCoADocumentFactory(docket_entry=entry)
        second = NYCoADocumentFactory(docket_entry=entry)
        self.assertEqual(first.url, second.url)
        self.assertNotEqual(first.make_filename(), second.make_filename())


class NYCoAFactoryTest(TestCase):
    """The NYCoA factories must produce rows the models accept."""

    def test_factories_build_coherent_rows(self):
        metadata = NYCoADocketMetadataFactory()
        issue = NYCoADocketIssueFactory(metadata=metadata)
        self.assertEqual(issue.metadata_id, metadata.pk)

        entry = NYCoADocketEntryFactory()
        self.assertIsNotNone(entry.party, "party should be populated")
        # PartyFactory's `docket` kwarg wires up the party's Role, so that is
        # where the tie back to the entry's docket shows up.
        self.assertEqual(entry.party.roles.first().docket_id, entry.docket_id)
        self.assertGreater(entry.date_due, entry.date_filed)

    def test_document_volume_and_part_stay_consistent(self):
        """`part` only means something for a volume that exists.

        All the documents hang off one entry because each new entry drags in a
        party, attorney, and attorney organization, and
        `AttorneyOrganizationFactory` collides on its blank `lookup_key` past
        a handful of rows -- which is true of the Florida factories too.
        """
        entry = NYCoADocketEntryFactory()
        documents = [
            NYCoADocumentFactory(docket_entry=entry) for _ in range(40)
        ]
        self.assertTrue(
            any(d.volume for d in documents), "volume is never set"
        )
        self.assertTrue(
            all(d.volume for d in documents if d.part),
            "part was set on a document with no volume",
        )
