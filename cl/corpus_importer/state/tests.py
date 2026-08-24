import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, ClassVar, ParamSpec, TypeVar
from unittest.mock import Mock, call, patch

from botocore.exceptions import ClientError
from django.db import connection
from django.db.models import Model, QuerySet
from django.test import override_settings
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
    ThroughParameters,
)
from cl.corpus_importer.state.run_db import (
    RunDatabaseUnavailable,
    downloaded_run_database,
    scrape_bucket_client,
)
from cl.corpus_importer.state.utils import MergeResult
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


class JKentScrapeLoaderTest(LoaderTestCase):
    """Tests for the generic jkent run-database loader."""

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
        self.assertEqual((report.invalid, report.failed), (0, 0))
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

    def test_limit_of_zero_loads_nothing(self) -> None:
        """A limit computed at runtime can come out zero. Does that load no
        rows at all, rather than the one row an off-by-one would let through?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        report = self.loader_class()(self.database, limit=0).load()

        self.assertEqual((report.seen, report.merged), (0, 0))
        self.assertFalse(Docket.objects.exists())

    def test_dry_run_reports_a_real_merge_but_writes_nothing(self) -> None:
        """A dry run runs the merge in full and rolls it back. Is the report
        real while the database is left untouched?"""
        _run_database(self.database, [{"docket_number": "A-1"}])

        report = self.loader_class()(self.database, dry_run=True).load()

        self.assertEqual((report.seen, report.merged), (1, 1))
        self.assertIn("Docket", report.result.creates)
        self.assertFalse(Docket.objects.exists())

    def test_normalize_returning_none_is_invalid(self) -> None:
        """`normalize` returning `None` is the loader's own judgment that there
        is nothing to do with a row. Is it counted as invalid, not failed?"""

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
            (report.seen, report.invalid, report.merged, report.failed),
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
            (report.seen, report.failed, report.invalid, report.merged),
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

    def test_a_payload_that_will_not_decode_is_invalid(self) -> None:
        """A scrape that stopped mid-write leaves a truncated blob behind. Is
        it counted rather than raised, so the rest of the run still loads?"""
        _run_database(
            self.database,
            ['{"docket_number": "A-1', {"docket_number": "A-2"}],
        )

        report = self.loader_class()(self.database).load()

        self.assertEqual(
            (report.seen, report.invalid, report.merged, report.failed),
            (2, 1, 1, 0),
        )
        self.assertEqual(
            Docket.objects.get().docket_number,
            "A-2",
            "The row after the undecodable one still merges.",
        )

    def test_merger_declining_a_scrape_is_a_failure(self) -> None:
        """A merger refuses a scrape in its own `validate`, which it reports as
        a failure. Is the row counted as one, and the rest of the run left to
        merge?"""
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
            (report.seen, report.merged, report.failed, report.invalid),
            (2, 1, 1, 0),
        )
        self.assertEqual(report.result.failures, {"Docket": [None]})
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
        # Recorded alongside the run's other failures, so a caller reading
        # `result` sees the same failure the counters do.
        self.assertEqual(report.result.failures, {"Docket": [None]})
        self.assertFalse(report.result.success)
        self.assertEqual(
            Docket.objects.get().docket_number,
            "A-2",
            "The row after the raising one still merges.",
        )

    def test_a_dry_run_survives_a_database_error(self) -> None:
        """A dry run merges inside one transaction, so a row the database
        refuses would abort it. Does an atomic merger's savepoint keep that row
        from costing the rest of the run?"""
        loader_class = self.loader_class()

        class DatabaseErrorMerger(loader_class.merger):  # type: ignore[misc, name-defined]
            atomic: ClassVar[bool] = True

            def merge_one(self) -> Any:
                if self.scrape.docket_number == "A-1":
                    # Any statement the database refuses will do; what matters
                    # is that it aborts the transaction it runs in.
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT 1 / 0")
                return super().merge_one()

        _run_database(
            self.database,
            [{"docket_number": "A-1"}, {"docket_number": "A-2"}],
        )

        report = self.loader_class(merger=DatabaseErrorMerger)(
            self.database, dry_run=True
        ).load()

        self.assertEqual(
            (report.seen, report.failed, report.merged), (2, 1, 1)
        )
        self.assertFalse(Docket.objects.exists(), "The dry run rolled back.")

    def test_report_str_names_every_count(self) -> None:
        """The report is what an operator reads off a load. Does its summary
        state all four counts?"""
        report = LoadReport(seen=6, merged=1, invalid=2, failed=1)

        self.assertEqual(
            str(report),
            "6 seen, 1 merged, 2 invalid, 1 failed",
        )

    def test_db_delay_waits_between_rows(self) -> None:
        """A long load has to leave the database room to serve everyone else.
        Does `db_delay` wait after each row?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(3)],
        )

        with patch("cl.corpus_importer.state.loader.time.sleep") as sleep:
            self.loader_class()(self.database, db_delay=0.25).load()

        self.assertEqual(sleep.call_args_list, [call(0.25)] * 3)

    def test_no_db_delay_does_not_wait(self) -> None:
        """The default is to run flat out. Does a zero delay skip the wait
        rather than sleeping zero seconds three thousand times?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(3)],
        )

        with patch("cl.corpus_importer.state.loader.time.sleep") as sleep:
            self.loader_class()(self.database).load()

        sleep.assert_not_called()

    def document_loader_class(self) -> type[JKentScrapeLoader[Any]]:
        """A loader whose merges write three documents, for the extraction
        dispatch to have something to pace. The document model is a stand-in:
        `dispatch_extraction` only names it and reads rows off it."""
        document_model = Mock(__name__="Doc")
        document_model._default_manager.filter.return_value = [
            Mock() for _ in range(3)
        ]
        return self.loader_class(document_model=document_model)

    def test_extraction_throttle_paces_every_document(self) -> None:
        """Extraction is dispatched from inside the merge loop, which can
        outrun the workers over a whole run. Does the throttle get its say
        before each document goes to the queue?"""
        loader_class = self.document_loader_class()
        with patch(
            "cl.corpus_importer.state.loader.CeleryThrottle"
        ) as throttle_class:
            loader = loader_class(
                self.database, extraction_throttle=4, extraction_queue="batch1"
            )
            loader.dispatch_extraction(MergeResult(creates={"Doc": {1, 2, 3}}))

        throttle_class.assert_called_once_with(
            min_items=4, queue_name="batch1"
        )
        self.assertEqual(throttle_class.return_value.maybe_wait.call_count, 3)

    def test_no_extraction_throttle_builds_no_throttle(self) -> None:
        """Building a throttle polls the celery queue. Does a load that asked
        for none leave the queue alone?"""
        loader = self.document_loader_class()(self.database)

        self.assertIsNone(loader.throttle)


class JKentScrapeLoaderCheckpointTest(LoaderTestCase):
    """Tests for the position a load records so a later one can resume it.

    Checkpoints go to the real Redis, since the point of one is that it
    outlives the process that wrote it.
    """

    def setUp(self) -> None:
        super().setUp()
        self.key = "state_scrape_load:test:run.db"
        self.redis = get_redis_interface("CACHE")
        self.redis.delete(self.key)
        self.addCleanup(self.redis.delete, self.key)
        patcher = patch(
            "cl.corpus_importer.state.loader.CHECKPOINT_EVERY", new=2
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def checkpoint(self) -> int:
        """The row the checkpoint names, or 0 for no checkpoint."""
        return get_last_parent_document_id_processed(self.key)

    def test_a_load_checkpoints_the_rows_it_finished(self) -> None:
        """A load that dies is resumed from its last checkpoint, so the
        checkpoint must never name a row the load had not got through. Does it
        name the last finished row?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        loader = self.loader_class()(self.database, checkpoint_key=self.key)

        # Stop the load partway, as a dying process would.
        with patch.object(
            loader,
            "merge_one",
            side_effect=[MergeResult(), MergeResult(), OSError("gone")],
        ):
            with self.assertRaises(OSError):
                loader.load()

        # The checkpoint was written at the top of row 2, by which point only
        # row 1 had merged. Row 2 merged after it and is loaded again on
        # resume, which merging idempotently makes harmless -- naming a row
        # the load had not reached would not be.
        self.assertEqual(self.checkpoint(), 1)

    def test_a_checkpoint_resumes_the_rows_it_left(self) -> None:
        """A checkpoint is only worth writing if it starts the next load in
        the right place. Does resuming from one merge exactly the rest?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        log_last_document_indexed(2, self.key)

        report = self.loader_class()(
            self.database, start_row=self.checkpoint()
        ).load()

        self.assertEqual((report.seen, report.merged), (3, 3))
        self.assertEqual(
            set(Docket.objects.values_list("docket_number", flat=True)),
            {"A-2", "A-3", "A-4"},
        )

    def test_a_finished_load_clears_its_checkpoint(self) -> None:
        """A checkpoint left behind by a load that finished would send the
        next load of the same run database straight to the end, merging
        nothing. Is it dropped?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        self.loader_class()(self.database, checkpoint_key=self.key).load()

        self.assertEqual(self.checkpoint(), 0)

    def test_a_dry_run_leaves_no_checkpoint(self) -> None:
        """A dry run rolls back everything it merged, so there is nothing to
        resume. Does it leave the checkpoint alone?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        log_last_document_indexed(2, self.key)

        self.loader_class()(
            self.database, checkpoint_key=self.key, dry_run=True
        ).load()

        self.assertEqual(self.checkpoint(), 2, "The real load's position.")

    def test_a_limited_run_leaves_no_checkpoint(self) -> None:
        """A limited run stops at a row that means nothing to a full load.
        Does it neither record that position nor clear a real one?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )
        log_last_document_indexed(2, self.key)

        self.loader_class()(
            self.database, checkpoint_key=self.key, limit=4
        ).load()

        self.assertEqual(self.checkpoint(), 2, "The real load's position.")

    def test_a_load_given_no_key_checkpoints_nothing(self) -> None:
        """Does a load with no checkpoint key run without touching Redis?"""
        _run_database(
            self.database,
            [{"docket_number": f"A-{n}"} for n in range(5)],
        )

        with patch(
            "cl.corpus_importer.state.loader.log_last_document_indexed"
        ) as log:
            self.loader_class()(self.database).load()

        log.assert_not_called()

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
            report = self.loader_class()(
                self.database, checkpoint_key=self.key
            ).load()

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
