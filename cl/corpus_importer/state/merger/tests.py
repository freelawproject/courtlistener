from collections.abc import Callable, Sequence
from typing import Any, ClassVar, cast, override

from django.db import connection
from django.db.models import Model, QuerySet
from django.db.models.signals import post_delete
from django.test.utils import CaptureQueriesContext

from cl.corpus_importer.state.common.docket import (
    DocketEntryRelation,
    PartyRelation,
)
from cl.corpus_importer.state.common.party import PartyMerger
from cl.corpus_importer.state.merger import (
    Constant,
    Fn,
    ManyStrategy,
    ManyToManyRelation,
    Merger,
    MergerConfig,
    MergerState,
    OneToManyRelation,
    OneToOneRelation,
    Params,
    RelatedParams,
    Scrape,
    ThroughParameters,
    Update,
)
from cl.corpus_importer.state.merger.specifications import AttributeMerger
from cl.people_db.factories import PersonFactory
from cl.people_db.models import Party, PartyType, Person
from cl.search.docket_sources import DocketSources
from cl.search.factories import (
    CourtFactory,
    DocketEntryFactory,
    DocketFactory,
)
from cl.search.models import (
    Court,
    Docket,
    DocketEntry,
    OriginatingCourtInformation,
    TrialCourtData,
)
from cl.tests.cases import SimpleTestCase, TestCase


def merger_test[**P, R](
    *, expected_query_count: int | range | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(f: Callable[P, R]) -> Callable[P, R]:
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            counts = {"merger": 0, "test": 0}
            merger_sql: list[str] = []
            merge_depth = 0

            original_merge = Merger.merge

            def counting_merge(merger_self: Any) -> Any:
                nonlocal merge_depth
                merge_depth += 1
                try:
                    return original_merge(merger_self)
                finally:
                    merge_depth -= 1

            def count_query(
                execute: Any, sql: Any, params: Any, many: Any, context: Any
            ) -> Any:
                # Skip savepoint bookkeeping from transaction.atomic(); it only
                # appears because tests already run inside a transaction.
                if not sql.startswith(("SAVEPOINT", "RELEASE", "ROLLBACK")):
                    if merge_depth:  # pyrefly:ignore[redundant-condition] See https://github.com/meta/pyrefly/issues/5563
                        counts["merger"] += 1
                        merger_sql.append(sql)
                    else:
                        counts["test"] += 1
                return execute(sql, params, many, context)

            Merger.merge = counting_merge  # type: ignore[method-assign, assignment]

            with connection.execute_wrapper(count_query):
                output = f(*args, **kwargs)

            if expected_query_count is not None:
                if isinstance(args[0], TestCase):
                    # It's okay if the query count is below the expect amount, but we still assert it isn't to force
                    # the expectation to be updated whenever performance is improved.
                    if isinstance(expected_query_count, int):
                        args[0].assertEqual(
                            counts["merger"],
                            expected_query_count,
                            "Merger query count should be equal to expectation.",
                        )
                    elif isinstance(expected_query_count, range):
                        args[0].assertIn(
                            counts["merger"],
                            expected_query_count,
                            "Merger query count should be in expected range.",
                        )

            return output

        return wrapper

    return decorator


DOCKET_SAVE_READS = (
    "case_name",
    "slug",
    "docket_number_raw",
    "docket_number_core",
)
"""The fields saving a docket that has a case name reads."""


class BaseMergerTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()
        cls.docket = DocketFactory.create()
        # pyrefly:ignore[bad-assignment]
        cls.docket_number: str = cls.docket.docket_number

    @merger_test(expected_query_count=1)
    def test_merger_creates_object(self) -> None:
        start_count = Docket.objects.count()

        class TestMerger(Merger[dict[str, str], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant("ABCDEFG")

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.none())

        r = TestMerger({}, params=None).merge()

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

    @merger_test(expected_query_count=2)
    def test_merger_updates_docket(self) -> None:
        tc = self
        new_dn = self.docket_number + "New"
        start_docket_count = Docket.objects.count()

        class TestMerger(Merger[dict[str, str], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, reads=DOCKET_SAVE_READS
            )

            court_id: str = Constant(self.court.id)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant(new_dn)

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.filter(pk=tc.docket.pk))

        r = TestMerger({}, params=None).merge()

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

    @merger_test(expected_query_count=1)
    def test_mappings_called(self) -> None:
        map_calls = 0
        dn = "ABCDEFG"

        def test_mapping(i: dict[str, str], params) -> str:
            nonlocal map_calls
            map_calls += 1
            return dn

        class TestMerger(Merger[dict[str, str], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Fn(test_mapping)(Scrape(dict), Params(Any))

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.none())

        r = TestMerger({}, params=None).merge()
        self.assertEqual(map_calls, 1)
        docket = Docket.objects.get(pk=r.creates["Docket"].pop())
        self.assertEqual(docket.docket_number, dn)

    @merger_test(expected_query_count=2)
    def test_related_mergers_1to1(self) -> None:
        class TestRelatedMerger(
            Merger[
                dict[str, str],
                RelatedParams[None],
                OriginatingCourtInformation,
            ]
        ):
            config: ClassVar[MergerConfig[OriginatingCourtInformation]] = (
                MergerConfig(model=OriginatingCourtInformation)
            )

            docket_number: str = Scrape(dict)["sr"]

            @classmethod
            def get_existing(
                cls, d: dict[str, str], manager, params: None
            ) -> OriginatingCourtInformation | None:
                return None

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant(self.docket_number + "New")
            originating_court_information: OriginatingCourtInformation = (
                OneToOneRelation(
                    TestRelatedMerger,
                    Scrape(dict)["mctest"],
                )
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.none())

        i = {"mctest": {"sr": "test"}}
        result = TestMerger(i, params=None).merge()

        self.assertIn("OriginatingCourtInformation", result.creates)
        self.assertEqual(len(result.creates["OriginatingCourtInformation"]), 1)
        oci_pk = result.creates["OriginatingCourtInformation"].pop()
        oci = OriginatingCourtInformation.objects.get(pk=oci_pk)
        self.assertEqual(oci.docket_number, i["mctest"]["sr"])
        self.assertEqual(oci.docket.pk, result.creates["Docket"].pop())

    @merger_test(expected_query_count=5)
    def test_related_mergers_reverse_1to1_creates(self) -> None:
        """Does a reverse one-to-one relation, where the OneToOneField lives on the child, create the child pointing at the parent? The child merger does not declare the foreign key; the relation sets it."""
        tc = self

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], TrialCourtData]
        ):
            config: ClassVar[MergerConfig[TrialCourtData]] = MergerConfig(
                model=TrialCourtData
            )

            docket_number_trial: str = Scrape(dict)["dn"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, reads=DOCKET_SAVE_READS
            )

            court: Court = Constant(tc.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str | None = Constant(tc.docket.docket_number)
            trialcourtdata: TrialCourtData = OneToOneRelation(
                TestRelatedMerger,
                Scrape(dict)["trial"],
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.filter(pk=tc.docket.pk))

        result = TestMerger({"trial": {"dn": "CR-123"}}, params=None).merge()

        self.assertTrue(result.success)
        self.assertIn("TrialCourtData", result.creates)
        self.docket.refresh_from_db()
        self.assertEqual(
            self.docket.trialcourtdata.docket_number_trial, "CR-123"
        )

    @merger_test(expected_query_count=5)
    def test_related_mergers_reverse_1to1_updates(self) -> None:
        """Does a reverse one-to-one relation update the row the parent already has instead of creating a second one?"""
        existing = TrialCourtData.objects.create(
            docket=self.docket, docket_number_trial="CR-000"
        )
        tc = self

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], TrialCourtData]
        ):
            config: ClassVar[MergerConfig[TrialCourtData]] = MergerConfig(
                model=TrialCourtData
            )

            docket_number_trial: str = Scrape(dict)["dn"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, reads=DOCKET_SAVE_READS
            )

            court: Court = Constant(tc.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str | None = Constant(tc.docket.docket_number)
            trialcourtdata: TrialCourtData = OneToOneRelation(
                TestRelatedMerger,
                Scrape(dict)["trial"],
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.filter(pk=tc.docket.pk))

        result = TestMerger({"trial": {"dn": "CR-999"}}, params=None).merge()

        self.assertTrue(result.success)
        self.assertNotIn("TrialCourtData", result.creates)
        self.assertEqual(TrialCourtData.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.docket_number_trial, "CR-999")

    def test_one_to_one_relation_must_be_a_one_to_one_field(self) -> None:
        """A one-to-one spec reads its direction off the model, so the field it names has to be one-to-one in the first place. Is a spec pointed at anything else refused when the merger is defined?"""

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], DocketEntry]
        ):
            config: ClassVar[MergerConfig[DocketEntry]] = MergerConfig(
                model=DocketEntry
            )

            description: str = Scrape(dict)["df"]

        with self.assertRaises(TypeError):

            class TestMerger(Merger[dict[str, Any], None, Docket]):
                config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                    model=Docket
                )

                docket_entries: list[DocketEntry] = OneToOneRelation(
                    TestRelatedMerger,
                    cast(AttributeMerger, Scrape(Any)),
                )

    @merger_test(expected_query_count=5)
    def test_related_mergers_child(self) -> None:
        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], DocketEntry]
        ):
            config: ClassVar[MergerConfig[DocketEntry]] = MergerConfig(
                model=DocketEntry
            )

            description: str = Scrape(dict)["df"]

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, DocketEntry]
            ) -> MergerState.LookupOutput[Any, Any, DocketEntry]:
                return state.resolve(DocketEntry.objects.none())

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant(self.docket_number + "New")
            docket_entries: list[DocketEntry] = OneToManyRelation(
                TestRelatedMerger,
                Scrape(dict)["mctest"],
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.none())

        i = {
            "mctest": [
                {"df": "test1"},
                {"df": "test2"},
                {"df": "test3"},
            ]
        }
        result = TestMerger(i, params=None).merge()

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

    @merger_test(expected_query_count=8)
    def test_related_mergers_m2m_simple(self) -> None:
        """Does a plain (no-through) many-to-many relation create the targets and link them to the parent? Uses batched candidate lookups so the bulk-linking path is exercised."""

        class TestPersonMerger(
            Merger[dict[str, str], RelatedParams[None], Person]
        ):
            config: ClassVar[MergerConfig[Person]] = MergerConfig(
                model=Person, key=("slug",)
            )

            name_first: str = Scrape(dict)["first"]
            name_last: str = Scrape(dict)["last"]
            slug: str = Scrape(dict)["slug"]

            @classmethod
            def candidates(
                cls, parent: Model, params: RelatedParams[None]
            ) -> QuerySet[Person]:
                return Person.objects.filter(empanelled_dockets=parent)

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant("M2M-SIMPLE")
            panel: list[Person] = ManyToManyRelation(
                TestPersonMerger,
                Scrape(dict)["panel"],
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.none())

        i = {
            "panel": [
                {"first": "Jane", "last": "Doe", "slug": "jane-doe-m2m"},
                {"first": "John", "last": "Roe", "slug": "john-roe-m2m"},
            ]
        }
        result = TestMerger(i, params=None).merge()

        self.assertIn("Person", result.creates)
        self.assertEqual(len(result.creates["Person"]), 2)
        docket = Docket.objects.get(pk=result.creates["Docket"].pop())
        self.assertEqual(
            set(docket.panel.values_list("name_last", flat=True)),
            {"Doe", "Roe"},
        )

    @merger_test(expected_query_count=8)
    def test_related_mergers_m2m_through(self) -> None:
        """Does a many-to-many relation with a `through` model create the targets, link them to the parent, and populate the through row's own fields from the same scrape?"""

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            config: ClassVar[MergerConfig[Party]] = MergerConfig(
                model=Party, key=("name",)
            )

            name: str = Scrape(dict)["name"]

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            config: ClassVar[MergerConfig[PartyType]] = MergerConfig(
                model=PartyType, key=("name",)
            )

            name: str = Scrape(dict)["type"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant("M2M-THROUGH")
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                Scrape(dict)["parties"],
                TestPartyTypeMerger,
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.none())

        i = {
            "parties": [
                {"name": "Alice", "type": "Plaintiff"},
                {"name": "Bob", "type": "Defendant"},
            ]
        }
        result = TestMerger(i, params=None).merge()

        self.assertIn("Party", result.creates)
        self.assertEqual(len(result.creates["Party"]), 2)
        self.assertIn("PartyType", result.creates)
        self.assertEqual(len(result.creates["PartyType"]), 2)

        docket = Docket.objects.get(pk=result.creates["Docket"].pop())
        self.assertEqual(
            set(docket.parties.values_list("name", flat=True)),
            {"Alice", "Bob"},
        )
        self.assertEqual(
            {
                (pt.party.name, pt.name)
                for pt in PartyType.objects.filter(docket=docket)
            },
            {("Alice", "Plaintiff"), ("Bob", "Defendant")},
        )

    def test_m2m_through_merger_must_match_through_model(self) -> None:
        """Is a `through` merger for the wrong model refused?

        A many-to-many spec whose `through` merger targets a model other than
        the relation's actual through model should fail when the merger is
        defined, with an error naming the mismatch.
        """

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            config: ClassVar[MergerConfig[Party]] = MergerConfig(model=Party)

            name: str = Scrape(dict)["name"]

        class TestWrongThroughMerger(
            Merger[dict[str, str], ThroughParameters[None], DocketEntry]
        ):
            config: ClassVar[MergerConfig[DocketEntry]] = MergerConfig(
                model=DocketEntry
            )

            description: str = Scrape(dict)["type"]

        with self.assertRaisesRegex(
            TypeError, "parties: Model for through merger is DocketEntry"
        ):

            class TestMerger(Merger[dict[str, Any], None, Docket]):
                config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                    model=Docket
                )

                parties: list[Party] = ManyToManyRelation(
                    TestPartyMerger,
                    Scrape(dict)["parties"],
                    TestWrongThroughMerger,
                )

    @merger_test(expected_query_count=9)
    def test_related_mergers_m2m_simple_disassociate(self) -> None:
        """Does DISASSOCIATE on a plain many-to-many remove stale associations while keeping the objects themselves?"""
        stale = PersonFactory.create()
        self.docket.panel.add(stale)
        tc = self

        class TestPersonMerger(
            Merger[dict[str, str], RelatedParams[None], Person]
        ):
            config: ClassVar[MergerConfig[Person]] = MergerConfig(
                model=Person, key=("slug",)
            )

            name_first: str = Scrape(dict)["first"]
            name_last: str = Scrape(dict)["last"]
            slug: str = Scrape(dict)["slug"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            panel: list[Person] = ManyToManyRelation(
                TestPersonMerger,
                Scrape(dict)["panel"],
                strategy=ManyStrategy.DISASSOCIATE,
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.filter(pk=tc.docket.pk))

        i = {
            "panel": [
                {"first": "Jane", "last": "Doe", "slug": "jane-doe-dis"},
            ]
        }
        result = TestMerger(i, params=None).merge()

        self.assertTrue(result.success)
        self.docket.refresh_from_db()
        self.assertTrue(
            Person.objects.filter(pk=stale.pk).exists(),
            "DISASSOCIATE must not delete the stale person.",
        )
        self.assertEqual(
            set(self.docket.panel.values_list("name_last", flat=True)),
            {"Doe"},
            "The stale association should be removed.",
        )

    @merger_test(expected_query_count=10)
    def test_related_mergers_m2m_through_disassociate(self) -> None:
        """Does DISASSOCIATE on a through many-to-many prune the stale through rows while keeping the related objects themselves?"""
        stale_party = Party.objects.create(name="Stale Party")
        PartyType.objects.create(
            docket=self.docket, party=stale_party, name="Plaintiff"
        )
        tc = self

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            config: ClassVar[MergerConfig[Party]] = MergerConfig(
                model=Party, key=("name",)
            )

            name: str = Scrape(dict)["name"]

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            config: ClassVar[MergerConfig[PartyType]] = MergerConfig(
                model=PartyType
            )

            name: str = Scrape(dict)["type"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                Scrape(dict)["parties"],
                TestPartyTypeMerger,
                strategy=ManyStrategy.DISASSOCIATE,
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.filter(pk=tc.docket.pk))

        i = {"parties": [{"name": "Alice", "type": "Plaintiff"}]}
        result = TestMerger(i, params=None).merge()

        self.assertTrue(result.success)
        self.docket.refresh_from_db()
        self.assertTrue(
            Party.objects.filter(pk=stale_party.pk).exists(),
            "DISASSOCIATE must not delete the stale party itself.",
        )
        self.assertFalse(
            PartyType.objects.filter(
                docket=self.docket, party=stale_party
            ).exists(),
            "The stale party's link to the docket should be removed.",
        )
        self.assertEqual(
            set(self.docket.parties.values_list("name", flat=True)),
            {"Alice"},
        )

    @merger_test(expected_query_count=15)
    def test_related_mergers_m2m_through_replace_deletes(self) -> None:
        """Characterization: does REPLACE on a through many-to-many delete the stale related objects outright?"""
        stale_party = Party.objects.create(name="Stale Party")
        PartyType.objects.create(
            docket=self.docket, party=stale_party, name="Plaintiff"
        )
        tc = self

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            config: ClassVar[MergerConfig[Party]] = MergerConfig(
                model=Party, key=("name",)
            )

            name: str = Scrape(dict)["name"]

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            config: ClassVar[MergerConfig[PartyType]] = MergerConfig(
                model=PartyType
            )

            name: str = Scrape(dict)["type"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                Scrape(dict)["parties"],
                TestPartyTypeMerger,
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.filter(pk=tc.docket.pk))

        i = {"parties": [{"name": "Alice", "type": "Plaintiff"}]}
        result = TestMerger(i, params=None).merge()

        self.assertTrue(result.success)
        self.assertFalse(
            Party.objects.filter(pk=stale_party.pk).exists(),
            "REPLACE deletes stale related objects outright.",
        )

    @merger_test(expected_query_count=4)
    def test_related_mergers_child_replace_keeps_rows_on_invalid_child(
        self,
    ) -> None:
        """Does REPLACE leave existing rows alone when a child's input is invalid? The child gives up before looking anything up, so the row it would have matched isn't known and can't be pruned safely."""
        stale = DocketEntry.objects.create(
            docket=self.docket, description="Stale"
        )
        tc = self

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], DocketEntry]
        ):
            config: ClassVar[MergerConfig[DocketEntry]] = MergerConfig(
                model=DocketEntry, key=("description",)
            )

            description: str = Scrape(dict)["df"]

            @staticmethod
            def validator(scrape: dict[str, str]) -> bool:
                return scrape["df"] != "Invalid"

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            docket_entries: list[DocketEntry] = OneToManyRelation(
                TestRelatedMerger,
                Scrape(dict)["entries"],
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.filter(pk=tc.docket.pk))

        i = {"entries": [{"df": "Fresh"}, {"df": "Invalid"}]}
        result = TestMerger(i, params=None).merge()

        self.assertFalse(result.success)
        self.assertTrue(
            DocketEntry.objects.filter(pk=stale.pk).exists(),
            "A failed child merge must not let REPLACE delete existing rows.",
        )
        self.assertEqual(
            set(
                self.docket.docket_entries.values_list(
                    "description", flat=True
                )
            ),
            {"Stale", "Fresh"},
        )

    @merger_test(expected_query_count=3)
    def test_related_mergers_m2m_replace_keeps_rows_on_ambiguous_child(
        self,
    ) -> None:
        """Does REPLACE leave existing rows alone when a child's lookup matches several rows? The merger can't pick one, so it never learns which row belongs to this scrape."""
        stale_party = Party.objects.create(name="Stale Party")
        PartyType.objects.create(
            docket=self.docket, party=stale_party, name="Plaintiff"
        )
        Party.objects.create(name="Ambiguous")
        Party.objects.create(name="Ambiguous")
        tc = self

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            config: ClassVar[MergerConfig[Party]] = MergerConfig(
                model=Party, key=("name",)
            )

            name: str = Scrape(dict)["name"]

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            config: ClassVar[MergerConfig[PartyType]] = MergerConfig(
                model=PartyType
            )

            name: str = Scrape(dict)["type"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                Scrape(dict)["parties"],
                TestPartyTypeMerger,
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.filter(pk=tc.docket.pk))

        i = {"parties": [{"name": "Ambiguous", "type": "Plaintiff"}]}
        result = TestMerger(i, params=None).merge()

        self.assertFalse(result.success)
        self.assertTrue(
            Party.objects.filter(pk=stale_party.pk).exists(),
            "An ambiguous child lookup must not let REPLACE delete existing "
            "rows.",
        )
        self.assertTrue(
            PartyType.objects.filter(
                docket=self.docket, party=stale_party
            ).exists(),
            "An ambiguous child lookup must not let REPLACE prune existing "
            "through rows.",
        )

    @merger_test(expected_query_count=1)
    def test_merger_subclassing(self) -> None:
        class TestMerger(Merger[dict[str, str], dict[str, Any], Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(self.court)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Constant("ABCDEFG")

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.none())

        class TestMerger2(TestMerger):
            court: Court = Constant(self.court)
            docket_number: str = Constant("ABCDEFGH")
            assigned_to_str: str = Params(dict)["assigned_to_str"]

        ats = "test"
        result = TestMerger2({}, params={"assigned_to_str": ats}).merge()

        self.assertIn("Docket", result.creates)
        self.assertEqual(len(result.creates["Docket"]), 1)
        docket = Docket.objects.get(pk=result.creates["Docket"].pop())
        self.assertEqual(docket.docket_number, "ABCDEFGH")
        self.assertEqual(docket.source, DocketSources.SCRAPER)
        self.assertEqual(docket.assigned_to_str, ats)


class KeyedEntryMerger(Merger[dict[str, str], Any, DocketEntry]):
    """A docket entry found by its description among its docket's entries."""

    config: ClassVar[MergerConfig[DocketEntry]] = MergerConfig(
        model=DocketEntry, key=("description",)
    )

    description: str = Scrape(dict)["description"]


class KeyedDocketMerger(Merger[dict[str, Any], Any, Docket]):
    """A docket found by its docket number, with its entries."""

    config: ClassVar[MergerConfig[Docket]] = MergerConfig(
        model=Docket, key=("docket_number",)
    )

    docket_number: str = Scrape(dict)["docket_number"]
    source: int = Constant(DocketSources.SCRAPER)
    docket_entries: list[DocketEntry] = OneToManyRelation(
        KeyedEntryMerger,
        Scrape(dict)["entries"],
    )


class KeyedCourtMerger(Merger[dict[str, Any], None, Court]):
    """A court found by its ID, with its dockets."""

    config: ClassVar[MergerConfig[Court]] = MergerConfig(
        model=Court, key=("id",)
    )

    id: str = Scrape(dict)["id"]
    dockets: list[Docket] = OneToManyRelation(
        KeyedDocketMerger,
        Scrape(dict)["dockets"],
    )


class SiblingLookupTest(TestCase):
    """How mergers created together find the objects they merge into."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()
        cls.dockets = [
            DocketFactory.create(
                court=cls.court,
                source=DocketSources.SCRAPER,
                docket_number=f"SIBLING-{n}",
            )
            for n in range(2)
        ]
        for docket in cls.dockets:
            for description in ("First", "Second"):
                DocketEntryFactory.create(
                    docket=docket, description=description
                )

    def scrape(self, docket: Docket, *descriptions: str) -> dict[str, Any]:
        """The scrape of a docket holding entries with these descriptions."""
        return {
            "docket_number": docket.docket_number,
            "entries": [{"description": d} for d in descriptions],
        }

    @merger_test(expected_query_count=2)
    def test_siblings_are_looked_up_together(self) -> None:
        """Do sibling mergers share one lookup query, with nothing more to do when the scrape matches the DB? One query finds the docket and one its entries."""
        result = KeyedDocketMerger(
            self.scrape(self.dockets[0], "First", "Second"), params=None
        ).merge()

        self.assertTrue(result.success, result.failures)
        self.assertFalse(result.create)
        self.assertFalse(result.update)

    @merger_test(expected_query_count=3)
    def test_children_are_fetched_for_every_parent_at_once(self) -> None:
        """Does one query fetch the children of every sibling parent? One query finds the court, one its dockets and one all of their entries."""
        result = KeyedCourtMerger(
            {
                "id": self.court.pk,
                "dockets": [
                    self.scrape(docket, "First", "Second")
                    for docket in self.dockets
                ],
            },
            params=None,
        ).merge()

        self.assertTrue(result.success, result.failures)
        self.assertFalse(result.create)
        self.assertFalse(result.update)

    def test_replace_prunes_rows_missing_from_the_scrape(self) -> None:
        """Does REPLACE delete exactly the rows the scrape no longer has, keeping those matched and those created along the way?"""
        docket = self.dockets[0]
        result = KeyedDocketMerger(
            self.scrape(docket, "First", "Third"), params=None
        ).merge()

        self.assertTrue(result.success, result.failures)
        self.assertEqual(
            sorted(
                docket.docket_entries.values_list("description", flat=True)
            ),
            ["First", "Third"],
        )
        self.assertEqual(
            sorted(
                self.dockets[1].docket_entries.values_list(
                    "description", flat=True
                )
            ),
            ["First", "Second"],
            "Another parent's rows are out of scope.",
        )

    def test_duplicate_natural_keys_fail_once(self) -> None:
        """Is a scrape repeating a natural key reported as a single failure, with the last duplicate merged and no row pruned?"""
        docket = self.dockets[0]
        result = KeyedDocketMerger(
            self.scrape(docket, "Third", "Third"), params=None
        ).merge()

        self.assertEqual(result.failures, {"DocketEntry": [None]})
        self.assertEqual(len(result.creates["DocketEntry"]), 1)
        self.assertEqual(
            sorted(
                docket.docket_entries.values_list("description", flat=True)
            ),
            ["First", "Second", "Third"],
        )


class LoadedFieldsTest(TestCase):
    """Which fields a merger loads of the objects it merges into."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()
        cls.docket = DocketFactory.create(
            court=cls.court,
            source=DocketSources.SCRAPER,
            docket_number="LOADED-1",
        )
        for description in ("First", "Second"):
            DocketEntryFactory.create(
                docket=cls.docket, description=description
            )
        cls.scrape = {
            "docket_number": cls.docket.docket_number,
            "entries": [{"description": "First"}, {"description": "Second"}],
        }

    def merged(self, merger: Merger[Any, Any, Any]) -> Any:
        """Run a merge that is expected to succeed.

        :return: The object merged into.
        """
        merger.merge()
        state = merger.state
        if not isinstance(state, MergerState.Complete):
            self.fail(f"The merge did not complete: {state}")
        return state.output

    def test_lookup_loads_only_used_fields(self) -> None:
        """Does a lookup leave out the fields no spec uses, both of the objects it finds and of the related objects it loads with them?"""
        court = self.merged(
            KeyedCourtMerger(
                {"id": self.court.pk, "dockets": [self.scrape]}, params=None
            )
        )
        [docket] = court.dockets.all()
        entries = docket.docket_entries.all()

        self.assertIn("full_name", court.get_deferred_fields())
        self.assertIn("case_name", docket.get_deferred_fields())
        self.assertNotIn("docket_number", docket.get_deferred_fields())
        self.assertEqual(len(entries), 2)
        for entry in entries:
            self.assertIn("entry_number", entry.get_deferred_fields())
            self.assertNotIn("description", entry.get_deferred_fields())

    def test_relation_loads_only_used_fields(self) -> None:
        """Are the objects a parent holds read without the fields no spec uses, in a single query?"""
        merger = KeyedDocketMerger(
            self.scrape, params=None, existing=Update(self.docket)
        )
        with CaptureQueriesContext(connection) as queries:
            merger.merge()

        self.assertEqual(len(queries), 1, queries.captured_queries)
        selected = queries[0]["sql"].partition(" FROM ")[0]
        self.assertIn('"description"', selected)
        self.assertNotIn('"entry_number"', selected)

    def test_one_to_one_loads_only_used_fields(self) -> None:
        """Is the object on the other side of a one-to-one relation read without the fields no spec uses?"""
        origin = OriginatingCourtInformation.objects.create(
            docket_number="ORIGIN-1"
        )
        self.docket.originating_court_information = origin
        self.docket.save()

        class OriginMerger(
            Merger[dict[str, str], Any, OriginatingCourtInformation]
        ):
            config: ClassVar[MergerConfig[OriginatingCourtInformation]] = (
                MergerConfig(model=OriginatingCourtInformation)
            )

            docket_number: str = Scrape(dict)["docket_number"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            docket_number: str = Scrape(dict)["docket_number"]
            originating_court_information: OriginatingCourtInformation = (
                OneToOneRelation(OriginMerger, Scrape(dict)["origin"])
            )

        docket = Docket.objects.get(pk=self.docket.pk)
        self.merged(
            TestMerger(
                {
                    "docket_number": docket.docket_number,
                    "origin": {"docket_number": "ORIGIN-1"},
                },
                params=None,
                existing=Update(docket),
            )
        )

        loaded = docket.originating_court_information
        if loaded is None:
            self.fail("The docket lost its originating court information.")
        self.assertIn("court_reporter", loaded.get_deferred_fields())
        self.assertNotIn("docket_number", loaded.get_deferred_fields())

    def test_overridden_lookup_loads_only_used_fields(self) -> None:
        """Are the candidates of a lookup that runs its own query read without the fields no spec uses?"""

        class TestMerger(KeyedDocketMerger):
            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(
                    Docket.objects.filter(docket_number=self.docket_number)
                )

        docket = self.merged(TestMerger(self.scrape, params=None))

        self.assertEqual(docket.pk, self.docket.pk)
        self.assertIn("case_name", docket.get_deferred_fields())
        self.assertNotIn("docket_number", docket.get_deferred_fields())

    def test_stored_loads_only_used_fields(self) -> None:
        """Does a query a merger builds for itself leave out the fields no spec uses?"""
        docket = KeyedDocketMerger(self.scrape, params=None).stored.get()

        self.assertIn("case_name", docket.get_deferred_fields())
        self.assertNotIn("docket_number", docket.get_deferred_fields())

    def test_pruned_objects_are_deleted_whole(self) -> None:
        """Does a deletion signal get every field of a pruned object, though the lookup that found it loaded only some?"""
        deferred: list[set[str]] = []

        def record(instance: DocketEntry, **kwargs: Any) -> None:
            """Note which fields a deleted entry was loaded without."""
            deferred.append(instance.get_deferred_fields())

        post_delete.connect(record, sender=DocketEntry)
        self.addCleanup(post_delete.disconnect, record, sender=DocketEntry)

        self.merged(
            KeyedDocketMerger(
                self.scrape | {"entries": [{"description": "First"}]},
                params=None,
            )
        )

        self.assertEqual(deferred, [set()])

    def test_declared_reads_are_loaded(self) -> None:
        """Is a field a merger says it reads loaded although no spec uses it?"""

        class TestMerger(KeyedDocketMerger):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, key=("docket_number",), reads=("case_name",)
            )

        docket = self.merged(TestMerger(self.scrape, params=None))

        self.assertNotIn("case_name", docket.get_deferred_fields())
        self.assertIn("case_name_full", docket.get_deferred_fields())

    def test_reads_extend_inherited_reads(self) -> None:
        """Does a merger that declares reads of its own still load the ones its parent declared?"""

        class ParentMerger(KeyedDocketMerger):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, key=("docket_number",), reads=("case_name",)
            )

        class ChildMerger(ParentMerger):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, key=("docket_number",), reads=("slug",)
            )

        docket = self.merged(ChildMerger(self.scrape, params=None))

        self.assertNotIn("case_name", docket.get_deferred_fields())
        self.assertNotIn("slug", docket.get_deferred_fields())


class EntryMerger(Merger[dict[str, str], Any, DocketEntry]):
    """A minimal child merger for exercising related specs on `Docket`."""

    config: ClassVar[MergerConfig[DocketEntry]] = MergerConfig(
        model=DocketEntry
    )


class MergerSpecOrderTest(SimpleTestCase):
    def test_after_orders_related_specs_regardless_of_declaration(
        self,
    ) -> None:
        """Does a spec run after the specs it names in `after`, even when it is declared first?"""

        class TestMerger(Merger[dict[str, str], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            docket_entries: list[DocketEntry] = DocketEntryRelation(
                EntryMerger
            )
            parties: Sequence[Party] = PartyRelation()

        self.assertEqual(
            [spec._name for spec in TestMerger.config.registry.merge_order],
            ["parties", "docket_entries"],
        )

    def test_after_unknown_spec_is_a_validation_error(self) -> None:
        """Is a dependency on a spec the merger doesn't have reported rather than silently ignored?"""
        with self.assertRaisesRegex(
            TypeError,
            "docket_entries: Runs after unknown related spec parties",
        ):

            class TestMerger(Merger[dict[str, str], None, Docket]):
                config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                    model=Docket
                )

                docket_entries: list[DocketEntry] = DocketEntryRelation(
                    EntryMerger
                )

    def test_after_cycle_is_rejected(self) -> None:
        """Are circular dependencies between related specs refused when the merger is defined, rather than when it first merges?"""
        with self.assertRaisesRegex(TypeError, "CycleError"):

            class TestMerger(Merger[dict[str, str], None, Docket]):
                config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                    model=Docket
                )

                docket_entries: list[DocketEntry] = OneToManyRelation(
                    EntryMerger, Scrape(dict)["entries"], after=["parties"]
                )
                parties: list[Party] = ManyToManyRelation(
                    PartyMerger,
                    Scrape(dict)["parties"],
                    after=["docket_entries"],
                )


class MergerConfigInheritanceTest(SimpleTestCase):
    def test_declared_config_keeps_inherited_specs(self) -> None:
        """Does a subclass that declares its own config still merge the specs its base declared, without leaking its own specs into the base?"""

        class BaseTestMerger(
            Merger[dict[str, str], None, Docket], abstract=True
        ):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            case_name: str = Constant("")

        class TestMerger(BaseTestMerger):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, key=("docket_number",)
            )

            docket_number: str = Constant("")

        self.assertEqual(
            set(TestMerger.config.registry.attr),
            {"case_name", "docket_number"},
        )
        self.assertEqual(TestMerger.config.key, ("docket_number",))

    def test_undeclared_config_inherits_base_config(self) -> None:
        """Does a subclass that doesn't declare a config inherit its base's model and key?"""

        class BaseTestMerger(Merger[dict[str, str], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, key=("docket_number",)
            )

            docket_number: str = Constant("")

        class TestMerger(BaseTestMerger):
            case_name: str = Constant("")

        self.assertIs(TestMerger.config.model, Docket)
        self.assertEqual(TestMerger.config.key, ("docket_number",))
        self.assertEqual(
            set(TestMerger.config.registry.attr),
            {"case_name", "docket_number"},
        )
        self.assertEqual(
            set(BaseTestMerger.config.registry.attr), {"docket_number"}
        )
