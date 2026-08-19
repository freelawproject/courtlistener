import json
import sqlite3
from collections.abc import Callable, Iterable
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, ClassVar, ParamSpec, TypeVar

from django.db import connection
from django.db.models import Model, QuerySet
from pydantic import BaseModel

from cl.corpus_importer.state.loader import (
    JKentScrapeLoader,
    LoadReport,
    UnusableScrape,
)
from cl.corpus_importer.state.merger import (
    Attribute,
    ManyStrategy,
    ManyToManyRelation,
    Merger,
    OneToManyRelation,
    OneToOneRelation,
    RelatedParams,
    ReverseOneToOneRelation,
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
    TrialCourtData,
)
from cl.tests.cases import TestCase

Param = ParamSpec("Param")
Return = TypeVar("Return")


def merger_test(
    *, expected_query_count: int | range | None = None
) -> Callable[[Callable[Param, Return]], Callable[Param, Return]]:
    def decorator(f: Callable[Param, Return]) -> Callable[Param, Return]:
        def wrapper(*args: Param.args, **kwargs: Param.kwargs) -> Return:
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


class BaseMergerTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()
        cls.docket = DocketFactory.create()

    @merger_test(expected_query_count=1)
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

    @merger_test(expected_query_count=2)
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

    @merger_test(expected_query_count=1)
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

    @merger_test(expected_query_count=3)
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

    @merger_test(expected_query_count=6)
    def test_related_mergers_reverse_1to1_creates(self) -> None:
        """Does a reverse one-to-one relation, where the OneToOneField lives on
        the child, create the child pointing at the parent?"""
        tc = self

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], TrialCourtData]
        ):
            model: ClassVar[type[Model]] = TrialCourtData
            key: ClassVar[Iterable[str]] = ["docket"]

            docket: Docket = Attribute(lambda d, params: params.parent)
            docket_number_trial: str = Attribute(lambda d, params: d["dn"])

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=tc.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(default=tc.docket.docket_number)
            trialcourtdata: TrialCourtData = ReverseOneToOneRelation(
                TestRelatedMerger, lambda d, params: d["trial"]
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        result = TestMerger({"trial": {"dn": "CR-123"}}, params=None).merge()

        self.assertTrue(result.success)
        self.assertIn("TrialCourtData", result.creates)
        self.docket.refresh_from_db()
        self.assertEqual(
            self.docket.trialcourtdata.docket_number_trial, "CR-123"
        )

    @merger_test(expected_query_count=5)
    def test_related_mergers_reverse_1to1_updates(self) -> None:
        """Does a reverse one-to-one relation update the row the parent already
        has instead of creating a second one?"""
        existing = TrialCourtData.objects.create(
            docket=self.docket, docket_number_trial="CR-000"
        )
        tc = self

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], TrialCourtData]
        ):
            model: ClassVar[type[Model]] = TrialCourtData
            key: ClassVar[Iterable[str]] = ["docket"]

            docket: Docket = Attribute(lambda d, params: params.parent)
            docket_number_trial: str = Attribute(lambda d, params: d["dn"])

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=tc.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(default=tc.docket.docket_number)
            trialcourtdata: TrialCourtData = ReverseOneToOneRelation(
                TestRelatedMerger, lambda d, params: d["trial"]
            )

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(pk=tc.docket.pk)

        result = TestMerger({"trial": {"dn": "CR-999"}}, params=None).merge()

        self.assertTrue(result.success)
        self.assertNotIn("TrialCourtData", result.creates)
        self.assertEqual(TrialCourtData.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.docket_number_trial, "CR-999")

    @merger_test(expected_query_count=5)
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

    @merger_test(expected_query_count=9)
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

    @merger_test(expected_query_count=9)
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

    @merger_test(expected_query_count=9)
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

    @merger_test(expected_query_count=10)
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

    @merger_test(expected_query_count=16)
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

    @merger_test(expected_query_count=4)
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

    @merger_test(expected_query_count=3)
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

    @merger_test(expected_query_count=1)
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


def _run_database(path: Path, payloads: list[dict[str, Any]]) -> None:
    """Write a minimal stand-in for a jkent run database.

    Only the columns `JKentScrapeLoader` reads are created, since the loader's
    contract is with the `results` table rather than with the whole schema."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "CREATE TABLE results ("
            "  id INTEGER PRIMARY KEY,"
            "  data_json VARCHAR NOT NULL"
            ")"
        )
        connection.executemany(
            "INSERT INTO results (data_json) VALUES (?)",
            [(json.dumps(payload),) for payload in payloads],
        )
        connection.commit()


class LoaderScrape(BaseModel):
    """The scrape a `JKentScrapeLoader` test subclass validates rows into."""

    docket_number: str
    case_name: str = ""


class JKentScrapeLoaderTest(TestCase):
    """Tests for the generic jkent run-database loader.

    The loader is court-agnostic, so these exercise it through a throwaway
    scrape model and merger rather than through any one state's loader.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "run.db"

    def loader_class(self, **attributes: Any) -> type[JKentScrapeLoader[Any]]:
        """A loader over the test database, merging into `Docket`.

        :param attributes: Overrides for the returned class, so a test can
            supply its own `normalize` or merger.
        :return: The loader class.
        """
        # Not named `court`: a class body cannot close over an enclosing local
        # whose name it also assigns.
        test_court = self.court

        class TestMerger(Merger[LoaderScrape, None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=test_court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(
                lambda scrape, params: scrape.docket_number
            )
            case_name: str = Attribute(lambda scrape, params: scrape.case_name)

            def query(self) -> QuerySet[Docket]:
                return Docket.objects.filter(
                    court=test_court, docket_number=self.scrape.docket_number
                )

        return type(
            "TestLoader",
            (JKentScrapeLoader,),
            {
                "query": "SELECT data_json FROM results ORDER BY id",
                "scrape_model": LoaderScrape,
                "merger": TestMerger,
            }
            | attributes,
        )

    def test_missing_database(self) -> None:
        """Is a run database that isn't there reported as such, rather than
        counted as an empty run?"""
        loader = self.loader_class()(self.database)

        with self.assertRaises(FileNotFoundError):
            loader.load()

    def test_load_merges_every_row(self) -> None:
        """Does a clean run merge one object per row and report it?"""
        _run_database(
            self.database,
            [
                {"docket_number": "A-1", "case_name": "Smith v Jones"},
                {"docket_number": "A-2", "case_name": "Roe v Doe"},
            ],
        )

        report = self.loader_class()(self.database).load()

        self.assertEqual((report.seen, report.merged), (2, 2))
        self.assertEqual(
            (report.skipped, report.invalid, report.rejected, report.failed),
            (0, 0, 0, 0),
        )
        self.assertEqual(len(report.result.creates["Docket"]), 2)
        self.assertEqual(
            set(Docket.objects.values_list("docket_number", flat=True)),
            {"A-1", "A-2"},
        )

    def test_scrapes_yields_without_writing(self) -> None:
        """`scrapes()` is the seam for inspecting a run. Does it produce the
        validated scrapes and leave the database alone?"""
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        scrapes = list(self.loader_class()(self.database).scrapes())

        self.assertEqual([s.docket_number for s in scrapes], ["A-1", "A-2"])
        self.assertFalse(Docket.objects.exists())

    def test_limit_stops_the_run_early(self) -> None:
        """Does `limit` stop the load after that many rows?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        report = self.loader_class()(self.database, limit=2).load()

        self.assertEqual((report.seen, report.merged), (2, 2))
        self.assertEqual(Docket.objects.count(), 2)

    def test_dry_run_reports_a_real_merge_but_writes_nothing(self) -> None:
        """A dry run runs the merge in full and rolls it back. Is the report
        real while the database is left untouched?"""
        _run_database(self.database, [{"docket_number": "A-1"}])

        report = self.loader_class()(self.database, dry_run=True).load()

        self.assertEqual((report.seen, report.merged), (1, 1))
        self.assertIn("Docket", report.result.creates)
        self.assertFalse(Docket.objects.exists())

    def test_normalize_returning_none_is_a_skip(self) -> None:
        """`normalize` returning `None` is the loader's own judgment that there
        is nothing to do with a row. Is it counted as skipped, not failed?"""

        def normalize(
            self: Any, payload: dict[str, Any], row: sqlite3.Row
        ) -> dict[str, Any] | None:
            return None if payload["docket_number"] == "A-1" else payload

        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        report = self.loader_class(normalize=normalize)(self.database).load()

        self.assertEqual(
            (report.seen, report.skipped, report.merged, report.failed),
            (2, 1, 1, 0),
        )
        self.assertEqual(Docket.objects.count(), 1)

    def test_normalize_raising_unusable_scrape_is_a_failure(self) -> None:
        """`UnusableScrape` says the run needs looking at. Is the row counted
        as failed and recorded against the merger's model, so a run's failures
        are all in one place?"""

        def normalize(
            self: Any, payload: dict[str, Any], row: sqlite3.Row
        ) -> dict[str, Any] | None:
            raise UnusableScrape(f"{payload['docket_number']} is unusable")

        _run_database(self.database, [{"docket_number": "A-1"}])

        report = self.loader_class(normalize=normalize)(self.database).load()

        self.assertEqual(
            (report.seen, report.failed, report.skipped, report.merged),
            (1, 1, 0, 0),
        )
        # No PK, because the row was refused before anything was looked up.
        self.assertEqual(report.result.failures, {"Docket": [None]})
        self.assertFalse(Docket.objects.exists())

    def test_payload_that_does_not_fit_the_model_is_invalid(self) -> None:
        """A payload the scrape model rejects usually means scraper drift. Is
        it reported rather than raised, so one bad row doesn't cost the run?"""
        _run_database(
            self.database,
            [{"case_name": "No docket number here"}, {"docket_number": "A-2"}],
        )

        report = self.loader_class()(self.database).load()

        self.assertEqual(
            (report.seen, report.invalid, report.merged), (2, 1, 1)
        )
        self.assertEqual(
            Docket.objects.get().docket_number,
            "A-2",
            "The row after the bad one still merges.",
        )

    def test_merger_declining_a_scrape_is_a_rejection(self) -> None:
        """A merger's `validate` turning a scrape away is not a failure. Is it
        counted separately?"""
        loader_class = self.loader_class()

        class RejectingMerger(loader_class.merger):  # type: ignore[misc, name-defined]
            @staticmethod
            def validate(scrape: LoaderScrape) -> bool:
                return scrape.docket_number != "A-1"

        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        report = self.loader_class(merger=RejectingMerger)(
            self.database
        ).load()

        self.assertEqual(
            (report.seen, report.rejected, report.merged, report.failed),
            (2, 1, 1, 0),
        )
        self.assertEqual(Docket.objects.count(), 1)

    def test_a_row_that_raises_does_not_cost_the_run(self) -> None:
        """Each row is merged independently. Is a merge that raises counted as
        a failure while the rest of the run continues?"""
        loader_class = self.loader_class()

        class RaisingMerger(loader_class.merger):  # type: ignore[misc, name-defined]
            def merge(self) -> Any:
                if self.scrape.docket_number == "A-1":
                    raise ValueError("boom")
                return super().merge()

        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        report = self.loader_class(merger=RaisingMerger)(self.database).load()

        self.assertEqual(
            (report.seen, report.failed, report.merged), (2, 1, 1)
        )
        self.assertEqual(
            Docket.objects.get().docket_number,
            "A-2",
            "The row after the raising one still merges.",
        )

    def test_report_str_names_every_count(self) -> None:
        """The report is what an operator reads off a load. Does its summary
        state all six counts?"""
        report = LoadReport(
            seen=6, merged=1, skipped=2, invalid=1, rejected=1, failed=1
        )

        self.assertEqual(
            str(report),
            "6 seen, 1 merged, 2 skipped, 1 invalid, 1 rejected, 1 failed",
        )
