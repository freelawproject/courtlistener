# from typing import Annotated, override
#
# from cl.corpus_importer.state.merger import InputField, Merger
# from cl.corpus_importer.state.utils import MergeResult
# from cl.search.docket_sources import DocketSources
# from cl.search.models import Docket
#
#
# class TestMerger(Merger[dict[str, str], Docket]):
#     source = DocketSources.SCRAPER
#     docket_number: Annotated[str, InputField("testy_pie")]
#
#     @override
#     def validate_input(self, i: dict[str, str]) -> bool:
#         return True
#
#     @override
#     def after_merge(
#         self, i: dict[str, str], m: Docket, r: MergeResult[int]
#     ) -> None:
#         print(m.docket_number)
#
#     @override
#     def find_existing(self, i: dict[str, str]) -> Docket | None:
#         return None
#
#
# m = TestMerger()
# m.merge({"testy_pie": "aaaaaa"})
from typing import Annotated, Any, override

from cl.corpus_importer.state.merger import (
    AttributeMerger,
    InputField,
    InputMap,
    Merger,
    Parameter,
    RelatedMerger,
    Relationship,
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
    @override
    def setUpTestData(cls) -> None:
        cls.court: Court = CourtFactory.create()
        cls.docket: Docket = DocketFactory.create()

    def test_merger_creates_object(self) -> None:
        start_count = Docket.objects.count()

        class TestMerger(Merger[dict[str, str], Docket]):
            court: Annotated[Court, AttributeMerger(Parameter)] = self.court
            source: Annotated[int, AttributeMerger(Parameter)] = (
                DocketSources.SCRAPER
            )
            docket_number: Annotated[str, AttributeMerger(Parameter)] = (
                "ABCDEFG"
            )

            @staticmethod
            def existing(i: Docket) -> Docket | None:
                return None

        r = TestMerger.merge({})

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
        self.assertEqual(
            created_docket.docket_number, TestMerger.docket_number
        )
        self.assertEqual(created_docket.court_id, self.court.id)
        self.assertEqual(created_docket.source, TestMerger.source)

    def test_merger_updates_docket(self) -> None:
        tc = self
        start_docket_count = Docket.objects.count()

        class TestMerger(Merger[dict[str, str], Docket]):
            court: Annotated[Court, AttributeMerger(Parameter)] = self.court
            source: Annotated[int, AttributeMerger(Parameter)] = (
                DocketSources.SCRAPER
            )
            docket_number: Annotated[str, AttributeMerger(Parameter)] = (
                self.docket.docket_number + "New"
            )

            @staticmethod
            def existing(i: Docket) -> Docket | None:
                return tc.docket

        r = TestMerger.merge({})

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
            TestMerger.docket_number,
            "The correct Docket should be updated.",
        )
        self.assertEqual(
            self.docket.source,
            TestMerger.source,
        )
        self.assertEqual(
            self.docket.court_id,
            self.court.id,
        )

    def test_mappings_called(self) -> None:
        map_calls = 0
        dn = "ABCDEFG"

        class TestMapping(InputMap[dict[str, str], str]):
            @override
            def map(self, i: dict[str, str]) -> str:
                nonlocal map_calls
                map_calls += 1
                return dn

        class TestMerger(Merger[dict[str, str], Docket]):
            court: Annotated[Court, AttributeMerger(Parameter)] = self.court
            source: Annotated[int, AttributeMerger(Parameter)] = (
                DocketSources.SCRAPER
            )
            docket_number: Annotated[str, AttributeMerger(TestMapping())] = (
                "ABCDEFG"
            )

            @staticmethod
            def existing(i: Docket) -> Docket | None:
                return None

        r = TestMerger.merge({})
        self.assertEqual(map_calls, 1)
        docket = Docket.objects.get(pk=r.creates["Docket"].pop())
        self.assertEqual(docket.docket_number, dn)

    def test_related_mergers_1to1(self) -> None:
        class TestRelatedMerger(
            Merger[dict[str, str], OriginatingCourtInformation]
        ):
            docket_number: Annotated[str, AttributeMerger(InputField("sr"))]

            @staticmethod
            def existing(
                i: OriginatingCourtInformation,
            ) -> OriginatingCourtInformation | None:
                return None

        class TestMerger(Merger[dict[str, Any], Docket]):
            court: Annotated[Court, AttributeMerger(Parameter)] = self.court
            source: Annotated[int, AttributeMerger(Parameter)] = (
                DocketSources.SCRAPER
            )
            docket_number: Annotated[str, AttributeMerger(Parameter)] = (
                self.docket.docket_number + "New"
            )
            originating_court_information: Annotated[
                OriginatingCourtInformation,
                RelatedMerger(
                    TestRelatedMerger,
                    InputField("mctest"),
                    relationship=Relationship.OneToOne,
                ),
            ]

            @staticmethod
            def existing(i: Docket) -> Docket | None:
                return None

        i = {"mctest": {"sr": "test"}}
        result = TestMerger.merge(i)

        self.assertIn("OriginatingCourtInformation", result.creates)
        self.assertEqual(len(result.creates["OriginatingCourtInformation"]), 1)
        oci_pk = result.creates["OriginatingCourtInformation"].pop()
        oci = OriginatingCourtInformation.objects.get(pk=oci_pk)
        self.assertEqual(oci.docket_number, i["mctest"]["sr"])
        self.assertEqual(oci.docket.pk, result.creates["Docket"].pop())

    def test_related_mergers_child(self) -> None:
        class TestRelatedMerger(Merger[dict[str, str], DocketEntry]):
            docket: Annotated[Docket, AttributeMerger(Parameter)]
            description: Annotated[str, AttributeMerger(InputField("df"))]

            @staticmethod
            def existing(
                i: DocketEntry,
            ) -> DocketEntry | None:
                return None

        class TestMerger(Merger[dict[str, Any], Docket]):
            court: Annotated[Court, AttributeMerger(Parameter)] = self.court
            source: Annotated[int, AttributeMerger(Parameter)] = (
                DocketSources.SCRAPER
            )
            docket_number: Annotated[str, AttributeMerger(Parameter)] = (
                self.docket.docket_number + "New"
            )
            originating_court_information: Annotated[
                OriginatingCourtInformation,
                RelatedMerger(
                    TestRelatedMerger,
                    InputField("mctest"),
                    relationship=Relationship.Child("docket"),
                ),
            ]

            @staticmethod
            def existing(i: Docket) -> Docket | None:
                return None

        i = {
            "mctest": [
                {"df": "test1"},
                {"df": "test2"},
                {"df": "test3"},
            ]
        }
        result = TestMerger.merge(i)

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
