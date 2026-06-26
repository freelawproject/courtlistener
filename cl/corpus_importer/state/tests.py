from typing import Any, ClassVar

from django.db.models import Model

from cl.corpus_importer.state.merger import (
    AttributeMerger,
    Merger,
    OneToManyMerger,
    OneToOneMerger,
)
from cl.search.docket_sources import DocketSources
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import (
    Court,
    Docket,
    DocketEntry,
    OriginatingCourtInformation,
)
from cl.tests.cases import TestCase


class BaseMergerTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()
        cls.docket = DocketFactory.create()

    def test_merger_creates_object(self) -> None:
        start_count = Docket.objects.count()

        class TestMerger(Merger[dict[str, str], Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = AttributeMerger(param=True, default=self.court)
            source: int = AttributeMerger(
                param=True, default=DocketSources.SCRAPER
            )
            docket_number: str = AttributeMerger(param=True, default="ABCDEFG")

            def query(self):
                return Docket.objects.none()

        r = TestMerger({}).merge()

        self.assertEqual(
            Docket.objects.count(),
            start_count + 1,
            "Docket should be created when it doesn't exist.",
        )
        self.assertEqual(r.success, True, "Merger should signal success.")
        self.assertEqual(
            r.create, True, "Merger should signal object was created."
        )
        self.assertEqual(
            r.update, False, "Merger should not signal object was updated."
        )
        self.assertEqual(
            ["Docket"], list(r.creates), "Merger should only create a Docket."
        )
        self.assertEqual(
            len(r.creates["Docket"]),
            1,
            "Exactly one Docket should be created.",
        )
        created_docket = Docket.objects.get(pk=r.creates["Docket"].pop())
        self.assertEqual(created_docket.docket_number, "ABCDEFG")
        self.assertEqual(created_docket.court_id, self.court.id)
        self.assertEqual(created_docket.source, DocketSources.SCRAPER)

    def test_merger_updates_docket(self) -> None:
        tc = self
        dn = self.docket.docket_number
        new_dn = dn + "New"
        start_docket_count = Docket.objects.count()

        class TestMerger(Merger[dict[str, str], Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = AttributeMerger(param=True, default=self.court)
            source: int = AttributeMerger(
                param=True, default=DocketSources.SCRAPER
            )
            docket_number: str = AttributeMerger(param=True, default=new_dn)

            def query(self):
                return Docket.objects.filter(pk=tc.docket.pk)

        r = TestMerger({}).merge()

        self.assertEqual(
            Docket.objects.count(),
            start_docket_count,
            "Docket should not be created when it exists.",
        )
        self.assertEqual(r.success, True, "Merger should signal success.")
        self.assertEqual(
            r.create, False, "Merger should not signal object was created."
        )
        self.assertEqual(
            r.update, True, "Merger should signal object was updated."
        )
        self.assertEqual(
            ["Docket"], list(r.updates), "Merger should only update a Docket."
        )
        self.assertEqual(
            len(r.updates["Docket"]),
            1,
            "Exactly one Docket should be updated.",
        )
        updated_pk = r.updates["Docket"].pop()
        self.assertEqual(
            updated_pk, self.docket.pk, "The correct Docket should be updated."
        )
        self.docket.refresh_from_db()
        self.assertEqual(
            self.docket.docket_number,
            new_dn,
            "The correct Docket should be updated.",
        )
        self.assertEqual(
            self.docket.source,
            DocketSources.SCRAPER,
        )
        self.assertEqual(
            self.docket.court_id,
            self.court.id,
        )

    def test_mappings_called(self) -> None:
        map_calls = 0
        dn = "ABCDEFG"

        def test_mapping(i: dict[str, str], *args: Any, **kwargs: Any) -> str:
            nonlocal map_calls
            map_calls += 1
            return dn

        class TestMerger(Merger[dict[str, str], Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = AttributeMerger(param=True, default=self.court)
            source: int = AttributeMerger(
                param=True, default=DocketSources.SCRAPER
            )
            docket_number: str = AttributeMerger(test_mapping)

            def query(self):
                return Docket.objects.none()

        r = TestMerger({}).merge()
        self.assertEqual(map_calls, 1)
        docket = Docket.objects.get(pk=r.creates["Docket"].pop())
        self.assertEqual(docket.docket_number, dn)

    def test_related_mergers_1to1(self) -> None:
        class TestRelatedMerger(
            Merger[dict[str, str], OriginatingCourtInformation]
        ):
            model: ClassVar[type[Model]] = OriginatingCourtInformation

            docket_number: str = AttributeMerger(lambda d: d["sr"])

            def query(self):
                return OriginatingCourtInformation.objects.none()

        class TestMerger(Merger[dict[str, Any], Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = AttributeMerger(param=True, default=self.court)
            source: int = AttributeMerger(
                param=True, default=DocketSources.SCRAPER
            )
            docket_number: str = AttributeMerger(
                param=True, default=self.docket.docket_number + "New"
            )
            originating_court_information: OriginatingCourtInformation = (
                OneToOneMerger(
                    TestRelatedMerger,
                    lambda d, *args, **kwargs: d["mctest"],
                )
            )

            def query(self):
                return Docket.objects.none()

        i = {"mctest": {"sr": "test"}}
        result = TestMerger(i).merge()

        self.assertIn("OriginatingCourtInformation", result.creates)
        self.assertEqual(len(result.creates["OriginatingCourtInformation"]), 1)
        oci_pk = result.creates["OriginatingCourtInformation"].pop()
        oci = OriginatingCourtInformation.objects.get(pk=oci_pk)
        self.assertEqual(oci.docket_number, i["mctest"]["sr"])
        self.assertEqual(oci.docket.pk, result.creates["Docket"].pop())

    def test_related_mergers_child(self) -> None:
        class TestRelatedMerger(Merger[dict[str, str], DocketEntry]):
            model: ClassVar[type[Model]] = DocketEntry

            description: str = AttributeMerger(lambda d: d["df"])

            def query(self):
                return DocketEntry.objects.none()

        class TestMerger(Merger[dict[str, Any], Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = AttributeMerger(param=True, default=self.court)
            source: int = AttributeMerger(
                param=True, default=DocketSources.SCRAPER
            )
            docket_number: str = AttributeMerger(
                param=True, default=self.docket.docket_number + "New"
            )
            docket_entries: list[DocketEntry] = OneToManyMerger[
                dict[str, Any], dict[str, Any], DocketEntry
            ](
                TestRelatedMerger,
                lambda d: d["mctest"],
            )

            def query(self):
                return Docket.objects.none()

        i = {
            "mctest": [
                {"df": "test1"},
                {"df": "test2"},
                {"df": "test3"},
            ]
        }
        result = TestMerger(i).merge()

        self.assertIn("DocketEntry", result.creates)
        self.assertEqual(len(result.creates["DocketEntry"]), 3)
        des = list(
            DocketEntry.objects.filter(pk__in=result.creates["DocketEntry"])
        )
        self.assertEqual(len(des), 3)
        self.assertEqual(
            set(de.description for de in des),
            set(mctest["df"] for mctest in i["mctest"]),
        )
        self.assertEqual(
            set(de.docket.pk for de in des), set(result.creates["Docket"])
        )

    def test_merger_subclassing(self) -> None:
        class TestMerger(Merger[dict[str, str], Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = AttributeMerger(param=True, default=self.court)
            source: int = AttributeMerger(
                param=True, default=DocketSources.SCRAPER
            )
            docket_number: str = AttributeMerger(param=True, default="ABCDEFG")

            def query(self):
                return Docket.objects.none()

        class TestMerger2(TestMerger):
            court: Court = AttributeMerger(param=True, default=self.court)
            docket_number: str = AttributeMerger(
                param=True, default="ABCDEFGH"
            )
            assigned_to_str: str = AttributeMerger(param=True)

        ats = "test"
        result = TestMerger2({}, assigned_to_str=ats).merge()

        self.assertIn("Docket", result.creates)
        self.assertEqual(len(result.creates["Docket"]), 1)
        docket = Docket.objects.get(pk=result.creates["Docket"].pop())
        self.assertEqual(docket.docket_number, "ABCDEFGH")
        self.assertEqual(docket.source, DocketSources.SCRAPER)
        self.assertEqual(docket.assigned_to_str, ats)
