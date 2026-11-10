"""Benchmarks for every phase of a merger's life: spec construction, class creation (registry inheritance and validation), instance initialisation (transforms and natural-key hashing), the pure-Python merge paths, and the DB-backed merge paths for each kind of relation.

Run with::

    docker exec cl-django uv run pytest -c pytest.toml cl/corpus_importer/state/bench

The DB-backed benches run inside a single test transaction per bench, so rows
created by one round stay visible to the next. Each "rescrape" bench therefore
measures the steady state of re-merging data that is already in the DB, and
each "create" bench uses a fresh natural key per round.
"""

from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
from types import new_class
from typing import Any, ClassVar, cast, override

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from cl.corpus_importer.state.merger.specifications import AttributeMerger
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

from . import state as MergerState
from .base import (
    Merger,
    MergerConfig,
    MergerSpecRegistry,
)
from .parameters import (
    Create,
    RelatedParams,
    ThroughParameters,
    Update,
)
from .specifications import (
    Constant,
    ManyToManyRelation,
    OneToManyRelation,
    OneToOneRelation,
    Params,
)
from .specifications import Scrape as ScrapeProxy
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
        namespace["config"] = MergerConfig(model=Docket)
        for name in DOCKET_TEXT_FIELDS:
            namespace[name] = Constant("")

    return new_class(
        "ManyAttrMerger", (Merger[None, None, Docket],), exec_body=body
    )


@dataclass(frozen=True)
class DocketParams:
    """Parameters for the docket mergers below. `court_id` is read by the transform of the `court_id` attribute."""

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
    config: ClassVar[MergerConfig[DocketEntry]] = MergerConfig(
        model=DocketEntry, key=("entry_number",)
    )

    entry_number: int = ScrapeProxy(Scrape)["entry_number"]
    description: str = ScrapeProxy(Scrape)["description"]


class OriginMerger(
    Merger[Scrape, RelatedParams[DocketParams], OriginatingCourtInformation]
):
    config: ClassVar[MergerConfig[OriginatingCourtInformation]] = MergerConfig(
        model=OriginatingCourtInformation
    )

    docket_number: str = ScrapeProxy(Scrape)["docket_number"]

    @override
    def lookup(
        self,
        state: MergerState.Lookup[
            Scrape, RelatedParams[DocketParams], OriginatingCourtInformation
        ],
    ) -> MergerState.LookupOutput[
        Scrape, RelatedParams[DocketParams], OriginatingCourtInformation
    ]:
        """A forward one-to-one is only ever created from here; the parent hands over any existing object itself."""
        return state.create()


class PartyMerger(Merger[Scrape, RelatedParams[DocketParams], Party]):
    config: ClassVar[MergerConfig[Party]] = MergerConfig(
        model=Party, key=("name",)
    )

    name: str = ScrapeProxy(Scrape)["name"]


class PartyTypeMerger(
    Merger[Scrape, ThroughParameters[DocketParams], PartyType]
):
    config: ClassVar[MergerConfig[PartyType]] = MergerConfig(
        model=PartyType, key=("name",)
    )

    name: str = ScrapeProxy(Scrape)["type"]


class DocketMerger(Merger[Scrape, DocketParams, Docket]):
    config: ClassVar[MergerConfig[Docket]] = MergerConfig(
        model=Docket,
        key=(
            "court_id",
            "docket_number",
        ),
    )

    court_id: str = Params(DocketParams).court_id
    source: int = Constant(DocketSources.SCRAPER)
    docket_number: str = ScrapeProxy(Scrape)["docket_number"]
    case_name: str = ScrapeProxy(Scrape)["case_name"]


class DocketWithEntriesMerger(DocketMerger):
    docket_entries: list[DocketEntry] = OneToManyRelation(
        EntryMerger, ScrapeProxy(Scrape)["entries"]
    )


class DocketWithOriginMerger(DocketMerger):
    originating_court_information: OriginatingCourtInformation = (
        OneToOneRelation(OriginMerger, ScrapeProxy(Scrape)["origin"])
    )


class DocketWithPartiesMerger(DocketMerger):
    parties: list[Party] = ManyToManyRelation(
        PartyMerger,
        ScrapeProxy(Scrape)["parties"],
        PartyTypeMerger,
    )


class RejectingDocketMerger(DocketMerger):
    @staticmethod
    def validator(scrape: Scrape) -> bool:
        return False


class SpecificationBench:
    """The per-attribute building blocks that run once per attribute on every init and merge."""

    def bench_attr_transform_custom(self, benchmark: BenchmarkFixture):
        spec = cast(AttributeMerger, Constant("abcdefg"))

        benchmark(spec.transform, None, None)

    def bench_attr_transform_default_no_params(
        self, benchmark: BenchmarkFixture
    ):
        spec = cast(AttributeMerger, Constant("abcdefg"))
        spec._name = "docket_number"

        benchmark(spec.transform, None, None)

    def bench_attr_transform_default_dict_params(
        self, benchmark: BenchmarkFixture
    ):
        spec = cast(AttributeMerger, Constant("abcdefg"))
        spec._name = "docket_number"

        benchmark(spec.transform, None, {"docket_number": "hijklmn"})

    def bench_attr_transform_default_object_params(
        self, benchmark: BenchmarkFixture
    ):
        spec = cast(AttributeMerger, Params(DocketParams).court_id)
        spec._name = "court_id"

        benchmark(spec.transform, None, DocketParams(court_id=STUB_COURT.pk))

    def bench_strategy_overwrite(self, benchmark: BenchmarkFixture):
        benchmark(overwrite, "scrape", "db")

    def bench_strategy_overwrite_if_present(self, benchmark: BenchmarkFixture):
        benchmark(overwrite_if_present, None, "db")

    def bench_attr_validation(self, benchmark: BenchmarkFixture):
        spec = cast(AttributeMerger, Constant("abcdefg"))
        spec._name = "docket_number"

        benchmark(spec.run_validation, DocketMerger)

    def bench_related_validation(self, benchmark: BenchmarkFixture):
        spec = OneToManyRelation(
            EntryMerger, cast(AttributeMerger, ScrapeProxy(Scrape))
        )
        spec._name = "docket_entries"

        benchmark(spec.run_validation, DocketMerger)

    def bench_registry_validation(self, benchmark: BenchmarkFixture):
        registry: MergerSpecRegistry[Any, Any] = (
            DocketWithEntriesMerger.config.registry
        )

        benchmark(registry.validate, DocketWithEntriesMerger)


class ClassCreationBench:
    """Defining a merger subclass: building the registry from the bases, registering each spec, and validating the whole class."""

    def bench_subclass_init_bare(self, benchmark: BenchmarkFixture):
        def run():
            class BareMerger(Merger[None, None, Docket]):
                config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                    model=Docket
                )

        benchmark(run)

    def bench_subclass_init_attr(self, benchmark: BenchmarkFixture):
        def run():
            class AttrMerger(Merger[None, None, Docket]):
                config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                    model=Docket
                )

                docket_number: str = Constant("abcdefg")

        benchmark(run)

    def bench_subclass_init_many_attrs(self, benchmark: BenchmarkFixture):
        benchmark(many_attr_merger)

    def bench_subclass_init_one_to_one(self, benchmark: BenchmarkFixture):
        def run():
            class OneToOneMerger(Merger[Scrape, None, Docket]):
                config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                    model=Docket
                )

                originating_court_information: OriginatingCourtInformation = (
                    OneToOneRelation(
                        OriginMerger,
                        cast(AttributeMerger, ScrapeProxy(Scrape)),
                    )
                )

        benchmark(run)

    def bench_subclass_init_one_to_many(self, benchmark: BenchmarkFixture):
        def run():
            class OneToManyMerger(Merger[Scrape, None, Docket]):
                config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                    model=Docket
                )

                docket_entries: list[DocketEntry] = OneToManyRelation(
                    EntryMerger,
                    cast(AttributeMerger, ScrapeProxy(Scrape)),
                )

        benchmark(run)

    def bench_subclass_init_many_to_many(self, benchmark: BenchmarkFixture):
        def run():
            class ManyToManyMerger(Merger[Scrape, None, Docket]):
                config: ClassVar[MergerConfig[Docket]] = MergerConfig(
                    model=Docket
                )

                parties: list[Party] = ManyToManyRelation(
                    PartyMerger,
                    cast(AttributeMerger, ScrapeProxy(Scrape)),
                    PartyTypeMerger,
                )

        benchmark(run)

    def bench_subclass_init_inherited(self, benchmark: BenchmarkFixture):
        """Subclassing a merger that already carries specs for every kind of relation, so the registry has to be copied and re-validated."""

        def run():
            class InheritedMerger(DocketWithPartiesMerger):
                case_name_short: str = Constant("")

        benchmark(run)

    def bench_subclass_init_abstract(self, benchmark: BenchmarkFixture):
        def run():
            class AbstractMerger(Merger[Scrape, None, Docket], abstract=True):
                docket_entries: list[DocketEntry] = OneToManyRelation(
                    EntryMerger,
                    cast(AttributeMerger, ScrapeProxy(Scrape)),
                )

        benchmark(run)


class InstanceInitBench:
    """Instantiating a merger: validating the scrape, running every transform and resolving the relation parameters."""

    def bench_init_bare(self, benchmark: BenchmarkFixture):
        class BareMerger(Merger[None, None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

        benchmark(BareMerger, None, params=None)

    def bench_init_attr(self, benchmark: BenchmarkFixture):
        class AttrMerger(Merger[None, None, Docket]):
            config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

            docket_number: str = Constant("abcdefg")

        benchmark(AttrMerger, None, params=None)

    def bench_init_many_attrs(self, benchmark: BenchmarkFixture):
        benchmark(many_attr_merger(), None, params=None)

    def bench_init_all_relations(self, benchmark: BenchmarkFixture):
        class AllRelationsMerger(DocketWithPartiesMerger):
            docket_entries: list[DocketEntry] = OneToManyRelation(
                EntryMerger,
                ScrapeProxy(Scrape)["entries"],
            )
            originating_court_information: OriginatingCourtInformation = (
                OneToOneRelation(
                    OriginMerger,
                    ScrapeProxy(Scrape)["origin"],
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

        benchmark(merger._hash_natural_key_transform, merger.state)

    def bench_hash_natural_key_model(self, benchmark: BenchmarkFixture):
        obj = PartyType(name="Plaintiff", docket_id=1, party_id=1)

        benchmark(
            PartyTypeMerger._hash_natural_key_model, obj, ("docket", "party")
        )


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
                existing=Update(existing),
            ).merge()

        benchmark(run)

    def bench_query_build(self, benchmark: BenchmarkFixture):
        merger = DocketMerger(
            make_scrape("MERGE"), params=DocketParams(court_id=STUB_COURT.pk)
        )

        benchmark(merger.lookup, merger.state)

    def bench_one_to_one_absent(self, benchmark: BenchmarkFixture):
        spec = DocketWithOriginMerger.config.registry.one_to_one[
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
            lambda: DocketMerger(
                scrape(), params=params, existing=Create
            ).merge()
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
