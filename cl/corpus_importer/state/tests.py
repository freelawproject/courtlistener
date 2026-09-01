import json
import logging
import sqlite3
from collections.abc import Callable, Generator, Iterable, Iterator
from contextlib import closing, contextmanager
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, ClassVar, ParamSpec, TypeVar
from unittest.mock import Mock, call, patch

from botocore.exceptions import ClientError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.db.models import Model, QuerySet
from django.test import override_settings
from pydantic import BaseModel

from cl.corpus_importer.management.commands.load_state_scrape import (
    DEFAULT_THROTTLE,
)
from cl.corpus_importer.state.ledger import PARTS as LEDGER_PARTS
from cl.corpus_importer.state.ledger import LoadLedger
from cl.corpus_importer.state.loader import (
    JKentScrapeLoader,
    LoadPhase,
    LoadReport,
    UnusableScrape,
    WaitOutcome,
)
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
from cl.corpus_importer.state.registry import LOADERS
from cl.corpus_importer.state.run_db import (
    RunDatabaseUnavailable,
    downloaded_run_database,
    scrape_bucket_client,
)
from cl.corpus_importer.state.utils import FileTally, MergeResult
from cl.corpus_importer.tasks import merge_state_scrape_row
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.lib.redis_utils import get_redis_interface
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
from cl.tests.cases import SimpleTestCase, TestCase

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
        the child, create the child pointing at the parent? The child merger
        does not declare the foreign key; the relation sets it."""
        tc = self

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], TrialCourtData]
        ):
            model: ClassVar[type[Model]] = TrialCourtData

            docket_number_trial: str = Attribute(lambda d, params: d["dn"])

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=tc.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(default=tc.docket.docket_number)
            trialcourtdata: TrialCourtData = OneToOneRelation(
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

            docket_number_trial: str = Attribute(lambda d, params: d["dn"])

        class TestMerger(Merger[dict[str, Any], None, Docket]):
            model: ClassVar[type[Model]] = Docket

            court: Court = Attribute(default=tc.court)
            source: int = Attribute(default=DocketSources.SCRAPER)
            docket_number: str = Attribute(default=tc.docket.docket_number)
            trialcourtdata: TrialCourtData = OneToOneRelation(
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

    def test_one_to_one_relation_must_be_a_one_to_one_field(self) -> None:
        """A one-to-one spec reads its direction off the model, so the field it
        names has to be one-to-one in the first place. Is a spec pointed at
        anything else refused when the merger is defined?"""

        class TestRelatedMerger(
            Merger[dict[str, str], RelatedParams[None], DocketEntry]
        ):
            model: ClassVar[type[Model]] = DocketEntry

            description: str = Attribute(lambda d, params: d["df"])

        with self.assertRaises(TypeError):

            class TestMerger(Merger[dict[str, Any], None, Docket]):
                model: ClassVar[type[Model]] = Docket

                docket_entries: list[DocketEntry] = OneToOneRelation(
                    TestRelatedMerger
                )

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


def _run_database(path: Path, payloads: list[dict[str, Any] | str]) -> None:
    """Write a minimal stand-in for a jkent run database.

    Only the columns `JKentScrapeLoader` reads are created, since the loader's
    contract is with the `results` table rather than with the whole schema.

    :param path: Where to write the database.
    :param payloads: One entry per row. A dict is serialized; a string is
        stored as given, so a test can write a blob that will not decode."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "CREATE TABLE results ("
            "  id INTEGER PRIMARY KEY,"
            "  data_json VARCHAR NOT NULL"
            ")"
        )
        connection.executemany(
            "INSERT INTO results (data_json) VALUES (?)",
            [
                (payload if isinstance(payload, str) else json.dumps(payload),)
                for payload in payloads
            ],
        )
        connection.commit()


class LoaderScrape(BaseModel):
    """The scrape a `JKentScrapeLoader` test subclass validates rows into."""

    docket_number: str
    case_name: str = ""


class LoaderTestCase(TestCase):
    """A run database in a temporary directory and a loader over it.

    The loader is court-agnostic, so its tests exercise it through a throwaway
    scrape model and merger rather than through any one state's loader.

    Celery runs eagerly under test, so a load's merges happen inline as it
    dispatches them and its ledger is full by the time it verifies. The ledger
    and the checkpoint go to the real Redis, since the point of both is that
    they outlive the process that wrote them.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.court = CourtFactory.create()

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "run.db"
        self.key = f"state_scrape_load:test:{self.id()}"
        self.redis = get_redis_interface("CACHE")
        self.clear_run_keys()
        self.addCleanup(self.clear_run_keys)

    def clear_run_keys(self, key: str | None = None) -> None:
        """Take away a run's checkpoint and every part of its ledger.

        :param key: The run key to clear, defaulting to the test's own. A load
            left to key itself off the run database needs its own cleanup.
        """
        key = key or self.key
        self.redis.delete(key, *(f"{key}:{part}" for part in LEDGER_PARTS))

    def ledger(self) -> LoadLedger:
        """The ledger the test's loads report into."""
        return LoadLedger(self.key)

    def loader_class(self, **attributes: Any) -> type[JKentScrapeLoader[Any]]:
        """A loader over the test database, merging into `Docket`.

        The class is put in the registry for the test's lifetime, because a
        merge task is handed a loader's name and looks the class back up by
        it -- a loader nothing has registered cannot be merged.

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

        loader: type[JKentScrapeLoader[Any]] = type(
            "TestLoader",
            (JKentScrapeLoader,),
            {
                "name": "test",
                "query": "SELECT data_json FROM results ORDER BY id",
                "scrape_model": LoaderScrape,
                "merger": TestMerger,
            }
            | attributes,
        )
        LOADERS[loader.name] = loader
        self.addCleanup(LOADERS.pop, loader.name, None)
        return loader

    def loader(
        self,
        loader_class: type[JKentScrapeLoader[Any]] | None = None,
        **kwargs: Any,
    ) -> JKentScrapeLoader[Any]:
        """A loader over the test database, keeping a ledger by default.

        Neither wait sleeps by default. Celery runs eagerly here, so the
        merges are already done and the ledger already full; anything a single
        pass finds outstanding really is outstanding for good, which is what a
        zero `in_flight_time` says. Tests that want the other exit set
        `in_flight_time` high and leave `verify_timeout` at zero.

        :param loader_class: The class to build, defaulting to a fresh
            `loader_class()`.
        :param kwargs: Passed through to the loader.
        :return: The loader.
        """
        kwargs.setdefault("run_key", self.key)
        kwargs.setdefault("in_flight_time", 0)
        kwargs.setdefault("verify_timeout", 0)
        return (loader_class or self.loader_class())(self.database, **kwargs)


class JKentScrapeLoaderTest(LoaderTestCase):
    """Tests for the generic jkent run-database loader."""

    def test_missing_database(self) -> None:
        """Is a run database that isn't there reported as such, rather than
        counted as an empty run?"""
        loader = self.loader()

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

        report = self.loader().load()

        self.assertEqual((report.seen, report.dispatched), (2, 2))
        self.assertEqual((report.merged, report.failed), (2, 0))
        self.assertEqual((report.invalid, report.refused), (0, 0))
        self.assertTrue(report.accounted_for)
        self.assertEqual(report.creates, {"Docket": 2})
        self.assertEqual(
            set(Docket.objects.values_list("docket_number", flat=True)),
            {"A-1", "A-2"},
        )

    def test_every_row_goes_to_the_queue_in_its_own_task(self) -> None:
        """Merging a docket per task is what lets one that fails cost only
        itself. Is one task dispatched per row, carrying the row's own
        payload?"""
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        with patch(
            "cl.corpus_importer.tasks.merge_state_scrape_row.si"
        ) as task:
            self.loader(ingest_queue="batch2", verify=False).load()

        self.assertEqual(
            [call.kwargs["row"] for call in task.call_args_list], [1, 2]
        )
        self.assertEqual(
            [
                json.loads(call.kwargs["payload"])["docket_number"]
                for call in task.call_args_list
            ],
            ["A-1", "A-2"],
        )
        task.return_value.set.assert_called_with(queue="batch2")

    def test_scrapes_yields_without_writing(self) -> None:
        """`scrapes()` is the seam for inspecting a run. Does it produce the
        validated scrapes and leave the database alone?"""
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        scrapes = list(self.loader().scrapes())

        self.assertEqual([s.docket_number for s in scrapes], ["A-1", "A-2"])
        self.assertFalse(Docket.objects.exists())

    def test_limit_stops_the_run_early(self) -> None:
        """Does `limit` stop the load after that many rows?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        report = self.loader(limit=2).load()

        self.assertEqual((report.seen, report.merged), (2, 2))
        self.assertEqual(Docket.objects.count(), 2)

    def test_limit_of_zero_loads_nothing(self) -> None:
        """A limit computed at runtime can come out zero. Does that load no
        rows at all, rather than the one row an off-by-one would let through?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        report = self.loader(limit=0).load()

        self.assertEqual((report.seen, report.dispatched), (0, 0))
        self.assertFalse(Docket.objects.exists())

    def test_normalize_returning_none_is_invalid(self) -> None:
        """`normalize` returning `None` is the loader's own judgment that there
        is nothing to do with a row. Is it counted as invalid, and left
        undispatched?"""

        def normalize(
            self: Any, payload: dict[str, Any], row: sqlite3.Row
        ) -> dict[str, Any] | None:
            return None if payload["docket_number"] == "A-1" else payload

        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        report = self.loader(self.loader_class(normalize=normalize)).load()

        self.assertEqual(
            (report.seen, report.invalid, report.dispatched, report.merged),
            (2, 1, 1, 1),
        )
        self.assertEqual(report.refused, 0)
        self.assertEqual(Docket.objects.count(), 1)

    def test_normalize_raising_unusable_scrape_is_refused(self) -> None:
        """`UnusableScrape` says the run needs looking at. Is the row counted
        as refused and never dispatched, since merging it is exactly what the
        loader objected to?"""

        def normalize(
            self: Any, payload: dict[str, Any], row: sqlite3.Row
        ) -> dict[str, Any] | None:
            raise UnusableScrape(f"{payload['docket_number']} is unusable")

        _run_database(self.database, [{"docket_number": "A-1"}])

        report = self.loader(self.loader_class(normalize=normalize)).load()

        self.assertEqual(
            (report.seen, report.refused, report.dispatched), (1, 1, 0)
        )
        self.assertEqual(
            (report.invalid, report.merged, report.failed), (0, 0, 0)
        )
        self.assertFalse(Docket.objects.exists())

    def test_payload_that_does_not_fit_the_model_is_invalid(self) -> None:
        """A payload the scrape model rejects usually means scraper drift. Is
        it reported rather than raised, so one bad row doesn't cost the run?"""
        _run_database(
            self.database,
            [{"case_name": "No docket number here"}, {"docket_number": "A-2"}],
        )

        report = self.loader().load()

        self.assertEqual(
            (report.seen, report.invalid, report.merged), (2, 1, 1)
        )
        self.assertEqual(
            Docket.objects.get().docket_number,
            "A-2",
            "The row after the bad one still merges.",
        )

    def test_a_payload_that_will_not_decode_is_invalid(self) -> None:
        """A scrape that stopped mid-write leaves a truncated blob behind. Is
        it counted rather than raised, so the rest of the run still loads?"""
        _run_database(
            self.database,
            ['{"docket_number": "A-1', {"docket_number": "A-2"}],
        )

        report = self.loader().load()

        self.assertEqual(
            (report.seen, report.invalid, report.merged, report.failed),
            (2, 1, 1, 0),
        )
        self.assertEqual(
            Docket.objects.get().docket_number,
            "A-2",
            "The row after the undecodable one still merges.",
        )

    def test_a_bad_row_is_named_in_the_log(self) -> None:
        """A count of bad rows says something drifted; only the row number
        says where to go and look, and it is what `--start-row` would need to
        reach that row again. Does the log carry it?"""
        _run_database(
            self.database,
            [
                {"docket_number": "A-1"},
                '{"docket_number": "A-2',
                {"docket_number": "A-3"},
            ],
        )
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable)

        with self.assertLogs(
            "cl.corpus_importer.state.loader", "ERROR"
        ) as logs:
            self.loader().load()

        self.assertIn("row 2 of run.db", logs.output[0])

    def test_a_bad_payload_is_named_by_its_docket_where_it_has_one(
        self,
    ) -> None:
        """A row number gets you back to the row, but a docket number is what
        anybody actually searches for. Does a validation failure carry both
        where the payload decoded far enough to have a docket number, and fall
        back to the row number where it did not?"""
        for label, payload, expected in (
            (
                "has a docket number",
                {"docket_number": "A-1", "case_name": 7},
                "A-1 (row 1) of run.db",
            ),
            (
                "has none to give",
                {"case_name": "No docket number here"},
                "row 1 of run.db",
            ),
        ):
            with self.subTest(label):
                self.database.unlink(missing_ok=True)
                _run_database(self.database, [payload])
                logging.disable(logging.NOTSET)
                self.addCleanup(logging.disable)

                with self.assertLogs(
                    "cl.corpus_importer.state.loader", "ERROR"
                ) as logs:
                    report = self.loader().load()

                self.assertEqual(report.invalid, 1)
                self.assertIn(expected, logs.output[0])
                self.assertIn("LoaderScrape", logs.output[0])

    def test_merger_declining_a_scrape_is_a_failure(self) -> None:
        """A merger refuses a scrape in its own `validate`, which it reports as
        a failure. Does the row come back from the queue counted as one, with
        the rest of the run left to merge?"""

        class RejectingMerger(self.loader_class().merger):  # type: ignore[misc, name-defined]
            @staticmethod
            def validate(scrape: LoaderScrape) -> bool:
                return scrape.docket_number != "A-1"

        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        report = self.loader(self.loader_class(merger=RejectingMerger)).load()

        self.assertEqual(
            (report.seen, report.dispatched, report.merged, report.failed),
            (2, 2, 1, 1),
        )
        self.assertEqual(
            (report.rejected, report.errored),
            (1, 0),
            "The merge ran and would not have the scrape, which is the "
            "scraper's problem rather than a row to re-run.",
        )
        self.assertTrue(report.accounted_for)
        self.assertEqual(Docket.objects.count(), 1)

    def test_a_row_that_raises_does_not_cost_the_run(self) -> None:
        """Each row is merged in a task of its own. Is a merge that raises
        recorded as a failure while the rest of the run continues?"""

        class RaisingMerger(self.loader_class().merger):  # type: ignore[misc, name-defined]
            def merge(self) -> Any:
                if self.scrape.docket_number == "A-1":
                    raise ValueError("boom")
                return super().merge()

        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        with patch.object(merge_state_scrape_row, "max_retries", 0):
            report = self.loader(
                self.loader_class(merger=RaisingMerger)
            ).load()

        self.assertEqual(
            (report.seen, report.failed, report.merged), (2, 1, 1)
        )
        self.assertTrue(
            report.accounted_for,
            "A row that failed still reported an outcome.",
        )
        self.assertEqual(
            Docket.objects.get().docket_number,
            "A-2",
            "The row after the raising one still merges.",
        )

    def test_a_merge_out_of_retries_is_recorded_rather_than_dropped(
        self,
    ) -> None:
        """Celery says nothing when a task's retries run out, which is the
        whole reason for the ledger. Is the row written off as failed rather
        than left looking like it never ran?"""

        class RefusingMerger(self.loader_class().merger):  # type: ignore[misc, name-defined]
            def merge(self) -> Any:
                raise DatabaseError("the database is having none of it")

        _run_database(self.database, [{"docket_number": "A-1"}])
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable)

        with (
            patch.object(merge_state_scrape_row, "max_retries", 0),
            self.assertLogs("cl.corpus_importer.tasks", "ERROR") as logs,
        ):
            report = self.loader(
                self.loader_class(merger=RefusingMerger)
            ).load()

        self.assertEqual((report.dispatched, report.failed), (1, 1))
        self.assertEqual(
            (report.rejected, report.errored),
            (0, 1),
            "No merge reached a verdict, so this is a row to re-run rather "
            "than a scrape to go and fix.",
        )
        self.assertTrue(
            report.accounted_for,
            "The row was written off, not left looking undispatched.",
        )
        self.assertIn("giving up", logs.output[0])
        self.assertEqual(
            logs.records[0].fingerprint,  # type: ignore[attr-defined]
            ["test", LoadPhase.MERGE],
            "Filed under the loader's own Sentry issue for merge failures.",
        )

    def test_a_merger_bug_is_not_mistaken_for_a_dropped_task(self) -> None:
        """An exception the task does not expect is a bug in the merger, not a
        broker that lost a message. Left to propagate it would take its row
        with it, and reconciliation would report the docket as one celery
        dropped -- sending somebody to the broker for a fault in the code. Is
        it written off as a merge failure instead?"""

        class BuggyMerger(self.loader_class().merger):  # type: ignore[misc, name-defined]
            def merge(self) -> Any:
                raise AttributeError("the merger has a typo in it")

        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable)

        with self.assertLogs("cl.corpus_importer.tasks", "ERROR") as logs:
            report = self.loader(self.loader_class(merger=BuggyMerger)).load()
            # Asserted inside the block so that a regression fails on the
            # mis-attribution rather than on the log line that goes with it.
            self.assertEqual(
                report.missing_count,
                0,
                "Celery lost nothing. The merger raised, and that is a "
                "different problem with a different fix.",
            )
            self.assertEqual((report.dispatched, report.failed), (2, 2))
            self.assertTrue(report.accounted_for)

        self.assertIn("raised AttributeError", logs.output[0])
        self.assertEqual(
            logs.records[0].fingerprint,  # type: ignore[attr-defined]
            ["test", LoadPhase.MERGE],
        )

    def test_a_merge_that_never_reports_is_missing(self) -> None:
        """A worker killed mid-merge takes its task with it and tells no one.
        Does the load name the row rather than reporting a clean run?"""
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        # Nothing runs the task, which is what a lost message looks like from
        # here: the ledger holds the dispatch and never gets an outcome.
        with patch("cl.corpus_importer.tasks.merge_state_scrape_row.si"):
            report = self.loader(verify_timeout=0).load()

        self.assertEqual((report.dispatched, report.merged), (2, 0))
        self.assertFalse(report.accounted_for)
        self.assertEqual(report.missing_count, 2)
        self.assertEqual(report.missing, {1: "A-1", 2: "A-2"})
        self.assertEqual(report.merge_wait, WaitOutcome.STALLED)
        self.assertTrue(report.dropped)

    def test_dropped_rows_get_their_own_sentry_issue(self) -> None:
        """A dropped task is the one failure nothing else in the system
        reports, so it has to be findable on its own rather than mixed in with
        the merges that failed loudly. Is it filed under its own fingerprint,
        keyed on the loader rather than the run?"""
        _run_database(self.database, [{"docket_number": "A-1"}])
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable)

        with (
            patch("cl.corpus_importer.tasks.merge_state_scrape_row.si"),
            self.assertLogs(
                "cl.corpus_importer.state.loader", "ERROR"
            ) as logs,
        ):
            self.loader(verify_timeout=0).load()

        self.assertEqual(
            logs.records[0].fingerprint,  # type: ignore[attr-defined]
            ["test", LoadPhase.RECONCILIATION],
        )
        self.assertNotIn(
            "run.db",
            str(logs.records[0].fingerprint),  # type: ignore[attr-defined]
            "Fingerprinting by run database would open a fresh Sentry issue "
            "every hourly load.",
        )

    def test_a_settled_row_leaves_nothing_behind(self) -> None:
        """The ledger is what keeps a long run from costing Redis a row per
        docket. Does a row that reported back take itself off, whichever way
        it went, leaving only counters?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        report = self.loader().load()

        self.assertEqual(report.merged, 5)
        self.assertEqual(
            self.redis.hlen(f"{self.key}:pending"),
            0,
            "Five merged dockets cost the ledger no rows at all.",
        )
        self.assertEqual(self.ledger().totals().merged, 5, "Only the count.")

    def test_file_counts_share_the_run_s_counter_hash(self) -> None:
        """A load moves a file per document, so anything the ledger spent per
        file would dwarf what it spends per docket. Do the file tallies ride
        along in the counter hash the row's own outcome is written to, rather
        than taking a key or a round trip of their own?"""
        ledger = self.ledger()
        ledger.dispatched(1, "A-1")

        ledger.merged(1, MergeResult(files=FileTally(moved=2, missing=1)))

        self.assertEqual(
            set(self.redis.keys(f"{self.key}:*")),
            {f"{self.key}:counts"},
            "The file counts cost the ledger no key of their own.",
        )
        self.assertEqual(ledger.totals().files, FileTally(moved=2, missing=1))

    def test_a_merge_that_moved_no_files_counts_none(self) -> None:
        """Most loaders publish nothing at all, and most merges of the one that
        does move no files. Is the usual merge left writing exactly what it
        wrote before?"""
        ledger = self.ledger()
        ledger.dispatched(1, "A-1")

        ledger.merged(1, MergeResult())

        self.assertEqual(
            set(self.redis.hkeys(f"{self.key}:counts")),
            {"dispatched", "merged"},
            "Nothing was moved, so nothing counts it.",
        )
        self.assertFalse(ledger.totals().files)

    def test_file_counts_add_up_across_rows(self) -> None:
        """The tally spans the run rather than any one docket. Does each row's
        merge add to it?"""
        ledger = self.ledger()

        for row, files in enumerate(
            (
                FileTally(moved=3),
                FileTally(moved=1, failed=2),
                FileTally(missing=1),
            )
        ):
            ledger.dispatched(row, f"A-{row}")
            ledger.merged(row, MergeResult(files=files))

        self.assertEqual(
            ledger.totals().files, FileTally(moved=4, missing=1, failed=2)
        )

    def test_a_rejected_row_still_counts_the_files_it_moved(self) -> None:
        """Publishing happens before the write that can fail, so a merge that
        went on to be rejected has still left files in the public bucket. Are
        they counted, rather than lost with the row?"""
        ledger = self.ledger()
        ledger.dispatched(1, "A-1")

        ledger.rejected(
            1,
            MergeResult(failures={"Docket": [None]}, files=FileTally(moved=1)),
        )

        self.assertEqual(ledger.totals().files, FileTally(moved=1))
        self.assertEqual(ledger.totals().rejected, 1)

    def test_a_falling_count_is_waited_on(self) -> None:
        """A count still coming down means somebody is working on our rows.
        Does the load keep waiting, and poll the count rather than dragging
        every pending row across on each pass?"""
        loader = self.loader(in_flight_time=600, verify_timeout=600)
        counts = [3, 2, 1, 0]

        with (
            patch.object(LoadLedger, "outstanding_count", side_effect=counts),
            patch.object(LoadLedger, "outstanding") as rows,
            patch("cl.corpus_importer.state.loader.time.sleep") as sleep,
        ):
            outstanding, wait = loader._await_drain(
                self.ledger().outstanding_count, poll=1, work="merges"
            )

        self.assertEqual((outstanding, wait), (0, WaitOutcome.DRAINED))
        self.assertEqual(sleep.call_count, len(counts) - 1)
        rows.assert_not_called()

    def test_a_steady_count_is_a_stall(self) -> None:
        """A count that stops moving says the work is gone. Is that reported
        as a stall rather than waited out to the timeout?"""
        loader = self.loader(in_flight_time=0, verify_timeout=600)

        with patch.object(LoadLedger, "outstanding_count", return_value=4):
            outstanding, wait = loader._await_drain(
                self.ledger().outstanding_count, poll=1, work="merges"
            )

        self.assertEqual((outstanding, wait), (4, WaitOutcome.STALLED))
        self.assertTrue(wait.conclusive)

    def test_a_count_still_moving_at_the_deadline_times_out(self) -> None:
        """Giving up on a queue that was still working is not a finding. Is it
        told apart from a stall?"""
        loader = self.loader(in_flight_time=600, verify_timeout=0)

        with patch.object(LoadLedger, "outstanding_count", return_value=4):
            outstanding, wait = loader._await_drain(
                self.ledger().outstanding_count, poll=1, work="merges"
            )

        self.assertEqual((outstanding, wait), (4, WaitOutcome.TIMED_OUT))
        self.assertFalse(
            wait.conclusive, "Says nothing about the work still left."
        )

    def test_skipping_verification_reports_only_what_was_dispatched(
        self,
    ) -> None:
        """A load meant to be left running should not sit waiting on its
        queues. Does `verify=False` return the dispatch counts alone?"""
        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        report = self.loader(verify=False).load()

        self.assertEqual((report.seen, report.dispatched), (2, 2))
        self.assertEqual(
            (report.merged, report.failed),
            (0, 0),
            "Nothing was read back out of the ledger.",
        )
        self.assertEqual(
            Docket.objects.count(), 2, "The merges ran all the same."
        )

    def test_a_load_given_no_run_key_still_keeps_a_ledger(self) -> None:
        """Every load is worth being able to check up on, whether or not
        anyone meant to resume it. Does a loader built without a run key key
        one off the run database and verify itself out of it?"""
        # The derived key names the run database, and the suite runs in
        # parallel against one Redis, so this run needs a name of its own.
        self.database = self.database.with_name(f"{self.id()}.db")
        _run_database(self.database, [{"docket_number": "A-1"}])
        loader = self.loader(run_key=None)
        self.addCleanup(self.clear_run_keys, loader.run_key)

        report = loader.load()

        self.assertEqual(
            loader.run_key, f"state_scrape_load:test:{self.database.name}"
        )
        self.assertEqual(
            (report.dispatched, report.merged),
            (1, 1),
            "Read back out of the ledger it keyed for itself.",
        )
        self.assertEqual(Docket.objects.count(), 1)

    def test_report_str_names_every_count(self) -> None:
        """The report is what an operator reads off a load. Does its summary
        state every count, keeping the two ways a merge fails apart?"""
        report = LoadReport(
            seen=8,
            dispatched=5,
            merged=2,
            rejected=1,
            errored=1,
            invalid=2,
            refused=1,
            missing_count=1,
            missing={4: "A-4"},
        )

        self.assertEqual(
            str(report),
            "8 seen, 5 dispatched, 2 merged, 1 rejected, 1 errored, "
            "2 invalid, 1 refused, 1 missing",
        )
        self.assertEqual(report.failed, 2, "Both, for a caller wanting one.")

    def test_db_delay_waits_between_rows(self) -> None:
        """A long load has to leave the queue room to drain. Does `db_delay`
        wait after each row?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(3)],
        )

        with patch("cl.corpus_importer.state.loader.time.sleep") as sleep:
            self.loader(db_delay=0.25).load()

        self.assertEqual(sleep.call_args_list, [call(0.25)] * 3)

    def test_no_db_delay_does_not_wait(self) -> None:
        """The default is to run flat out. Does a zero delay skip the wait
        rather than sleeping zero seconds three thousand times?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(3)],
        )

        with patch("cl.corpus_importer.state.loader.time.sleep") as sleep:
            self.loader().load()

        sleep.assert_not_called()

    def test_both_queues_get_a_throttle(self) -> None:
        """Merges dispatch their own extraction, so a load can bury either
        queue. Is a throttle built for each one it was given a rate for?"""
        with patch(
            "cl.corpus_importer.state.loader.CeleryThrottle"
        ) as throttle_class:
            self.loader(
                ingest_throttle=4,
                ingest_queue="batch1",
                extraction_throttle=6,
                extraction_queue="batch2",
            )

        self.assertEqual(
            throttle_class.call_args_list,
            [
                call(min_items=4, queue_name="batch1"),
                call(min_items=6, queue_name="batch2"),
            ],
        )

    def test_every_throttle_gets_its_say_before_a_row_goes_out(self) -> None:
        """A throttle only holds a load back if it is consulted. Does each one
        get asked before every dispatch?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(3)],
        )
        with patch(
            "cl.corpus_importer.state.loader.CeleryThrottle"
        ) as throttle_class:
            loader = self.loader(ingest_throttle=4, extraction_throttle=6)

        loader.load()

        self.assertEqual(throttle_class.return_value.maybe_wait.call_count, 6)

    def test_skipping_extraction_leaves_its_queue_unthrottled(self) -> None:
        """Building a throttle polls the celery queue. Does a load dispatching
        no extraction leave that queue alone?"""
        loader = self.loader(extract=False, extraction_throttle=6)

        self.assertEqual(loader.throttles, [])

    def test_no_throttle_builds_none(self) -> None:
        """Does a load that asked for no throttling poll no queues?"""
        self.assertEqual(self.loader().throttles, [])


class JKentScrapeLoaderExtractionTest(LoaderTestCase):
    """Tests for the documents a load hands to the extraction queue.

    The document model is a stand-in here: `dispatch_extraction` only names it
    and reads rows off it. Checking that extraction actually ran takes a real
    model, and lives with the New York loader's tests.
    """

    def document_model(self) -> Any:
        """A stand-in for a state document model."""
        return Mock(__name__="Doc")

    def document(self, pk: int, dispatched: bool = True) -> Any:
        """A document row that reports whether extraction was dispatched."""
        document = Mock(pk=pk)
        document.extract.return_value = dispatched
        return document

    def test_only_documents_actually_sent_are_expected_back(self) -> None:
        """A document with no file to read is never dispatched and will never
        change status. Is it left out of what the load waits on?"""
        model = self.document_model()
        model._default_manager.filter.return_value = [
            self.document(1),
            self.document(2, dispatched=False),
        ]
        loader_class = self.loader_class(document_model=model)

        dispatched = loader_class.dispatch_extraction(
            MergeResult(creates={"Doc": {1, 2}}), "batch1"
        )

        self.assertEqual(dispatched, {1})
        model._default_manager.filter.assert_called_once_with(pk__in={1, 2})

    def test_a_loader_writing_no_documents_dispatches_nothing(self) -> None:
        """Does a loader with no document model leave extraction alone?"""
        loader_class = self.loader_class()

        self.assertEqual(
            loader_class.dispatch_extraction(
                MergeResult(creates={"Docket": {1}}), "celery"
            ),
            set(),
        )


class JKentScrapeLoaderCheckpointTest(LoaderTestCase):
    """Tests for the position a load records so a later one can resume it."""

    def setUp(self) -> None:
        super().setUp()
        patcher = patch(
            "cl.corpus_importer.state.loader.CHECKPOINT_EVERY", new=2
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def checkpoint(self) -> int:
        """The row the checkpoint names, or 0 for no checkpoint."""
        return get_last_parent_document_id_processed(self.key)

    def test_a_load_checkpoints_the_rows_it_dispatched(self) -> None:
        """A load that dies is resumed from its last checkpoint, so the
        checkpoint must never name a row the load had not reached. Does it name
        the last row it sent?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        loader = self.loader()

        # Stop the load partway, as a dying process would.
        with patch.object(
            loader, "_dispatch", side_effect=[None, None, OSError("gone")]
        ):
            with self.assertRaises(OSError):
                loader.load()

        # The checkpoint was written at the top of row 2, by which point only
        # row 1 had been dispatched. Row 2 went out after it and is dispatched
        # again on resume, which merging idempotently makes harmless -- naming
        # a row the load had not reached would not be.
        self.assertEqual(self.checkpoint(), 1)

    def test_a_checkpoint_resumes_the_rows_it_left(self) -> None:
        """A checkpoint is only worth writing if it starts the next load in
        the right place. Does resuming from one merge exactly the rest?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        log_last_document_indexed(2, self.key)

        report = self.loader(start_row=self.checkpoint()).load()

        self.assertEqual((report.seen, report.merged), (3, 3))
        self.assertEqual(
            set(Docket.objects.values_list("docket_number", flat=True)),
            {"A-2", "A-3", "A-4"},
        )

    def test_a_resumed_load_keeps_the_ledger_it_is_adding_to(self) -> None:
        """The rows a load merged before it died are in its ledger, and only
        that ledger says so. Does resuming add to it rather than wipe it?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(4)],
        )

        self.loader(limit=2).load()
        self.loader(start_row=2).load()

        self.assertEqual(self.ledger().totals().merged, 4)

    def test_a_load_starting_over_drops_the_last_one_s_ledger(self) -> None:
        """A run from the top is a fresh pass, and last time's outcomes say
        nothing about it. Are they cleared before anything is dispatched?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(3)],
        )
        self.ledger().dispatched(99, "A-99-from-a-previous-load")

        report = self.loader().load()

        self.assertEqual(report.merged, 3)
        self.assertTrue(report.accounted_for, "The stale row is gone.")

    def test_a_finished_load_clears_its_checkpoint(self) -> None:
        """A checkpoint left behind by a load that finished would send the
        next load of the same run database straight to the end, merging
        nothing. Is it dropped?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        self.loader().load()

        self.assertEqual(self.checkpoint(), 0)

    def test_a_limited_run_leaves_no_checkpoint(self) -> None:
        """A limited run stops at a row that means nothing to a full load.
        Does it neither record that position nor clear a real one?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        log_last_document_indexed(2, self.key)

        self.loader(limit=4).load()

        self.assertEqual(self.checkpoint(), 2, "The real load's position.")

    def test_a_load_given_no_key_checkpoints_under_its_own(self) -> None:
        """A load nobody named still has to be resumable. Does it checkpoint
        under the key it derived from the run database?"""
        # The derived key names the run database, and the suite runs in
        # parallel against one Redis, so this run needs a name of its own.
        self.database = self.database.with_name(f"{self.id()}.db")
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        loader = self.loader(run_key=None)
        self.addCleanup(self.clear_run_keys, loader.run_key)

        with patch(
            "cl.corpus_importer.state.loader.log_last_document_indexed"
        ) as log:
            loader.load()

        key = f"state_scrape_load:test:{self.database.name}"
        self.assertEqual(loader.checkpointing, key)
        self.assertEqual(
            [call.args[1] for call in log.call_args_list],
            [key, key],
            "Every checkpoint went to the key the load derived for itself.",
        )

    def test_a_load_survives_a_checkpoint_it_cannot_write(self) -> None:
        """A checkpoint is a convenience, not the load. Does an unreachable
        Redis cost the run its resume point and nothing more?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        with patch(
            "cl.corpus_importer.state.loader.log_last_document_indexed",
            side_effect=ConnectionError("no redis"),
        ):
            report = self.loader().load()

        self.assertEqual((report.seen, report.merged), (5, 5))


class FakeBucket:
    """Stands in for the boto3 client `downloaded_run_database` fetches with.

    Records what was asked for so a test can assert on it, and writes
    `contents` where the real client would write the object."""

    def __init__(
        self,
        contents: bytes = b"SQLite format 3\x00",
        error: Exception | None = None,
    ) -> None:
        self.contents = contents
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        self.calls.append((bucket, key, destination))
        if self.error is not None:
            raise self.error
        Path(destination).write_bytes(self.contents)


@override_settings(
    AWS_STORAGE_BUCKET_NAME="scrapes",
    AWS_ACCESS_KEY_ID="key",
    AWS_SECRET_ACCESS_KEY="secret",
)
class RunDatabaseTest(SimpleTestCase):
    """Tests for fetching a run database out of the scrape bucket."""

    @contextmanager
    def download(self, bucket: FakeBucket, key: str) -> Iterator[Path]:
        """`downloaded_run_database` with `bucket` standing in for S3.

        The patch has to outlive the download, so this wraps the whole context
        rather than handing one back."""
        with patch(
            "cl.corpus_importer.state.run_db.scrape_bucket_client",
            return_value=bucket,
        ):
            with downloaded_run_database(key) as database:
                yield database

    def test_downloads_the_key_to_a_temporary_file(self) -> None:
        """Does the database arrive on local disk, under its own name, from
        the configured bucket?"""
        bucket = FakeBucket(contents=b"a run")

        with self.download(bucket, "nycourts_gov/2026-08-08.db") as database:
            self.assertTrue(database.exists())
            self.assertEqual(database.name, "2026-08-08.db")
            self.assertEqual(database.read_bytes(), b"a run")
            self.assertEqual(
                bucket.calls,
                [("scrapes", "nycourts_gov/2026-08-08.db", str(database))],
            )

    def test_takes_the_download_away_afterwards(self) -> None:
        """A run database is hundreds of megabytes. Is the temporary copy
        cleaned up when the caller is done with it?"""
        with self.download(FakeBucket(), "nycourts_gov/run.db") as database:
            self.assertTrue(database.exists())

        self.assertFalse(database.exists())
        self.assertFalse(database.parent.exists())

    def test_cleans_up_after_a_load_that_raises(self) -> None:
        """Does the copy go away even when the caller fails mid-load?"""
        with self.assertRaises(ValueError):
            with self.download(
                FakeBucket(), "nycourts_gov/run.db"
            ) as database:
                path = database
                raise ValueError("the load blew up")

        self.assertFalse(path.exists())

    def test_reports_a_key_that_cannot_be_fetched(self) -> None:
        """A missing key, or credentials that cannot read it, is all an
        operator can act on. Is it reported with the key named?"""
        bucket = FakeBucket(
            error=ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        )

        with self.assertRaises(RunDatabaseUnavailable) as caught:
            with self.download(bucket, "nycourts_gov/nope.db"):
                pass

        self.assertIn(
            "s3://scrapes/nycourts_gov/nope.db", str(caught.exception)
        )

    def test_rejects_a_key_that_names_no_database(self) -> None:
        """Is a prefix handed over in place of a database refused before
        anything is downloaded?"""
        bucket = FakeBucket()

        with self.assertRaises(RunDatabaseUnavailable):
            with self.download(bucket, "nycourts_gov/"):
                pass

        self.assertEqual(bucket.calls, [])

    def test_client_reads_courtlistener_credentials(self) -> None:
        """Is the client built with CourtListener's own S3 credentials?"""
        with patch("cl.corpus_importer.state.run_db.boto3.client") as client:
            scrape_bucket_client()

        self.assertEqual(
            client.call_args.kwargs,
            {
                "aws_access_key_id": "key",
                "aws_secret_access_key": "secret",
            },
        )

    @override_settings(AWS_ACCESS_KEY_ID="", AWS_SECRET_ACCESS_KEY="")
    def test_unset_credentials_leave_boto3_its_own_chain(self) -> None:
        """An empty credential setting means "nothing configured here", not
        "sign anonymously" -- a deployment may be getting its credentials from
        an instance role instead. Is it passed as `None`?"""
        with patch("cl.corpus_importer.state.run_db.boto3.client") as client:
            scrape_bucket_client()

        self.assertIsNone(client.call_args.kwargs["aws_access_key_id"])
        self.assertIsNone(client.call_args.kwargs["aws_secret_access_key"])


@contextmanager
def _fake_download(key: str) -> Generator[Path]:
    """Stand in for the fetch out of the scrape bucket.

    Yields a path nothing reads: the command's argument handling is what these
    tests are about, and the loader under it is a mock."""
    yield Path("/nonexistent") / key


class LoadStateScrapeCommandTest(SimpleTestCase):
    """Tests for how the load command reads its arguments."""

    CHECKPOINT = 120

    def setUp(self) -> None:
        self.loader = Mock()
        self.loader.return_value.load.return_value = LoadReport()
        self.output = StringIO()
        self.errors = StringIO()
        for target, replacement in (
            ("downloaded_run_database", _fake_download),
            (
                "get_last_parent_document_id_processed",
                Mock(return_value=self.CHECKPOINT),
            ),
        ):
            patcher = patch(
                "cl.corpus_importer.management.commands."
                f"load_state_scrape.{target}",
                replacement,
            )
            patcher.start()
            self.addCleanup(patcher.stop)
        registry = patch.dict(LOADERS, {"nycoa": self.loader}, clear=True)
        registry.start()
        self.addCleanup(registry.stop)

    def load(self, *arguments: str) -> None:
        """Run the command over a stand-in run database."""
        call_command(
            "load_state_scrape",
            "nycoa",
            "nycourts_gov/2026-08-08.db",
            *arguments,
            stdout=self.output,
            stderr=self.errors,
        )

    def started_at(self) -> int:
        """The row the load the command built was told to start from."""
        return self.loader.call_args.kwargs["start_row"]

    def test_start_row_and_auto_resume_are_contradictory(self) -> None:
        """Each says to start somewhere the other says not to, and honouring
        either one quietly does what the other asked against. Is the operator
        made to pick, rather than one of them being guessed at?"""
        with self.assertRaises(CommandError) as raised:
            self.load("--auto-resume", "--start-row", "5")

        message = str(raised.exception)
        self.assertIn(
            "--start-row 5",
            message,
            "The message quotes back the value that has to go.",
        )
        self.assertIn("--auto-resume", message)
        self.loader.assert_not_called()

    def test_both_queues_are_throttled_by_default(self) -> None:
        """An unthrottled load puts a whole run's dockets in the broker at
        once, and every other import command paces itself out of the box. Do
        the queues start throttled here too, at the same figure?"""
        self.load()

        kwargs = self.loader.call_args.kwargs
        self.assertEqual(kwargs["ingest_throttle"], DEFAULT_THROTTLE)
        self.assertEqual(kwargs["extraction_throttle"], DEFAULT_THROTTLE)
        self.assertEqual(
            DEFAULT_THROTTLE,
            5,
            "The figure --throttle-min-items defaults to for SCOTUS, Texas "
            "and Florida.",
        )

    def test_throttling_can_still_be_turned_off(self) -> None:
        """A backfill wants throughput over a clear queue. Is zero honoured
        rather than falling back to the default?"""
        self.load("--ingest-throttle", "0")

        self.assertEqual(self.loader.call_args.kwargs["ingest_throttle"], 0)

    def test_auto_resume_starts_from_the_checkpoint(self) -> None:
        """Does --auto-resume on its own pick the load up where the last one
        left off?"""
        self.load("--auto-resume")

        self.assertEqual(self.started_at(), self.CHECKPOINT)

    def test_start_row_alone_is_passed_through(self) -> None:
        """Does --start-row on its own start the load where it says?"""
        self.load("--start-row", "5")

        self.assertEqual(self.started_at(), 5)

    def test_a_zero_start_row_does_not_stand_in_the_way(self) -> None:
        """--start-row defaults to zero, which asks for nothing. Is it left
        out of the objection?"""
        self.load("--auto-resume", "--start-row", "0")

        self.assertEqual(self.started_at(), self.CHECKPOINT)

    def test_dropped_dockets_are_named(self) -> None:
        """Rows celery lost are the whole reason the load verifies itself.
        Does the command say which ones, rather than leaving them in the log?"""
        self.loader.return_value.load.return_value = LoadReport(
            seen=2,
            dispatched=2,
            merged=1,
            missing_count=1,
            missing={7: "APL-2024-00177"},
        )

        self.load()

        # On stderr, so a scheduled run's mail catches it without the counts
        # around it.
        errors = self.errors.getvalue()
        self.assertIn("never reported back", errors)
        self.assertIn("row 7: APL-2024-00177", errors)
        self.assertNotIn("never reported back", self.output.getvalue())

    def test_skip_load_checks_a_stored_ledger_without_a_download(
        self,
    ) -> None:
        """A run that gave up while its queues were still moving has to be
        settleable later. Does --skip-load do that from the ledger alone,
        without fetching a run database that can run to hundreds of
        megabytes?"""
        self.loader.return_value.verify_only.return_value = LoadReport(
            rows_read=False, dispatched=9, merged=9
        )

        with patch(
            "cl.corpus_importer.management.commands."
            "load_state_scrape.downloaded_run_database"
        ) as download:
            self.load("--skip-load")

        download.assert_not_called()
        self.loader.return_value.verify_only.assert_called_once_with()
        self.loader.return_value.load.assert_not_called()

    def test_skip_load_does_not_claim_rows_it_never_read(self) -> None:
        """Printing `0 invalid` for a run whose rows were never opened reads as
        "no bad rows" when it means "did not look". Are those counts left out,
        and said to be left out?"""
        self.loader.return_value.verify_only.return_value = LoadReport(
            rows_read=False, dispatched=9, merged=8, rejected=1
        )

        self.load("--skip-load")

        written = self.output.getvalue()
        summary = written.splitlines()[0]
        self.assertEqual(
            summary, "9 dispatched, 8 merged, 1 rejected, 0 errored, 0 missing"
        )
        self.assertNotIn("seen", summary)
        self.assertNotIn("invalid", summary)
        self.assertIn("no run database was opened", written)

    def test_skipping_both_phases_leaves_nothing_to_do(self) -> None:
        """The two flags each skip one half of the command, and are otherwise
        free to combine. Is the operator made to pick when they skip both?"""
        with self.assertRaises(CommandError) as raised:
            self.load("--skip-load", "--skip-verification")

        message = str(raised.exception)
        self.assertIn("--skip-load", message)
        self.assertIn("--skip-verification", message)
        self.loader.assert_not_called()

    def test_counts_line_up_under_one_another(self) -> None:
        """A run touching several models is read down a column. Are the model
        names and their counts padded to a common width?"""
        self.loader.return_value.load.return_value = LoadReport(
            seen=2,
            dispatched=2,
            merged=2,
            creates={"Docket": 2, "OpinionCluster": 11},
            updates={"Docket": 105},
        )

        self.load()

        written = self.output.getvalue().splitlines()
        self.assertEqual(
            written[1:],
            [
                "  Created Docket            2",
                "  Created OpinionCluster   11",
                "  Updated Docket          105",
            ],
        )

    def test_a_timed_out_wait_is_not_reported_as_lost_work(self) -> None:
        """Giving up on a queue that was still coming down is not a finding.
        Does the output name the timeout as the reason it stopped watching,
        and point at the flag that settles it?"""
        self.loader.return_value.load.return_value = LoadReport(
            seen=9,
            dispatched=9,
            merged=4,
            missing_count=5,
            missing={5: "APL-2024-00177"},
            merge_wait=WaitOutcome.TIMED_OUT,
        )

        self.load()

        errors = self.errors.getvalue()
        self.assertIn("never reported back yet -- timed out", errors)
        self.assertIn("--skip-load", errors)

    def test_a_stalled_wait_is_reported_as_lost_work(self) -> None:
        """A queue that stopped moving is a finding. Does the output say so
        rather than hedging?"""
        self.loader.return_value.load.return_value = LoadReport(
            seen=9,
            dispatched=9,
            merged=4,
            missing_count=5,
            missing={5: "APL-2024-00177"},
            merge_wait=WaitOutcome.STALLED,
        )

        self.load()

        errors = self.errors.getvalue()
        self.assertIn("never reported back -- queue stalled", errors)
        self.assertNotIn("--skip-load", errors)

    def test_the_files_a_run_moved_are_written_out(self) -> None:
        """A load that publishes files does work no row count shows. Is what
        became of them written where the model counts are?"""
        self.loader.return_value.load.return_value = LoadReport(
            seen=2, dispatched=2, merged=2, files=FileTally(moved=17)
        )

        self.load()

        self.assertIn(
            "Files: 17 moved, 0 not found, 0 could not be moved",
            self.output.getvalue(),
        )
        self.assertEqual(
            self.errors.getvalue(),
            "",
            "Every file landed, so there is nothing to warn about.",
        )

    def test_files_that_never_reached_the_bucket_are_warned_about(
        self,
    ) -> None:
        """A document pointing at nothing serves nothing and extracts nothing,
        which no other count in the report shows. Does the warning say how many
        re-running the load would mend, and how many it would not?"""
        self.loader.return_value.load.return_value = LoadReport(
            seen=2,
            dispatched=2,
            merged=2,
            files=FileTally(moved=5, missing=2, failed=3),
        )

        self.load()

        errors = self.errors.getvalue()
        self.assertIn("5 files never reached the public bucket", errors)
        self.assertIn("the 3 the bucket refused", errors)
        self.assertIn("the 2 it could not find", errors)

    def test_a_run_that_moved_no_files_says_nothing_about_them(self) -> None:
        """Most loaders publish nothing at all. Is the files line held back
        rather than printing three zeroes on every load?"""
        self.loader.return_value.load.return_value = LoadReport(
            seen=2, dispatched=2, merged=2
        )

        self.load()

        self.assertNotIn("Files:", self.output.getvalue())

    def test_an_unverified_load_does_not_claim_a_clean_run(self) -> None:
        """A load that skipped verification knows only what it dispatched.
        Does it say so instead of reporting nothing merged?"""
        self.loader.return_value.load.return_value = LoadReport(
            seen=2, dispatched=2
        )

        self.load("--skip-verification")

        self.assertIn("Verification was skipped", self.errors.getvalue())
