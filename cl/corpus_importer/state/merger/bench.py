"""Benchmarks for every phase of a merger's life: spec construction, class creation (registry inheritance and validation), instance initialisation (transforms and natural-key hashing), the pure-Python merge paths, and the DB-backed merge paths for each kind of relation.

Run with::

    docker exec cl-django uv run pytest -c pytest.toml cl/corpus_importer/state/bench

The DB-backed benches run inside a single test transaction per bench, so rows
created by one round stay visible to the next. Each "rescrape" bench therefore
measures the steady state of re-merging data that is already in the DB, and
each "create" bench uses a fresh natural key per round.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import count
from types import new_class
from typing import Any, ClassVar

import pytest
from django.db.models import Model, QuerySet
from pytest_benchmark.fixture import BenchmarkFixture

from cl.corpus_importer.state.utils import MergeResult
from cl.people_db.models import Party, PartyType
from cl.search.docket_sources import DocketSources
from cl.search.factories import CourtFactory
from cl.search.models import (
    Court,
    Docket,
    DocketEntry,
    OriginatingCourtInformation,
)

from .base import (
    Merger,
    MergerSpecRegistry,
    RelatedParams,
    ThroughParameters,
)
from .specifications import (
    Attribute,
    ManyToManyRelation,
    OneToManyRelation,
    OneToOneRelation,
)
from .strategy import (
    overwrite,
    overwrite_if_present,
)

Scrape = dict[str, Any]

# Sizes for the benches that scale with the amount of scraped data.
ATTRIBUTE_COUNT = 20
ENTRY_COUNT = 20
PARTY_COUNT = 10
BULK_COUNT = 50

# Text fields on `Docket`, used to build mergers with many attributes.
DOCKET_TEXT_FIELDS = (
    "appeal_from_str",
    "assigned_to_str",
    "referred_to_str",
    "panel_str",
    "case_name_short",
    "case_name",
    "case_name_full",
    "docket_number",
    "docket_number_core",
    "docket_number_raw",
    "federal_dn_office_code",
    "federal_dn_case_type",
    "federal_dn_judge_initials_assigned",
    "federal_dn_judge_initials_referred",
    "cause",
    "nature_of_suit",
    "jury_demand",
    "jurisdiction_type",
    "appellate_fee_status",
    "appellate_case_type_information",
)[:ATTRIBUTE_COUNT]

# A court that never touches the DB, for the benches that only need a
# plausible foreign key value.
STUB_COURT = Court(pk="bench")


def many_attr_merger() -> type[Merger[None, None, Docket]]:
    """Define a merger with an attribute for each of `DOCKET_TEXT_FIELDS`."""

    def body(namespace: dict[str, Any]) -> None:
        namespace["model"] = Docket
        for name in DOCKET_TEXT_FIELDS:
            namespace[name] = Attribute(default="")

    return new_class(
        "ManyAttrMerger", (Merger[None, None, Docket],), exec_body=body
    )


@dataclass(frozen=True)
class DocketParams:
    """Parameters for the docket mergers below. `court_id` is picked up by the default transform of the `court_id` attribute."""

    court_id: str


def make_scrape(docket_number: str) -> Scrape:
    """Build a docket scrape with `ENTRY_COUNT` entries, `PARTY_COUNT` parties and an originating court."""
    return {
        "docket_number": docket_number,
        "case_name": f"Case {docket_number}",
        "entries": [
            {"entry_number": n, "description": f"Entry {n}"}
            for n in range(1, ENTRY_COUNT + 1)
        ],
        "parties": [
            {"name": f"Party {n} of {docket_number}", "type": "Plaintiff"}
            for n in range(PARTY_COUNT)
        ],
        "origin": {"docket_number": f"ORIG-{docket_number}"},
    }


class EntryMerger(Merger[Scrape, RelatedParams[DocketParams], DocketEntry]):
    model: ClassVar[type[Model]] = DocketEntry
    key: ClassVar[Iterable[str]] = ["entry_number"]

    entry_number: int = Attribute(
        transform=lambda d, params: d["entry_number"]
    )
    description: str = Attribute(transform=lambda d, params: d["description"])


class OriginMerger(
    Merger[Scrape, RelatedParams[DocketParams], OriginatingCourtInformation]
):
    model: ClassVar[type[Model]] = OriginatingCourtInformation

    docket_number: str = Attribute(
        transform=lambda d, params: d["docket_number"]
    )

    def query(self) -> QuerySet[OriginatingCourtInformation]:
        """A forward one-to-one is only ever created from here; the parent hands over any existing object itself."""
        return self.manager.none()


class PartyMerger(Merger[Scrape, RelatedParams[DocketParams], Party]):
    model: ClassVar[type[Model]] = Party
    key: ClassVar[Iterable[str]] = ["name"]

    name: str = Attribute(transform=lambda d, params: d["name"])


class PartyTypeMerger(
    Merger[Scrape, ThroughParameters[DocketParams], PartyType]
):
    model: ClassVar[type[Model]] = PartyType
    key: ClassVar[Iterable[str]] = ["name"]

    name: str = Attribute(transform=lambda d, params: d["type"])


class DocketMerger(Merger[Scrape, DocketParams, Docket]):
    model: ClassVar[type[Model]] = Docket
    key: ClassVar[Iterable[str]] = ["court_id", "docket_number"]

    court_id: str = Attribute(transform=lambda scrape, params: scrape)
    source: int = Attribute(default=DocketSources.SCRAPER)
    docket_number: str = Attribute(
        transform=lambda d, params: d["docket_number"]
    )
    case_name: str = Attribute(transform=lambda d, params: d["case_name"])


class AtomicDocketMerger(DocketMerger):
    atomic: ClassVar[bool] = True


class DocketWithEntriesMerger(DocketMerger):
    docket_entries: list[DocketEntry] = OneToManyRelation(
        EntryMerger, Attribute(transform=lambda d, params: d["entries"])
    )


class DocketWithOriginMerger(DocketMerger):
    originating_court_information: OriginatingCourtInformation = (
        OneToOneRelation(
            OriginMerger, Attribute(transform=lambda d, params: d["origin"])
        )
    )


class DocketWithPartiesMerger(DocketMerger):
    parties: list[Party] = ManyToManyRelation(
        PartyMerger,
        Attribute(transform=lambda d, params: d["parties"]),
        PartyTypeMerger,
    )


class RejectingDocketMerger(DocketMerger):
    @staticmethod
    def validate(scrape: Scrape) -> bool:
        return False


class SpecificationBench:
    """The per-attribute building blocks that run once per attribute on every init and merge."""

    def bench_attr_transform_custom(self, benchmark: BenchmarkFixture):
        spec = Attribute(default="abcdefg")

        benchmark(spec.transform, None, None)

    def bench_attr_transform_default_no_params(
        self, benchmark: BenchmarkFixture
    ):
        spec = Attribute(default="abcdefg")
        spec.name = "docket_number"

        benchmark(spec.transform, None, None)

    def bench_attr_transform_default_dict_params(
        self, benchmark: BenchmarkFixture
    ):
        spec = Attribute(default="abcdefg")
        spec.name = "docket_number"

        benchmark(spec.transform, None, {"docket_number": "hijklmn"})

    def bench_attr_transform_default_object_params(
        self, benchmark: BenchmarkFixture
    ):
        spec = Attribute(transform=lambda scrape, params: scrape)
        spec.name = "court_id"

        benchmark(spec.transform, None, DocketParams(court_id=STUB_COURT.pk))

    def bench_strategy_overwrite(self, benchmark: BenchmarkFixture):
        benchmark(overwrite, "scrape", "db")

    def bench_strategy_overwrite_if_present(self, benchmark: BenchmarkFixture):
        benchmark(overwrite_if_present, None, "db")

    def bench_attr_validation(self, benchmark: BenchmarkFixture):
        spec = Attribute(default="abcdefg")
        spec.name = "docket_number"

        benchmark(spec.run_validation, DocketMerger)

    def bench_related_validation(self, benchmark: BenchmarkFixture):
        spec = OneToManyRelation(
            EntryMerger, Attribute(transform=lambda scrape, params: scrape)
        )
        spec.name = "docket_entries"

        benchmark(spec.run_validation, DocketMerger)

    def bench_registry_validation(self, benchmark: BenchmarkFixture):
        registry: MergerSpecRegistry[Any, Any] = (
            DocketWithEntriesMerger.__registry__
        )

        benchmark(registry.validate, DocketWithEntriesMerger)


class ClassCreationBench:
    """Defining a merger subclass: building the registry from the bases, registering each spec, and validating the whole class."""

    def bench_subclass_init_bare(self, benchmark: BenchmarkFixture):
        def run():
            class BareMerger(Merger[None, None, Docket]):
                model: ClassVar[type[Docket]] = Docket

        benchmark(run)

    def bench_subclass_init_attr(self, benchmark: BenchmarkFixture):
        def run():
            class AttrMerger(Merger[None, None, Docket]):
                model: ClassVar[type[Docket]] = Docket

                docket_number: str = Attribute(default="abcdefg")

        benchmark(run)

    def bench_subclass_init_many_attrs(self, benchmark: BenchmarkFixture):
        benchmark(many_attr_merger)

    def bench_subclass_init_one_to_one(self, benchmark: BenchmarkFixture):
        def run():
            class OneToOneMerger(Merger[Scrape, None, Docket]):
                model: ClassVar[type[Docket]] = Docket

                originating_court_information: OriginatingCourtInformation = (
                    OneToOneRelation(
                        OriginMerger,
                        Attribute(transform=lambda scrape, params: scrape),
                    )
                )

        benchmark(run)

    def bench_subclass_init_one_to_many(self, benchmark: BenchmarkFixture):
        def run():
            class OneToManyMerger(Merger[Scrape, None, Docket]):
                model: ClassVar[type[Docket]] = Docket

                docket_entries: list[DocketEntry] = OneToManyRelation(
                    EntryMerger,
                    Attribute(transform=lambda scrape, params: scrape),
                )

        benchmark(run)

    def bench_subclass_init_many_to_many(self, benchmark: BenchmarkFixture):
        def run():
            class ManyToManyMerger(Merger[Scrape, None, Docket]):
                model: ClassVar[type[Docket]] = Docket

                parties: list[Party] = ManyToManyRelation(
                    PartyMerger,
                    Attribute(transform=lambda scrape, params: scrape),
                    PartyTypeMerger,
                )

        benchmark(run)

    def bench_subclass_init_inherited(self, benchmark: BenchmarkFixture):
        """Subclassing a merger that already carries specs for every kind of relation, so the registry has to be copied and re-validated."""

        def run():
            class InheritedMerger(DocketWithPartiesMerger):
                case_name_short: str = Attribute(default="")

        benchmark(run)

    def bench_subclass_init_abstract(self, benchmark: BenchmarkFixture):
        def run():
            class AbstractMerger(Merger[Scrape, None, Docket], abstract=True):
                docket_entries: list[DocketEntry] = OneToManyRelation(
                    EntryMerger,
                    Attribute(transform=lambda scrape, params: scrape),
                )

        benchmark(run)


class InstanceInitBench:
    """Instantiating a merger: validating the scrape, running every transform and resolving the relation parameters."""

    def bench_init_bare(self, benchmark: BenchmarkFixture):
        class BareMerger(Merger[None, None, Docket]):
            model: ClassVar[type[Docket]] = Docket

        benchmark(BareMerger, None, params=None)

    def bench_init_attr(self, benchmark: BenchmarkFixture):
        class AttrMerger(Merger[None, None, Docket]):
            model: ClassVar[type[Docket]] = Docket

            docket_number: str = Attribute(default="abcdefg")

        benchmark(AttrMerger, None, params=None)

    def bench_init_many_attrs(self, benchmark: BenchmarkFixture):
        benchmark(many_attr_merger(), None, params=None)

    def bench_init_all_relations(self, benchmark: BenchmarkFixture):
        class AllRelationsMerger(DocketWithPartiesMerger):
            docket_entries: list[DocketEntry] = OneToManyRelation(
                EntryMerger,
                Attribute(transform=lambda d, params: d["entries"]),
            )
            originating_court_information: OriginatingCourtInformation = (
                OneToOneRelation(
                    OriginMerger,
                    Attribute(transform=lambda d, params: d["origin"]),
                )
            )

        benchmark(
            AllRelationsMerger,
            make_scrape("INIT"),
            params=DocketParams(court_id=STUB_COURT.pk),
        )

    def bench_init_rejected(self, benchmark: BenchmarkFixture):
        benchmark(
            RejectingDocketMerger,
            make_scrape("INIT"),
            params=DocketParams(court_id=STUB_COURT.pk),
        )

    def bench_init_related_params(self, benchmark: BenchmarkFixture):
        benchmark(
            EntryMerger,
            {"entry_number": 1, "description": "Entry 1"},
            params=RelatedParams(
                DocketParams(court_id=STUB_COURT.pk), parent=Docket(pk=1)
            ),
        )

    def bench_init_reverse_related_params(self, benchmark: BenchmarkFixture):
        benchmark(
            OriginMerger,
            {"docket_number": "ORIG"},
            params=RelatedParams(
                DocketParams(court_id=STUB_COURT.pk),
                parent=Docket(pk=1),
                parent_name="docket",
            ),
        )

    def bench_init_through_params(self, benchmark: BenchmarkFixture):
        benchmark(
            PartyTypeMerger,
            {"name": "Alice", "type": "Plaintiff"},
            params=ThroughParameters(
                DocketParams(court_id=STUB_COURT.pk),
                parent=Docket(pk=1),
                source=Docket(pk=1),
                source_name="docket",
                target=Party(pk=1),
                target_name="party",
            ),
        )

    def bench_hash_natural_key_transform(self, benchmark: BenchmarkFixture):
        merger = PartyTypeMerger(
            {"name": "Alice", "type": "Plaintiff"},
            params=ThroughParameters(
                DocketParams(court_id=STUB_COURT.pk),
                parent=Docket(pk=1),
                source=Docket(pk=1),
                source_name="docket",
                target=Party(pk=1),
                target_name="party",
            ),
        )

        benchmark(merger._hash_natural_key_transform)

    def bench_hash_natural_key_model(self, benchmark: BenchmarkFixture):
        obj = PartyType(name="Plaintiff", docket_id=1, party_id=1)

        benchmark(
            PartyTypeMerger._hash_natural_key_model, obj, ("docket", "party")
        )

    def bench_uses_natural_key(self, benchmark: BenchmarkFixture):
        benchmark(DocketMerger.uses_natural_key)


class MergeBench:
    """The merge paths that never touch the DB."""

    def bench_merge_rejected(self, benchmark: BenchmarkFixture):
        merger = RejectingDocketMerger(
            make_scrape("MERGE"), params=DocketParams(court_id=STUB_COURT.pk)
        )

        benchmark(merger.merge)

    def bench_merge_noop_update(self, benchmark: BenchmarkFixture):
        """Merging into an existing object that already matches: every attribute is compared and none is written."""
        scrape = make_scrape("MERGE")
        existing = Docket(
            court=STUB_COURT,
            source=DocketSources.SCRAPER,
            docket_number=scrape["docket_number"],
            case_name=scrape["case_name"],
        )

        def run():
            return DocketMerger(
                scrape,
                params=DocketParams(court_id=STUB_COURT.pk),
                existing=existing,
                lookup=False,
            ).merge()

        benchmark(run)

    def bench_query_build(self, benchmark: BenchmarkFixture):
        merger = DocketMerger(
            make_scrape("MERGE"), params=DocketParams(court_id=STUB_COURT.pk)
        )

        benchmark(merger.query)

    def bench_one_to_one_absent(self, benchmark: BenchmarkFixture):
        spec = DocketWithOriginMerger.__registry__.one_to_one[
            "originating_court_information"
        ]

        benchmark(spec.merge, None, {"origin": None}, None)

    def bench_merge_result_combine(self, benchmark: BenchmarkFixture):
        results = [
            MergeResult.created("DocketEntry", n) for n in range(ENTRY_COUNT)
        ] + [MergeResult.updated("Docket", 1), MergeResult.failed("Party")]

        def run():
            result = MergeResult.unnecessary()
            for r in results:
                result |= r
            return result

        benchmark(run)


@pytest.fixture
def court(db: None) -> Court:
    """A court for the DB-backed benches to hang dockets off of."""
    return CourtFactory.create()


def per_round_scrapes() -> Callable[[], Scrape]:
    """Build a scrape with a docket number nobody has used before, for the benches that create a fresh object every round."""
    counter = count()
    return lambda: make_scrape(f"NEW-{next(counter)}")


@pytest.mark.django_db
class MergeDBBench:
    """The merge paths that read from and write to the DB."""

    def bench_lookup_hit(self, benchmark: BenchmarkFixture, court: Court):
        """Natural-key lookup that finds the object and has nothing to write."""
        params = DocketParams(court_id=court.pk)
        scrape = make_scrape("HIT")
        DocketMerger(scrape, params=params).merge()

        benchmark(lambda: DocketMerger(scrape, params=params).merge())

    def bench_lookup_miss_create(
        self, benchmark: BenchmarkFixture, court: Court
    ):
        params = DocketParams(court_id=court.pk)
        scrape = per_round_scrapes()

        benchmark(lambda: DocketMerger(scrape(), params=params).merge())

    def bench_create_without_lookup(
        self, benchmark: BenchmarkFixture, court: Court
    ):
        params = DocketParams(court_id=court.pk)
        scrape = per_round_scrapes()

        benchmark(
            lambda: DocketMerger(scrape(), params=params, lookup=False).merge()
        )

    def bench_update(self, benchmark: BenchmarkFixture, court: Court):
        """Natural-key lookup followed by a save, because the case name differs from the DB every round."""
        params = DocketParams(court_id=court.pk)
        scrape = make_scrape("UPDATE")
        DocketMerger(scrape, params=params).merge()
        counter = count()

        def run():
            scrape["case_name"] = f"Case {next(counter)}"
            return DocketMerger(scrape, params=params).merge()

        benchmark(run)

    def bench_atomic_lookup_hit(
        self, benchmark: BenchmarkFixture, court: Court
    ):
        params = DocketParams(court_id=court.pk)
        scrape = make_scrape("ATOMIC")
        AtomicDocketMerger(scrape, params=params).merge()

        benchmark(lambda: AtomicDocketMerger(scrape, params=params).merge())

    def bench_init_many(self, benchmark: BenchmarkFixture, court: Court):
        """Batched natural-key lookup for `BULK_COUNT` scrapes that are all already in the DB."""
        params = DocketParams(court_id=court.pk)
        scrapes = [make_scrape(f"BULK-{n}") for n in range(BULK_COUNT)]
        for scrape in scrapes:
            DocketMerger(scrape, params=params).merge()

        benchmark(DocketMerger.init_many, scrapes, params=params)

    def bench_one_to_one_create(
        self, benchmark: BenchmarkFixture, court: Court
    ):
        params = DocketParams(court_id=court.pk)
        scrape = per_round_scrapes()

        benchmark(
            lambda: DocketWithOriginMerger(scrape(), params=params).merge()
        )

    def bench_one_to_one_rescrape(
        self, benchmark: BenchmarkFixture, court: Court
    ):
        params = DocketParams(court_id=court.pk)
        scrape = make_scrape("O2O")
        DocketWithOriginMerger(scrape, params=params).merge()

        benchmark(
            lambda: DocketWithOriginMerger(scrape, params=params).merge()
        )

    def bench_one_to_many_create(
        self, benchmark: BenchmarkFixture, court: Court
    ):
        params = DocketParams(court_id=court.pk)
        scrape = per_round_scrapes()

        benchmark(
            lambda: DocketWithEntriesMerger(scrape(), params=params).merge()
        )

    def bench_one_to_many_rescrape(
        self, benchmark: BenchmarkFixture, court: Court
    ):
        params = DocketParams(court_id=court.pk)
        scrape = make_scrape("O2M")
        DocketWithEntriesMerger(scrape, params=params).merge()

        benchmark(
            lambda: DocketWithEntriesMerger(scrape, params=params).merge()
        )

    def bench_many_to_many_create(
        self, benchmark: BenchmarkFixture, court: Court
    ):
        params = DocketParams(court_id=court.pk)
        scrape = per_round_scrapes()

        benchmark(
            lambda: DocketWithPartiesMerger(scrape(), params=params).merge()
        )

    def bench_many_to_many_rescrape(
        self, benchmark: BenchmarkFixture, court: Court
    ):
        params = DocketParams(court_id=court.pk)
        scrape = make_scrape("M2M")
        DocketWithPartiesMerger(scrape, params=params).merge()

        benchmark(
            lambda: DocketWithPartiesMerger(scrape, params=params).merge()
        )
