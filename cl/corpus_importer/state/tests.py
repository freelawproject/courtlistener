from collections.abc import Iterable
from typing import Any, ClassVar

from django.db import connection
from django.db.models import Model, QuerySet

from cl.corpus_importer.state.merger import (
    Attribute,
    ManyStrategy,
    ManyToManyRelation,
    Merger,
    OneToManyRelation,
    OneToOneRelation,
    RelatedParams,
    ThroughParameters,
)
from cl.people_db.factories import PersonFactory
from cl.people_db.models import Party, PartyType, Person
from cl.search.docket_sources import DocketSources
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import (
    Court,
    Docket,
    DocketEntry,
    OriginatingCourtInformation,
)
from cl.tests.cases import TestCase


class QueryCountTestCase(TestCase):
    """Track the number of queries run during each test and print a summary
    once the class finishes.

    Queries executed while inside a ``Merger.merge()`` call are counted as
    "merger" queries; everything else (factories, assertion fetches, other
    test scaffolding) is counted as "test"."""

    _query_counts: ClassVar[dict[str, dict[str, int]]]
    _merger_queries: ClassVar[dict[str, list[str]]]

    @classmethod
    def setUpClass(cls) -> None:
        cls._query_counts = {}
        cls._merger_queries = {}
        super().setUpClass()

    def setUp(self) -> None:
        super().setUp()
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
                if merge_depth:
                    counts["merger"] += 1
                    merger_sql.append(sql)
                else:
                    counts["test"] += 1
            return execute(sql, params, many, context)

        Merger.merge = counting_merge  # type: ignore[method-assign, assignment]
        self.addCleanup(setattr, Merger, "merge", original_merge)

        wrapper = connection.execute_wrapper(count_query)
        wrapper.__enter__()

        def record_query_count() -> None:
            wrapper.__exit__(None, None, None)
            self._query_counts[self._testMethodName] = counts
            self._merger_queries[self._testMethodName] = merger_sql

        self.addCleanup(record_query_count)

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        print(f"\n{cls.__name__} query counts:")
        ROW_WIDTH = 65
        print("-" * (ROW_WIDTH + 10))
        print(f"| {'Test':^{ROW_WIDTH}} | {'Qs':^3} |")
        print("|-" + "-" * ROW_WIDTH + "-|-----|")
        for name, counts in sorted(cls._query_counts.items()):
            # total = counts["merger"] + counts["test"]
            print(f"| {name:>{ROW_WIDTH}} | {counts['merger']:>3} |")
            # for sql in cls._merger_queries[name]:
            #     sql = re.sub(r"^SELECT .*? FROM", "SELECT ... FROM", sql)
            #     sql = re.sub(
            #         r"\([^)]*\) VALUES \([^)]*\)", "(...) VALUES (...)", sql
            #     )
            #     print(f"    {sql}")
        merger_total = sum(c["merger"] for c in cls._query_counts.values())
        # test_total = sum(c["test"] for c in cls._query_counts.values())
        print(f"| {'total':>{ROW_WIDTH}} | {merger_total:>3} |")
        print("-" * (ROW_WIDTH + 10))


class BaseMergerTest(QueryCountTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()
        cls.docket = DocketFactory.create()

    def test_merger_creates_object(self) -> None:
        start_count = Docket.objects.count()

        class TestMerger(Merger[dict[str, str], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=self.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(default="ABCDEFG")

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

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

    def test_merger_updates_docket(self) -> None:
        tc = self
        dn = self.docket.docket_number
        new_dn = dn + "New"
        start_docket_count = Docket.objects.count()

        class TestMerger(Merger[dict[str, str], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court_id: Court = Attribute(default=self.court.id)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(default=new_dn)

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

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

    def test_mappings_called(self) -> None:
        map_calls = 0
        dn = "ABCDEFG"

        def test_mapping(i: dict[str, str], params) -> str:
            nonlocal map_calls
            map_calls += 1
            return dn

        class TestMerger(Merger[dict[str, str], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=self.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(test_mapping)

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

        r = TestMerger({}, params=None).merge()
        self.assertEqual(map_calls, 1)
        docket = Docket.objects.get(pk=r.creates["Docket"].pop())
        self.assertEqual(docket.docket_number, dn)

    def test_related_mergers_1to1(self) -> None:
        class TestRelatedMerger(
            Merger[
                dict[str, str],
                RelatedParams[None],
                OriginatingCourtInformation,
            ]
        ):
            model: ClassVar[type[Model]] = OriginatingCourtInformation

            docket_number: str = Attribute(lambda d, params: d["sr"])

            @classmethod
            def get_existing(
                cls, d: dict[str, str], manager, params: None
            ) -> OriginatingCourtInformation | None:
                return None

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=self.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(
                default=self.docket.docket_number + "New"
            )
            originating_court_information: OriginatingCourtInformation = (
                OneToOneRelation(
                    TestRelatedMerger,
                    lambda d, params: d["mctest"],
                )
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

        i = {"mctest": {"sr": "test"}}
        result = TestMerger(i, params=None).merge()

        self.assertIn("OriginatingCourtInformation", result.creates)
        self.assertEqual(len(result.creates["OriginatingCourtInformation"]), 1)
        oci_pk = result.creates["OriginatingCourtInformation"].pop()
        oci = OriginatingCourtInformation.objects.get(pk=oci_pk)
        self.assertEqual(oci.docket_number, i["mctest"]["sr"])
        self.assertEqual(oci.docket.pk, result.creates["Docket"].pop())

    def test_related_mergers_child(self) -> None:
        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], DocketEntry]
        ):
            model: ClassVar[type[Model]] = DocketEntry

            description: str = Attribute(lambda d, params: d["df"])

            def query(self) -> QuerySet[DocketEntry]:
                return DocketEntry.objects.none()

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=self.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(
                default=self.docket.docket_number + "New"
            )
            docket_entries: list[DocketEntry] = OneToManyRelation(
                TestRelatedMerger,
                lambda d, params: d["mctest"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

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

    def test_related_mergers_m2m_simple(self) -> None:
        """Does a plain (no-through) many-to-many relation create the targets
        and link them to the parent? Uses batched candidate lookups so the
        bulk-linking path is exercised."""

        class TestPersonMerger(
            Merger[dict[str, str], RelatedParams[None], Person]
        ):
            model: ClassVar[type[Model]] = Person

            name_first: str = Attribute(lambda d, params: d["first"])
            name_last: str = Attribute(lambda d, params: d["last"])
            slug: str = Attribute(lambda d, params: d["slug"])
            key = ["slug"]

            @classmethod
            def candidates(
                cls, parent: Model, params: RelatedParams[None]
            ) -> QuerySet[Person]:
                return Person.objects.filter(empanelled_dockets=parent)

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=self.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(default="M2M-SIMPLE")
            panel: list[Person] = ManyToManyRelation(
                TestPersonMerger,
                transform=lambda d, params: d["panel"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

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

    def test_related_mergers_m2m_through(self) -> None:
        """Does a many-to-many relation with a `through` model create the
        targets, link them to the parent, and populate the through row's own
        fields from the same scrape?"""

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            model: ClassVar[type[Model]] = Party
            key: ClassVar[Iterable[str]] = ["name"]

            name: str = Attribute(lambda d, params: d["name"])

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            model: ClassVar[type[Model]] = PartyType
            key: ClassVar[Iterable[str]] = ["name"]

            name: str = Attribute(lambda d, params: d["type"])

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=self.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(default="M2M-THROUGH")
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                TestPartyTypeMerger,
                lambda d, params: d["parties"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

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

    def test_related_mergers_m2m_simple_disassociate(self) -> None:
        """Does DISASSOCIATE on a plain many-to-many remove stale
        associations while keeping the objects themselves?"""
        stale = PersonFactory.create()
        self.docket.panel.add(stale)
        tc = self

        class TestPersonMerger(
            Merger[dict[str, str], RelatedParams[None], Person]
        ):
            model: ClassVar[type[Model]] = Person
            key: ClassVar[Iterable[str]] = ["slug"]

            name_first: str = Attribute(lambda d, params: d["first"])
            name_last: str = Attribute(lambda d, params: d["last"])
            slug: str = Attribute(lambda d, params: d["slug"])

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=tc.docket.court)
            source: int = Attribute(default=tc.docket.source)
            docket_number: str = Attribute(default=tc.docket.docket_number)
            panel: list[Person] = ManyToManyRelation(
                TestPersonMerger,
                transform=lambda d, params: d["panel"],
                strategy=ManyStrategy.DISASSOCIATE,
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

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

    def test_related_mergers_m2m_through_disassociate(self) -> None:
        """Does DISASSOCIATE on a through many-to-many prune the stale
        through rows while keeping the related objects themselves?"""
        stale_party = Party.objects.create(name="Stale Party")
        PartyType.objects.create(
            docket=self.docket, party=stale_party, name="Plaintiff"
        )
        tc = self

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            model: ClassVar[type[Model]] = Party
            key: ClassVar[Iterable[str]] = ["name"]

            name: str = Attribute(lambda d, params: d["name"])

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            model: ClassVar[type[Model]] = PartyType

            name: str = Attribute(lambda d, params: d["type"])

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=tc.docket.court)
            source: int = Attribute(default=tc.docket.source)
            docket_number: str = Attribute(default=tc.docket.docket_number)
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                TestPartyTypeMerger,
                lambda d, params: d["parties"],
                strategy=ManyStrategy.DISASSOCIATE,
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

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

    def test_related_mergers_m2m_through_replace_deletes(self) -> None:
        """Characterization: does REPLACE on a through many-to-many delete
        the stale related objects outright?"""
        stale_party = Party.objects.create(name="Stale Party")
        PartyType.objects.create(
            docket=self.docket, party=stale_party, name="Plaintiff"
        )
        tc = self

        class TestPartyMerger(
            Merger[dict[str, str], RelatedParams[None], Party]
        ):
            model: ClassVar[type[Model]] = Party
            key: ClassVar[Iterable[str]] = ["name"]

            name: str = Attribute(lambda d, params: d["name"])

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            model: ClassVar[type[Model]] = PartyType

            name: str = Attribute(lambda d, params: d["type"])

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=tc.docket.court)
            source: int = Attribute(default=tc.docket.source)
            docket_number: str = Attribute(default=tc.docket.docket_number)
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                TestPartyTypeMerger,
                lambda d, params: d["parties"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        i = {"parties": [{"name": "Alice", "type": "Plaintiff"}]}
        result = TestMerger(i, params=None).merge()

        self.assertTrue(result.success)
        self.assertFalse(
            Party.objects.filter(pk=stale_party.pk).exists(),
            "REPLACE deletes stale related objects outright.",
        )

    def test_related_mergers_child_replace_keeps_rows_on_invalid_child(
        self,
    ) -> None:
        """Does REPLACE leave existing rows alone when a child's input is
        invalid? The child gives up before looking anything up, so the row it
        would have matched isn't known and can't be pruned safely."""
        stale = DocketEntry.objects.create(
            docket=self.docket, description="Stale"
        )
        tc = self

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], DocketEntry]
        ):
            model: ClassVar[type[Model]] = DocketEntry
            key: ClassVar[Iterable[str]] = ["description"]

            description: str = Attribute(lambda d, params: d["df"])

            @staticmethod
            def validate(scrape: dict[str, str]) -> bool:
                return scrape["df"] != "Invalid"

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=tc.docket.court)
            source: int = Attribute(default=tc.docket.source)
            docket_number: str = Attribute(default=tc.docket.docket_number)
            docket_entries: list[DocketEntry] = OneToManyRelation(
                TestRelatedMerger,
                lambda d, params: d["entries"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

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

    def test_related_mergers_m2m_replace_keeps_rows_on_ambiguous_child(
        self,
    ) -> None:
        """Does REPLACE leave existing rows alone when a child's lookup
        matches several rows? The merger can't pick one, so it never learns
        which row belongs to this scrape."""
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
            model: ClassVar[type[Model]] = Party
            key: ClassVar[Iterable[str]] = ["name"]

            name: str = Attribute(lambda d, params: d["name"])

        class TestPartyTypeMerger(
            Merger[dict[str, str], ThroughParameters[None], PartyType]
        ):
            model: ClassVar[type[Model]] = PartyType

            name: str = Attribute(lambda d, params: d["type"])

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=tc.docket.court)
            source: int = Attribute(default=tc.docket.source)
            docket_number: str = Attribute(default=tc.docket.docket_number)
            parties: list[Party] = ManyToManyRelation(
                TestPartyMerger,
                TestPartyTypeMerger,
                lambda d, params: d["parties"],
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

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

    def test_merger_subclassing(self) -> None:
        class TestMerger(Merger[dict[str, str], dict[str, Any], Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=self.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(default="ABCDEFG")

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.none()

        class TestMerger2(TestMerger):
            court: Court = Attribute(default=self.court)
            docket_number: str = Attribute(default="ABCDEFGH")
            assigned_to_str: str = Attribute(
                lambda d, params: params["assigned_to_str"]
            )

        ats = "test"
        result = TestMerger2({}, params={"assigned_to_str": ats}).merge()

        self.assertIn("Docket", result.creates)
        self.assertEqual(len(result.creates["Docket"]), 1)
        docket = Docket.objects.get(pk=result.creates["Docket"].pop())
        self.assertEqual(docket.docket_number, "ABCDEFGH")
        self.assertEqual(docket.source, DocketSources.SCRAPER)
        self.assertEqual(docket.assigned_to_str, ats)
