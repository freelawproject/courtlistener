from cl.search.docket_sources import DocketSources
from cl.search.models import Docket
from cl.tests.cases import SimpleTestCase


class UsptoPtlitigSourceTest(SimpleTestCase):
    def test_add_uspto_ptlitig_source(self) -> None:
        d = Docket(source=Docket.RECAP)
        d.add_uspto_ptlitig_source()
        self.assertEqual(d.source, Docket.RECAP_AND_USPTO_PTLITIG)

    def test_add_uspto_ptlitig_source_is_idempotent(self) -> None:
        d = Docket(source=Docket.USPTO_PTLITIG)
        d.add_uspto_ptlitig_source()
        self.assertEqual(d.source, Docket.USPTO_PTLITIG)

    def test_source_constants_are_contiguous(self) -> None:
        """The source values must stay a gap-free 0..511, since the
        source-group helpers identify membership by decomposing these."""
        values = sorted(
            value
            for name, value in vars(DocketSources).items()
            if not name.startswith("_") and isinstance(value, int)
        )
        self.assertEqual(values, list(range(512)))

    def test_uspto_ptlitig_source_groups(self) -> None:
        # A combined RECAP+PTLITIG docket still counts as a RECAP source...
        self.assertIn(
            Docket.RECAP_AND_USPTO_PTLITIG, DocketSources.RECAP_SOURCES()
        )
        # ...but a PTLITIG-only docket does not.
        self.assertNotIn(Docket.USPTO_PTLITIG, DocketSources.RECAP_SOURCES())
        non_uspto = DocketSources.NON_USPTO_PTLITIG_SOURCES()
        self.assertIn(Docket.RECAP, non_uspto)
        self.assertNotIn(Docket.USPTO_PTLITIG, non_uspto)
