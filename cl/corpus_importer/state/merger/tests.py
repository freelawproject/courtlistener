import operator
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, ClassVar, cast, override

from django.db import connection, transaction
from django.db.models import F, Model, Q, QuerySet
from django.db.models.signals import post_delete
from django.test.utils import CaptureQueriesContext
from juriscraper.state.docket import Document as ScrapeDocument

from cl.corpus_importer.state.common.docket import (
    DocketEntryRelation,
    PartyRelation,
)
from cl.corpus_importer.state.common.party import PartyMerger
from cl.corpus_importer.state.merger import (
    Constant,
    Create,
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
from cl.corpus_importer.state.merger.match import (
    BoundNarrow,
    Fail,
    First,
    Key,
    Match,
    Narrow,
    Next,
)
from cl.corpus_importer.state.merger.pool import (
    Global,
    Relatives,
    Siblings,
    sort_rows,
)
from cl.corpus_importer.state.merger.specifications import (
    Ancestor,
    Annotation,
    Coalesce,
    Comparison,
    Database,
    Source,
)
from cl.corpus_importer.state.utils import MergeResult
from cl.people_db.factories import (
    PartyFactory,
    PartyTypeFactory,
    PersonFactory,
)
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


def merged_docket(result: MergeResult) -> Docket:
    """Fetch the docket a merge created; the merge must have created one."""
    return Docket.objects.get(pk=next(iter(result.creates["Docket"])))


@contextmanager
def table_row(test: TestCase, label: str) -> Iterator[None]:
    """Run one row of a case table as its own subtest, rolling back its database writes when it ends.

    Rows that merge the same docket or count rows of a table would otherwise
    see what an earlier row wrote.

    Args:
        test: The test running the table.
        label: The name the row is reported under.
    """
    with test.subTest(label), transaction.atomic():
        yield
        transaction.set_rollback(True)


DOCKET_SAVE_READS = (
    "case_name",
    "slug",
    "docket_number_raw",
    "docket_number_core",
)
"""The fields saving a docket that has a case name reads."""


class SluggedPersonMerger(Merger[dict[str, str], RelatedParams[None], Person]):
    """A person found by their slug."""

    config: ClassVar[MergerConfig[Person]] = MergerConfig(
        model=Person, key=("slug",)
    )

    name_first: str = Scrape(dict)["first"]
    name_last: str = Scrape(dict)["last"]
    slug: str = Scrape(dict)["slug"]


class NamedPartyMerger(Merger[dict[str, str], RelatedParams[None], Party]):
    """A party found by its name."""

    config: ClassVar[MergerConfig[Party]] = MergerConfig(
        model=Party, key=("name",)
    )

    name: str = Scrape(dict)["name"]


class PartyTypeMerger(
    Merger[dict[str, str], ThroughParameters[None], PartyType]
):
    """The type a party appears under on a docket."""

    config: ClassVar[MergerConfig[PartyType]] = MergerConfig(model=PartyType)

    name: str = Scrape(dict)["type"]


class BaseMergerTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()
        cls.docket = DocketFactory.create()
        # pyrefly:ignore[bad-assignment]
        cls.docket_number: str = cls.docket.docket_number

    def parties_merger(
        self, strategy: ManyStrategy = ManyStrategy.REPLACE
    ) -> type[Merger[dict[str, Any], None, Docket]]:
        """A merger of `self.docket` and the parties on it, each typed through `PartyType`."""
        docket = self.docket

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(docket.court)
            source: int = Constant(docket.source)
            docket_number: str | None = Constant(docket.docket_number)
            parties: list[Party] = ManyToManyRelation(
                NamedPartyMerger,
                Scrape(dict)["parties"],
                PartyTypeMerger,
                strategy=strategy,
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[Any, Any, Docket]
            ) -> MergerState.LookupOutput[Any, Any, Docket]:
                return state.resolve(Docket.objects.filter(pk=docket.pk))

        return TestMerger

    @merger_test(expected_query_count=1)
    def test_merger_creates_object(self) -> None:
        """Does a merger whose lookup finds nothing create the object from its specs, calling each mapping once?"""
        start_count = Docket.objects.count()
        map_calls = 0

        def test_mapping(i: dict[str, str], params: Any) -> str:
            nonlocal map_calls
            map_calls += 1
            return "ABCDEFG"

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
        self.assertEqual(map_calls, 1)
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

    @merger_test(expected_query_count=9)
    def test_related_mergers_reverse_1to1(self) -> None:
        """Does a reverse one-to-one relation, where the OneToOneField lives on the child, create the child pointing at the parent, then update that row on a later merge instead of creating a second one? The child merger does not declare the foreign key; the relation sets it."""
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
        created = TrialCourtData.objects.get(docket=self.docket)
        self.assertEqual(created.docket_number_trial, "CR-123")

        result = TestMerger({"trial": {"dn": "CR-999"}}, params=None).merge()

        self.assertTrue(result.success)
        self.assertNotIn("TrialCourtData", result.creates)
        self.assertEqual(TrialCourtData.objects.count(), 1)
        created.refresh_from_db()
        self.assertEqual(created.docket_number_trial, "CR-999")

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
                    Scrape(dict[str, str] | None),
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

        class TestPersonMerger(SluggedPersonMerger):
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

    @merger_test(expected_query_count=9)
    def test_related_mergers_m2m_through(self) -> None:
        """Does a many-to-many relation with a `through` model create the targets, link them to the parent, and populate the through row's own fields from the same scrape?"""
        i = {
            "parties": [
                {"name": "Alice", "type": "Plaintiff"},
                {"name": "Bob", "type": "Defendant"},
            ]
        }
        result = self.parties_merger()(i, params=None).merge()

        self.assertIn("Party", result.creates)
        self.assertEqual(len(result.creates["Party"]), 2)
        self.assertIn("PartyType", result.creates)
        self.assertEqual(len(result.creates["PartyType"]), 2)
        self.assertEqual(
            set(self.docket.parties.values_list("name", flat=True)),
            {"Alice", "Bob"},
        )
        self.assertEqual(
            {
                (pt.party.name, pt.name)
                for pt in PartyType.objects.filter(docket=self.docket)
            },
            {("Alice", "Plaintiff"), ("Bob", "Defendant")},
        )

    def test_m2m_through_merger_must_match_through_model(self) -> None:
        """Is a `through` merger for the wrong model refused?

        A many-to-many spec whose `through` merger targets a model other than
        the relation's actual through model should fail when the merger is
        defined, with an error naming the mismatch.
        """

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
                    NamedPartyMerger,
                    Scrape(dict)["parties"],
                    TestWrongThroughMerger,
                )

    @merger_test(expected_query_count=9)
    def test_related_mergers_m2m_simple_disassociate(self) -> None:
        """Does DISASSOCIATE on a plain many-to-many remove stale associations while keeping the objects themselves?"""
        stale = PersonFactory.create()
        self.docket.panel.add(stale)
        tc = self

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            court: Court = Constant(tc.docket.court)
            source: int = Constant(tc.docket.source)
            docket_number: str | None = Constant(tc.docket.docket_number)
            panel: list[Person] = ManyToManyRelation(
                SluggedPersonMerger,
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

    @merger_test(expected_query_count=23)
    def test_related_mergers_m2m_through_prunes_stale_rows(self) -> None:
        """Do DISASSOCIATE and REPLACE on a through many-to-many both prune the stale through rows, with DISASSOCIATE keeping the stale related object and REPLACE deleting it outright?"""
        cases = [
            ("disassociate", ManyStrategy.DISASSOCIATE, True),
            ("replace", ManyStrategy.REPLACE, False),
        ]
        for name, strategy, party_kept in cases:
            with self.subTest(name):
                stale_party = Party.objects.create(name=f"Stale {name}")
                PartyType.objects.create(
                    docket=self.docket, party=stale_party, name="Plaintiff"
                )

                result = self.parties_merger(strategy)(
                    {"parties": [{"name": "Alice", "type": "Plaintiff"}]},
                    params=None,
                ).merge()

                self.assertTrue(result.success)
                self.assertEqual(
                    Party.objects.filter(pk=stale_party.pk).exists(),
                    party_kept,
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

        i = {"parties": [{"name": "Ambiguous", "type": "Plaintiff"}]}
        result = self.parties_merger()(i, params=None).merge()

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


CASE_NAME = Docket.case_name
CASE_NAME_FULL = Docket.case_name_full


def _prefer_stored(stored: str | None, scraped: str) -> str:
    """Keep a stored value over a scraped one."""
    return stored or scraped


def _if_stored(stored: str | None, scraped: Any) -> Any:
    """Use a scraped value only when a value is already stored."""
    return scraped if stored else None


class DatabaseSpecTest(TestCase):
    """Specs that read the object being merged into."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()
        cls.docket = DocketFactory.create(
            court=cls.court,
            source=DocketSources.SCRAPER,
            docket_number="DB-1",
            case_name="Stored Name",
        )
        cls.blank_docket = DocketFactory.create(
            court=cls.court,
            source=DocketSources.SCRAPER,
            docket_number="DB-2",
            case_name="",
        )

    def merger(self) -> type[Merger[dict[str, str], None, Docket]]:
        """A docket merger keeping any case name already stored."""
        court = self.court

        class TestMerger(Merger[dict[str, str], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, reads=DOCKET_SAVE_READS
            )

            court_id: str = Constant(court.pk)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Scrape(dict)["docket_number"]
            case_name: str = Fn(_prefer_stored)(
                Database(CASE_NAME), Scrape(dict)["case_name"]
            )

        return TestMerger

    def loaded(
        self, merger: type[Merger[Any, Any, Docket]], docket: Docket
    ) -> Docket:
        """Read a docket the way the merger's lookup would."""
        return merger.config.loading(Docket.objects.filter(pk=docket.pk)).get()

    def test_reads_object_merged_into(self) -> None:
        """Does a spec reading the database see the object being merged into, keeping a stored value and falling back to the scrape when there is no object or its value is blank? Is the object updated only when the merged value differs from the stored one?"""
        merger = self.merger()
        cases: list[tuple[str, str, Any, str, bool]] = [
            ("no object", "DB-NEW", Create, "Scraped Name", False),
            (
                "stored",
                "DB-1",
                Update(self.loaded(merger, self.docket)),
                "Stored Name",
                False,
            ),
            (
                "blank stored",
                "DB-2",
                Update(self.loaded(merger, self.blank_docket)),
                "Scraped Name",
                True,
            ),
        ]
        for name, docket_number, existing, expected, updated in cases:
            with self.subTest(name):
                result = merger(
                    {
                        "docket_number": docket_number,
                        "case_name": "Scraped Name",
                    },
                    params=None,
                    existing=existing,
                ).merge()

                self.assertTrue(result.success, result.failures)
                self.assertEqual(result.update, updated)
                self.assertEqual(
                    Docket.objects.get(docket_number=docket_number).case_name,
                    expected,
                )

    def test_lookup_sees_scraped_value_of_database_spec(self) -> None:
        """Does a lookup see the scraped version of attributes that read the database, so one can be the natural key, and the merger the stored version once the object is found?"""
        seen: list[str] = []
        court = self.court

        class TestMerger(Merger[dict[str, str], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, key=("docket_number",), reads=DOCKET_SAVE_READS
            )

            court_id: str = Constant(court.pk)
            source: int = Constant(DocketSources.SCRAPER)
            docket_number: str = Coalesce(
                Scrape(dict)["docket_number"],
                Database(Docket.docket_number),
                default="",
            )
            case_name: str = Fn(_prefer_stored)(
                Database(CASE_NAME), Scrape(dict)["case_name"]
            )

            @override
            def lookup(
                self, state: MergerState.Lookup[dict[str, str], None, Docket]
            ) -> MergerState.LookupOutput[dict[str, str], None, Docket]:
                seen.append(self.case_name)
                return super().lookup(state)

        merger = TestMerger(
            {"docket_number": "DB-1", "case_name": "Scraped Name"},
            params=None,
        )
        result = merger.merge()

        self.assertTrue(result.success, result.failures)
        self.assertFalse(result.create)
        self.assertEqual(seen, ["Scraped Name"])
        self.assertEqual(merger.case_name, "Stored Name")

    def test_relation_input_reads_stored_value(self) -> None:
        """Is a relation whose input reads the database merged with the value stored on the object being merged into?"""

        class OriginMerger(
            Merger[dict[str, str], Any, OriginatingCourtInformation]
        ):
            config: ClassVar[MergerConfig[OriginatingCourtInformation]] = (
                MergerConfig(model=OriginatingCourtInformation)
            )

            docket_number: str = Scrape(dict)["docket_number"]

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                model=Docket, reads=DOCKET_SAVE_READS
            )

            docket_entries: list[DocketEntry] = OneToManyRelation(
                KeyedEntryMerger,
                Fn(_if_stored)(Database(CASE_NAME), Scrape(dict)["entries"]),
            )
            originating_court_information: OriginatingCourtInformation = (
                OneToOneRelation(
                    OriginMerger,
                    Fn(_if_stored)(
                        Database(CASE_NAME), Scrape(dict)["origin"]
                    ),
                )
            )

        result = TestMerger(
            {
                "entries": [{"description": "Entry"}],
                "origin": {"docket_number": "ORIGIN-1"},
            },
            params=None,
            existing=Update(self.loaded(TestMerger, self.docket)),
        ).merge()

        self.assertTrue(result.success, result.failures)
        for model in ("DocketEntry", "OriginatingCourtInformation"):
            with self.subTest(model):
                self.assertEqual(len(result.creates.get(model, ())), 1)

    def test_fields_read_from_database_are_loaded(self) -> None:
        """Is a field a spec reads from the database loaded, though no spec merges into it?"""

        class TestMerger(Merger[dict[str, str], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            case_name: str = Fn(_prefer_stored)(
                Database(CASE_NAME_FULL), Scrape(dict)["case_name"]
            )

        docket = self.loaded(TestMerger, self.docket)

        self.assertNotIn("case_name_full", docket.get_deferred_fields())
        self.assertIn("case_name_short", docket.get_deferred_fields())

    def test_database_field_of_another_model_is_rejected(self) -> None:
        """Is a spec reading a field of a model other than the merger's refused when the merger is defined?"""
        with self.assertRaisesRegex(TypeError, "is from DocketEntry"):

            class TestMerger(Merger[dict[str, str], None, Docket]):
                config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                    model=Docket
                )

                case_name: str | None = Database(DocketEntry.description)


class SaveStateTest(TestCase):
    """How a merger writes the object it merged into."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()
        cls.docket = DocketFactory.create(
            court=cls.court,
            source=DocketSources.SCRAPER,
            docket_number="SAVE-1",
        )

    @merger_test(expected_query_count=0)
    def test_unchanged_update_is_neither_written_nor_recorded(self) -> None:
        """Does an update that changes nothing skip the write and report no update?"""
        result = KeyedDocketMerger(
            {"docket_number": "SAVE-1", "entries": []},
            params=None,
            existing=Update(self.docket),
        ).merge()

        self.assertTrue(result.success, result.failures)
        self.assertFalse(result.update)

    def test_forced_update_is_recorded_without_writing(self) -> None:
        """Does a forced save of an unchanged object report it as updated without writing it?"""

        class TestMerger(Merger[dict[str, str], None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            docket_number: str = Scrape(dict)["docket_number"]

            @override
            def update(
                self, state: MergerState.Update[Any, Any, Docket]
            ) -> MergerState.UpdateOutput[Any, Any, Docket]:
                save_state = super().update(state)
                if not isinstance(save_state, MergerState.Save):
                    return save_state
                return state.save(
                    save_state.operation.instance,
                    save_state.operation.fields,
                    save_state.result,
                    force=True,
                )

        with CaptureQueriesContext(connection) as queries:
            result = TestMerger(
                {"docket_number": "SAVE-1"},
                params=None,
                existing=Update(self.docket),
            ).merge()

        self.assertTrue(result.success, result.failures)
        self.assertEqual(result.updates["Docket"], {self.docket.pk})
        self.assertEqual(len(queries), 0, queries.captured_queries)


class SpecAccessTrackingTest(SimpleTestCase):
    """What specs record about the inputs they read."""

    def test_specs_track_what_they_read(self) -> None:
        """Does every kind of expression report whether it reads the scrape and which stored fields it reads?"""
        cases: list[tuple[str, Any, bool, set[str]]] = [
            ("constant", Constant(1), False, set()),
            ("params", Params(dict)["a"], False, set()),
            ("scrape item", Scrape(dict)["a"], True, set()),
            ("scrape attribute", Scrape(ScrapeDocument).url, True, set()),
            ("database", Database(CASE_NAME), False, {"case_name"}),
            (
                "database attribute",
                cast(str, Database(CASE_NAME)).upper,
                False,
                {"case_name"},
            ),
            ("call on scrape", Fn(str)(Scrape(dict)["a"]), True, set()),
            (
                "call on database",
                Fn(_prefer_stored)(Database(CASE_NAME_FULL), Constant("")),
                False,
                {"case_name_full"},
            ),
            (
                "related",
                OneToManyRelation(
                    EntryMerger,
                    cast(
                        Any,
                        Fn(_prefer_stored)(
                            Database(CASE_NAME), Scrape(dict)["a"]
                        ),
                    ),
                ),
                True,
                {"case_name"},
            ),
            (
                "coalesce",
                Coalesce(Database(CASE_NAME), Scrape(dict)["a"], default=""),
                True,
                {"case_name"},
            ),
            (
                "coalesce without scrape",
                Coalesce(Database(CASE_NAME), Constant("a"), default=""),
                False,
                {"case_name"},
            ),
            (
                "item keyed by database",
                Constant(cast(Any, {}))[Database(CASE_NAME)],
                False,
                {"case_name"},
            ),
            (
                "item keyed by scrape",
                Constant(cast(Any, {}))[Scrape(dict)["a"]],
                True,
                set(),
            ),
        ]
        for name, spec, uses_scrape, db_fields in cases:
            with self.subTest(name):
                self.assertEqual(Source.SCRAPE in spec._sources, uses_scrape)
                self.assertEqual(set(spec._db_fields), db_fields)

    def test_item_keyed_by_expression_on_scrape(self) -> None:
        """Can the scrape be indexed by the value of another expression?"""
        spec: Any = Scrape(dict)[Params(str)]

        self.assertEqual(spec.transform({"a": 1}, "a", None), 1)

    def test_attribute_chained_on_database_value(self) -> None:
        """Is an attribute chained onto a stored field read from the field's value rather than from the object holding it?"""
        spec: Any = cast(str, Database(CASE_NAME)).upper()

        self.assertEqual(
            spec.transform({}, None, Docket(case_name="Stored")), "STORED"
        )


class ExpressionSourceTest(SimpleTestCase):
    """What expressions record about their sources, and how `==` builds terms."""

    def test_sources_are_tracked(self) -> None:
        """Does every kind of expression report which inputs it reads?"""
        cases: list[tuple[str, Any, Source]] = [
            ("scrape", Scrape(dict)["a"], Source.SCRAPE),
            ("params", Params(SimpleNamespace).x, Source.PARAMS),
            ("ancestor", Ancestor(Docket).pk, Source.ANCESTOR),
            ("database", Database(Docket.case_name), Source.DATABASE),
            ("annotation", Annotation("role"), Source.ANNOTATION),
            (
                "fn over database",
                Fn(_prefer_stored)(Database(Docket.case_name), ""),
                Source.CONSTANT | Source.DATABASE,
            ),
        ]
        for name, spec, sources in cases:
            with self.subTest(name):
                self.assertEqual(spec._sources, sources)

    def test_annotations_are_propagated_without_duplicates(self) -> None:
        """Are the annotation keys an expression reads collected once each, in order?"""
        spec: Any = Fn(_prefer_stored)(Annotation("role"), Annotation("role"))
        other: Any = Fn(_prefer_stored)(spec, Annotation("kind"))

        self.assertEqual(spec._annotations, ("role",))
        self.assertEqual(other._annotations, ("role", "kind"))
        self.assertEqual(other._sources, Source.CONSTANT | Source.ANNOTATION)

    def test_annotation_reads_attribute_and_loads_no_column(self) -> None:
        """Does an annotation read the attribute off the stored row without adding a column to load?"""
        spec = Annotation("role")

        self.assertEqual(
            spec.transform(None, None, SimpleNamespace(role="Appellant")),
            "Appellant",
        )
        self.assertEqual(spec._db_fields, ())
        self.assertEqual(spec._annotations, ("role",))

    def test_eq_builds_comparison(self) -> None:
        """Does `==` between expressions build a comparison of the two sides?"""
        left, right = Database(Docket.case_name), Scrape(dict)["n"]
        term = left == right

        self.assertIsInstance(term, Comparison)
        self.assertIs(term.left, left)
        self.assertIs(term.right, right)

    def test_comparison_has_no_truth_value(self) -> None:
        """Does using a comparison as a condition fail instead of silently succeeding?"""
        with self.assertRaises(TypeError):
            bool(Database(Docket.case_name) == Scrape(dict)["n"])

    def test_eq_with_plain_value_is_not_a_comparison(self) -> None:
        """Is `==` with something other than an expression left to Python?"""
        self.assertNotIsInstance(
            Database(Docket.case_name) == None,  # noqa: E711
            Comparison,
        )

    def test_specs_hash_and_compare_by_identity_in_containers(self) -> None:
        """Do containers tell two equal-looking expressions apart?"""
        a, b = Scrape(dict)["a"], Scrape(dict)["a"]

        self.assertEqual(len({a, b}), 2)
        self.assertIn(a, {a: 1})
        self.assertEqual(len(dict.fromkeys([a, b])), 2)


def _raise(*_: Any) -> Any:
    """Fail if called, to show an expression was never evaluated."""
    raise AssertionError("Expression should not have been evaluated")


class CoalesceSpecTest(SimpleTestCase):
    """Expressions picking the first usable value among several."""

    def test_outputs_first_truthy_or_integer_value(self) -> None:
        """Is the first argument that evaluates to a truthy value or an integer output, or the default when there is none?"""
        cases: list[tuple[str, dict[str, Any], Any]] = [
            ("first truthy", {"a": "x", "b": "y"}, "x"),
            ("skips None", {"a": None, "b": "y"}, "y"),
            ("skips empty string", {"a": "", "b": "y"}, "y"),
            ("skips empty list", {"a": [], "b": "y"}, "y"),
            ("keeps zero", {"a": 0, "b": 5}, 0),
            ("default", {"a": None, "b": ""}, "d"),
        ]
        spec: Any = Coalesce(Scrape(dict)["a"], Scrape(dict)["b"], default="d")
        for name, scrape, expected in cases:
            with self.subTest(name):
                self.assertEqual(spec.transform(scrape, None, None), expected)

    def test_default_defaults_to_none(self) -> None:
        """Is None output when every argument is unusable and no default is given?"""
        spec: Any = Coalesce(Scrape(dict)["a"])

        self.assertIsNone(spec.transform({"a": ""}, None, None))

    def test_default_is_not_evaluated(self) -> None:
        """Is an expression passed as the default output as-is rather than evaluated?"""
        default = Scrape(dict)["b"]
        spec: Any = Coalesce(Scrape(dict)["a"], default=default)

        self.assertIs(
            spec.transform({"a": None, "b": "y"}, None, None), default
        )

    def test_arguments_after_a_usable_value_are_not_evaluated(self) -> None:
        """Are arguments after the first usable one left unevaluated?"""
        spec: Any = Coalesce(Scrape(dict)["a"], Fn(_raise)(), default="d")

        self.assertEqual(spec.transform({"a": "x"}, None, None), "x")

    def test_reads_database(self) -> None:
        """Can a stored value be coalesced with a scraped one?"""
        spec: Any = Coalesce(
            Database(CASE_NAME), Scrape(dict)["a"], default=""
        )
        cases: list[tuple[str, Docket | None, str]] = [
            ("stored", Docket(case_name="Stored"), "Stored"),
            ("blank stored", Docket(case_name=""), "Scraped"),
            ("no object", None, "Scraped"),
        ]
        for name, docket, expected in cases:
            with self.subTest(name):
                self.assertEqual(
                    spec.transform({"a": "Scraped"}, None, docket), expected
                )


NS = SimpleNamespace


class PartyPoolMerger(Merger[dict[str, str], Any, Party]):
    """A party, for tests of the pools that read parties."""

    config: ClassVar[MergerConfig[Party]] = MergerConfig(model=Party)

    name: str = Scrape(dict)["name"]


PARTY_POOL = Relatives(party_types__docket=Ancestor(Docket)).annotate(
    role=F("party_types__name")
)
"""The parties on an ancestor docket, each with its role on that docket."""


class PoolTest(TestCase):
    """Which rows a pool puts in scope, and how its readers hand them out."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.docket_a = DocketFactory.create()
        cls.docket_b = DocketFactory.create()
        cls.entries = [
            DocketEntryFactory.create(
                docket=cls.docket_a, description=description
            )
            for description in ("First", "Second", "Third")
        ]
        DocketEntryFactory.create(docket=cls.docket_b, description="Other")
        cls.party = PartyFactory.create(
            name="Shared Party", docket=cls.docket_a
        )
        PartyTypeFactory.create(
            docket=cls.docket_a, party=cls.party, name="Appellant"
        )
        PartyTypeFactory.create(
            docket=cls.docket_b, party=cls.party, name="Respondent"
        )

    def siblings_reader(self, relation: QuerySet[DocketEntry]) -> Any:
        """A reader over a docket's entries, as its parent's relation."""
        return Siblings().reader(
            KeyedEntryMerger,
            relation=relation,
            params=None,
            ordering=("pk",),
        )

    def keyed_reader(self) -> Any:
        """A reader over the entries of the first docket, one query per call."""
        return Relatives(docket=Ancestor(Docket)).reader(
            KeyedEntryMerger,
            relation=None,
            params=RelatedParams(None, parent=self.docket_a),
            ordering=("pk",),
        )

    def test_filter_values_are_restricted(self) -> None:
        """Is a filter value that reads a scrape, the database or nothing but a plain value rejected?"""
        cases: dict[str, Any] = {
            "plain": 1,
            "scrape": Scrape(dict)["d"],
            "database": Database(Docket.case_name),
            "scrape and ancestor": Fn(_raise)(
                Scrape(dict)["d"], Ancestor(Docket)
            ),
        }
        for name, value in cases.items():
            with self.subTest(name), self.assertRaises(TypeError):
                Relatives(docket=value)

    def test_filter_values_may_read_params_ancestors_and_constants(
        self,
    ) -> None:
        """Is a filter value built from params, ancestors and constants accepted?"""
        pool = Relatives(
            docket=Ancestor(Docket),
            court=Params(SimpleNamespace).court,
            source=Constant(DocketSources.SCRAPER),
            number=Fn(_raise)(Ancestor(Docket), Constant(1)),
        )

        self.assertEqual(
            set(pool.filters), {"docket", "court", "source", "number"}
        )

    def test_annotate_rejects_non_expressions(self) -> None:
        """Is an annotation that is not a Django query expression rejected?"""
        for name, value in {
            "string": "party_types__name",
            "merger expression": Scrape(dict)["role"],
        }.items():
            with self.subTest(name), self.assertRaises(TypeError):
                Relatives().annotate(role=value)  # type: ignore[arg-type]

    def test_annotate_returns_new_pool(self) -> None:
        """Does annotating leave the pool it was called on unchanged?"""
        base = Relatives(party_types__docket=Ancestor(Docket))
        annotated = base.annotate(role=F("party_types__name"))

        self.assertEqual(base.annotations, {})
        self.assertEqual(set(annotated.annotations), {"role"})
        self.assertEqual(set(annotated.filters), {"party_types__docket"})
        self.assertIsInstance(annotated, Relatives)

    def test_annotation_reuses_filter_join(self) -> None:
        """Does a party on two dockets get only this docket's role?"""
        reader = PARTY_POOL.reader(
            PartyPoolMerger,
            relation=None,
            params=RelatedParams(None, parent=self.docket_a),
            ordering=("pk",),
        )

        rows: Sequence[Any] = reader.rows(Q(name=self.party.name), ("pk",))

        self.assertEqual([r.role for r in rows], ["Appellant"])

    def test_query_loads_annotates_and_orders(self) -> None:
        """Does a pool query load only the merger's fields, carry the annotations and sort as asked?"""
        query = PARTY_POOL.query(
            PartyPoolMerger,
            Party.objects.filter(party_types__docket=self.docket_b),
            ("-pk",),
        )

        self.assertEqual(
            list(query.values_list("role", flat=True)), ["Respondent"]
        )
        self.assertEqual(
            query.query.order_by,
            ("-pk",),
        )
        self.assertEqual(
            query.query.deferred_loading[0],
            frozenset(PartyPoolMerger.config.fields),
        )

    def test_relatives_are_bounded_by_filters(self) -> None:
        """Does a relatives pool read only the rows its filters allow?"""
        rows = self.keyed_reader().rows(Q(), ("pk",))

        self.assertEqual(
            [r.description for r in rows], ["First", "Second", "Third"]
        )

    def test_global_pool_reads_the_default_manager(self) -> None:
        """Does a global pool read rows of every parent?"""
        reader = Global().reader(
            KeyedEntryMerger, relation=None, params=None, ordering=("pk",)
        )

        self.assertEqual(
            [
                r.description
                for r in reader.rows(Q(description="Other"), ("pk",))
            ],
            ["Other"],
        )
        self.assertEqual(
            {r.pk for r in reader.rows(Q(), ("pk",))},
            set(DocketEntry.objects.values_list("pk", flat=True)),
        )

    def test_whole_reader_reads_once(self) -> None:
        """Does a whole reader answer every call from one query?"""
        reader = self.siblings_reader(self.docket_a.docket_entries.all())

        with self.assertNumQueries(1):
            reader.rows(Q(), ("pk",))
            reader.rows(Q(), ("-pk",))

    def test_whole_reader_ignores_where_and_sorts_in_memory(self) -> None:
        """Does a whole reader return every row, in the order asked for?"""
        reader = self.siblings_reader(self.docket_a.docket_entries.all())

        self.assertEqual(
            [r.pk for r in reader.rows(Q(description="First"), ("-pk",))],
            [e.pk for e in reversed(self.entries)],
        )

    def test_prefetched_relation_is_not_read_again(self) -> None:
        """Does a whole reader use a prefetched relation as it is?"""
        docket = Docket.objects.prefetch_related("docket_entries").get(
            pk=self.docket_a.pk
        )
        reader = self.siblings_reader(docket.docket_entries.all())

        with self.assertNumQueries(0):
            rows = reader.rows(Q(), ("pk",))

        self.assertEqual(len(rows), len(self.entries))

    def test_keyed_reader_queries_per_call(self) -> None:
        """Does a keyed reader run one query per call, filtered by where?"""
        reader = self.keyed_reader()

        with self.assertNumQueries(2):
            first = reader.rows(Q(description="First"), ("pk",))
            second = reader.rows(Q(description="Second"), ("-pk",))

        self.assertEqual([r.description for r in first], ["First"])
        self.assertEqual([r.description for r in second], ["Second"])

    def test_sort_rows_puts_nulls_last(self) -> None:
        """Do nulls sort after every value whichever the direction?"""
        rows = [NS(d=None, pk=1), NS(d=2, pk=2), NS(d=1, pk=3)]

        self.assertEqual(
            [r.pk for r in sort_rows(rows, ("d", "pk"))], [3, 2, 1]
        )
        self.assertEqual(
            [r.pk for r in sort_rows(rows, ("-d", "pk"))], [2, 3, 1]
        )

    def test_sort_rows_breaks_ties_by_later_fields(self) -> None:
        """Are ties on one field broken by the next, each with its own direction?"""
        rows = [NS(a=1, pk=1), NS(a=2, pk=2), NS(a=1, pk=3)]

        self.assertEqual(
            [r.pk for r in sort_rows(rows, ("a", "-pk"))], [3, 1, 2]
        )

    def test_siblings_without_relation_is_rejected(self) -> None:
        """Does a siblings pool refuse to read when there is no parent relation?"""
        with self.assertRaises(TypeError):
            Siblings().reader(
                KeyedEntryMerger,
                relation=None,
                params=None,
                ordering=("pk",),
            )

    def test_whole_prune_deletes_unkept_read_rows(self) -> None:
        """Does pruning a whole reader delete the rows it read that are not kept?"""
        relation = self.docket_a.docket_entries.all()
        reader = self.siblings_reader(relation)
        reader.rows(Q(), ("pk",))
        kept = self.entries[0]

        reader.prune(relation, {kept.pk})

        self.assertEqual(
            list(self.docket_a.docket_entries.values_list("pk", flat=True)),
            [kept.pk],
        )
        self.assertEqual(
            self.docket_b.docket_entries.count(),
            1,
            "Rows outside the pool are out of scope.",
        )

    def test_whole_prune_reads_when_rows_never_ran(self) -> None:
        """Does pruning a whole reader that has not read yet still delete exactly the unkept rows?"""
        relation = self.docket_a.docket_entries.all()
        reader = self.siblings_reader(relation)
        kept = self.entries[1]

        reader.prune(relation, {kept.pk})

        self.assertEqual(
            list(self.docket_a.docket_entries.values_list("pk", flat=True)),
            [kept.pk],
        )

    def test_keyed_prune_excludes_without_reading(self) -> None:
        """Does pruning a keyed reader delete by exclusion without reading the pool first?"""
        relation = self.docket_a.docket_entries.all()
        reader = self.keyed_reader()
        kept = self.entries[2]

        with CaptureQueriesContext(connection) as queries:
            reader.prune(relation, {kept.pk})

        self.assertEqual(
            list(self.docket_a.docket_entries.values_list("pk", flat=True)),
            [kept.pk],
        )
        # Django's `QuerySet.delete()` issues all of these; a read of the
        # pool would be one more `SELECT` from the entries table.
        # `QuerySet.delete()` collects the rows to delete (one `SELECT` of the
        # entries, one for each relation cascading from them) and then updates
        # and deletes: 7 queries here. The single `SELECT` of the entries is
        # the collector's, so the pool's read never happens.
        self.assertEqual(len(queries), 7)
        self.assertEqual(
            sum(
                q["sql"].startswith('SELECT "search_docketentry"."id"')
                for q in queries
            ),
            1,
        )


class NumberedEntryMerger(Merger[dict[str, str], Any, DocketEntry]):
    """A docket entry whose number is scraped as text."""

    config: ClassVar[MergerConfig[DocketEntry]] = MergerConfig(
        model=DocketEntry, key=("entry_number",)
    )

    entry_number: str = Scrape(dict)["number"]


class MatchDeclarationTest(SimpleTestCase):
    """Declaring match tiers and binding them to a merger."""

    def test_rejections(self) -> None:
        """Is each invalid declaration rejected, naming the problem?"""
        cases: dict[str, tuple[Match, str]] = {
            "unknown shorthand field": (Match(Key("nope")), "nope"),
            "shorthand not computed by merger": (
                Match(Key("entry_number")),
                "entry_number",
            ),
            "stored side reads scrape": (
                Match(
                    Key(
                        Fn(operator.add)(
                            Database(DocketEntry.description),
                            Scrape(dict)["x"],
                        )
                        == Constant(1)
                    )
                ),
                "may only read",
            ),
            "stored side reads params": (
                Match(Key(Fn(str)(Params(Any)) == Scrape(dict)["x"])),
                "exactly one side",
            ),
            "neither side reads row": (
                Match(Key(Constant(1) == Scrape(dict)["x"])),
                "exactly one side",
            ),
            "both sides read row": (
                Match(
                    Key(
                        cast(Any, Database(DocketEntry.description))
                        == Database(DocketEntry.description)
                    )
                ),
                "exactly one side",
            ),
            "annotation not in pool": (
                Match(Key(Annotation("role") == Scrape(dict)["r"])),
                "role",
            ),
            "ordering not a field": (
                Match(Key("description", ambiguous=First("nope"))),
                "nope",
            ),
            "ordering is an expression": (
                Match(
                    Key("description", ambiguous=First("description__lower"))
                ),
                "description__lower",
            ),
            "non-term": (Match(Key(cast(Any, False))), "False"),
            "invalid term in a narrow": (
                Match(Key("description", ambiguous=Narrow("nope"))),
                "nope",
            ),
        }
        for name, (match, problem) in cases.items():
            with self.subTest(name):
                with self.assertRaises(ExceptionGroup) as raised:
                    match.bind(KeyedEntryMerger, None)
                self.assertIn(problem, str(raised.exception))

    def test_every_problem_is_reported(self) -> None:
        """Does the group carry one error for each problem in the declaration?"""
        with self.assertRaises(ExceptionGroup) as raised:
            Match(
                Key("nope"), Key("description", ambiguous=First("nah"))
            ).bind(KeyedEntryMerger, None)
        self.assertEqual(len(raised.exception.exceptions), 2)

    def test_annotation_in_declared_pool_is_accepted(self) -> None:
        """Is an annotation the declared pool adds accepted in a term?"""
        pool = Siblings().annotate(role=F("description"))
        Match(Key(Annotation("role") == Scrape(dict)["r"])).bind(
            KeyedEntryMerger, pool
        )

    def test_bound_tier_ordering_ends_in_pk(self) -> None:
        """Does every tier's ordering end in `pk`, whether or not it has a `First`?"""
        bound = Match(
            Key("description", ambiguous=First("-date_created")),
            Key("description"),
        ).bind(KeyedEntryMerger, None)
        self.assertEqual(bound.tiers[0].ordering, ("-date_created", "pk"))
        self.assertEqual(bound.tiers[1].ordering, ("pk",))

    def test_ordering_naming_pk_is_unchanged(self) -> None:
        """Is `pk` left alone when the ordering already names it?"""
        bound = Match(Key("description", ambiguous=First("pk"))).bind(
            KeyedEntryMerger, None
        )
        self.assertEqual(bound.tiers[0].ordering, ("pk",))

    def test_tier_ordering_is_that_of_the_first_a_narrow_chain_ends_in(
        self,
    ) -> None:
        """Does a tier take the ordering of the `First` ending its `Narrow` chain?"""
        bound = Match(
            Key(
                "description",
                ambiguous=Narrow(
                    Database(DocketEntry.entry_number)
                    == Scrape(dict)["number"],
                    ambiguous=First("-date_created"),
                ),
            )
        ).bind(KeyedEntryMerger, None)
        self.assertEqual(bound.tiers[0].ordering, ("-date_created", "pk"))

    def test_columns_include_stored_fields_and_orderings(self) -> None:
        """Are the columns every stored field of every term plus every ordering field?"""
        bound = Match(
            Key(
                "description",
                ambiguous=Narrow(
                    Database(DocketEntry.entry_number)
                    == Scrape(dict)["number"],
                    ambiguous=First("-date_created", "pk"),
                ),
            )
        ).bind(KeyedEntryMerger, None)
        self.assertEqual(
            bound.columns, {"description", "entry_number", "date_created"}
        )

    def test_bare_fail_is_normalised(self) -> None:
        """Is `Fail` passed as a class turned into an instance, wherever it is an outcome?"""
        self.assertEqual(Key().ambiguous, Fail())
        self.assertEqual(Key(missing=Fail, duplicate=Fail).missing, Fail())
        self.assertEqual(Key(missing=Fail, duplicate=Fail).duplicate, Fail())
        self.assertEqual(Narrow().missing, Fail())
        self.assertEqual(Narrow().ambiguous, Fail())

    def test_default_outcomes(self) -> None:
        """Do tiers and narrows default to the outcomes the declaration documents?"""
        key = Key()
        self.assertIs(key.missing, Next)
        self.assertEqual(key.ambiguous, Fail())
        self.assertEqual(key.duplicate, Fail())

    def test_bound_outcomes_are_carried(self) -> None:
        """Does a bound tier carry its outcomes, with a `Narrow` bound too?"""
        message = Fail("no")
        bound = Match(
            Key(
                "description",
                missing=Create,
                ambiguous=Narrow(
                    Database(DocketEntry.entry_number)
                    == Scrape(dict)["number"],
                    missing=message,
                ),
                duplicate=Next,
            )
        ).bind(KeyedEntryMerger, None)
        tier = bound.tiers[0]
        self.assertEqual(tier.index, 1)
        self.assertIs(tier.missing, Create)
        self.assertIs(tier.duplicate, Next)
        self.assertIsInstance(tier.ambiguous, BoundNarrow)
        self.assertEqual(cast(BoundNarrow, tier.ambiguous).missing, message)
        self.assertEqual(len(tier.chain_terms), 1)
        self.assertEqual(len(tier.terms), 1)

    def test_distinct_comparisons_are_unequal(self) -> None:
        """Do two comparisons compare unequal without evaluating the `==` of their sides?"""
        a = Database(DocketEntry.description) == Scrape(dict)["a"]
        b = Database(DocketEntry.description) == Scrape(dict)["a"]
        self.assertNotEqual(a, b)
        self.assertEqual(a, a)

    def test_keyed_pool_needs_a_bare_term(self) -> None:
        """Does a keyed pool reject a tier with no bare `Database` term, and a whole pool accept it?"""
        bound = Match(
            Key(
                Fn(operator.methodcaller("lower"))(
                    Database(DocketEntry.description)
                )
                == Scrape(dict)["d"]
            )
        ).bind(KeyedEntryMerger, None)
        self.assertTrue(bound.check_pool(Global()))
        self.assertTrue(bound.check_pool(Relatives()))
        self.assertFalse(bound.check_pool(Siblings()))

    def test_keyed_pool_accepts_bare_terms(self) -> None:
        """Is a tier with a shorthand term or a bare `Database` term accepted by a keyed pool?"""
        for name, key in {
            "shorthand": Key("description"),
            "explicit": Key(
                Database(DocketEntry.description) == Scrape(dict)["d"]
            ),
        }.items():
            with self.subTest(name):
                bound = Match(key).bind(KeyedEntryMerger, None)
                self.assertEqual(bound.check_pool(Global()), [])

    def test_keyed_pool_reports_each_bare_less_tier(self) -> None:
        """Is there one error per tier without a bare term?"""
        bound = Match(
            Key(),
            Key("description"),
            Key(cast(Any, Constant(1)) == Database(DocketEntry.entry_number)),
        ).bind(KeyedEntryMerger, None)
        self.assertEqual(len(bound.check_pool(Global())), 1)

    def test_shorthand_term_values(self) -> None:
        """Does the shorthand read the stored column and the merger's computed value, converted by the field?"""
        bound = Match(Key("entry_number")).bind(NumberedEntryMerger, None)
        (term,) = bound.tiers[0].terms
        merger = SimpleNamespace(entry_number="5")
        state = MergerState.Lookup({"number": "5"}, None, {})
        self.assertEqual(
            term.scraped_value(cast(Any, merger), state),
            5,
        )
        self.assertEqual(term.stored_value(DocketEntry(entry_number=5)), 5)
        self.assertIsNotNone(term.field)
        self.assertEqual(term.attribute, "entry_number")

    def test_explicit_term_values(self) -> None:
        """Does an explicit term evaluate each side against its own input?"""
        bound = Match(
            Key(
                Fn(operator.methodcaller("lower"))(
                    Database(DocketEntry.description)
                )
                == Fn(str.lower)(Scrape(dict)["d"])
            )
        ).bind(KeyedEntryMerger, None)
        (term,) = bound.tiers[0].terms
        state = MergerState.Lookup({"d": "AbC"}, None, {})
        self.assertEqual(
            term.scraped_value(cast(Any, SimpleNamespace()), state), "abc"
        )
        self.assertEqual(
            term.stored_value(DocketEntry(description="XyZ")), "xyz"
        )
        self.assertIsNone(term.field)
        self.assertIsNone(term.attribute)

    def test_explicit_bare_term_converts_scraped_value(self) -> None:
        """Is the scraped side of a bare `Database` term converted by the stored field?"""
        bound = Match(
            Key(Database(DocketEntry.entry_number) == Scrape(dict)["n"])
        ).bind(KeyedEntryMerger, None)
        (term,) = bound.tiers[0].terms
        state = MergerState.Lookup({"n": "7"}, None, {})
        self.assertEqual(
            term.scraped_value(cast(Any, SimpleNamespace()), state), 7
        )
