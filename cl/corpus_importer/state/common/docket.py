from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, ClassVar, cast

from django.db.models import Model
from juriscraper.state.docket import (
    Docket as ScrapeDocket,
)
from juriscraper.state.docket import DocketEntry as ScrapeDocketEntry
from juriscraper.state.docket import Party as ScrapeParty

from cl.corpus_importer.state.common.docket_entry import DocketEntryMerger
from cl.corpus_importer.state.common.party import PartyMerger, PartyTypeMerger
from cl.corpus_importer.state.merger import (
    Constant,
    Fn,
    ManyStrategy,
    ManyToManyRelation,
    Merger,
    OneToManyRelation,
    Params,
    Scrape,
    WithStrategy,
    overwrite,
)
from cl.corpus_importer.state.merger.specifications import AttributeMerger
from cl.people_db.models import Party
from cl.search.models import Docket


def add_scraper_source(scrape: int | None, db: int | None) -> int:
    if not db:
        db = 0
    if db in Docket.NON_SCRAPER_SOURCES():
        return db + Docket.SCRAPER
    return db


def _docket_parties[PType: ScrapeParty[Any]](
    docket: ScrapeDocket[Any, Any, PType], params: Any
) -> Sequence[PType]:
    return docket.parties


def _docket_entries[EType: ScrapeDocketEntry[Any]](
    docket: ScrapeDocket[Any, EType, Any], params: Any
) -> Sequence[EType]:
    return docket.entries


def PartyRelation(
    merger: type[Merger[Any, Any, Any]] = PartyMerger,
    *,
    party_type: type[Merger[Any, Any, Any]] = PartyTypeMerger,
    transform: Callable[[Any, Any], Sequence[Any]] = _docket_parties,
) -> list[Party]:
    """Merge a docket's parties.

    A re-scrape with no parties (or a party with no representatives) keeps the
    existing links and roles.
    """
    return ManyToManyRelation(
        merger,
        cast(AttributeMerger, Fn(transform)(Scrape(Any), Params(Any))),
        party_type,
        strategy=ManyStrategy.DISASSOCIATE,
    )


def DocketEntryRelation(
    merger: type[Merger[Any, Any, Any]] = DocketEntryMerger,
    *,
    transform: Callable[[Any, Any], Sequence[Any]] = _docket_entries,
    strategy: ManyStrategy = ManyStrategy.APPEND,
) -> list[Any]:
    return OneToManyRelation(
        merger,
        cast(AttributeMerger, Fn(transform)(Scrape(Any), Params(Any))),
        strategy=strategy,
    )


class DocketMerger[DType: ScrapeDocket[Any, Any, Any], ParamType](
    Merger[DType, ParamType, Docket], abstract=True
):
    model: ClassVar[type[Model]] = Docket

    atomic = True

    source: int = WithStrategy(Constant(Docket.SCRAPER), add_scraper_source)
    date_filed: date | None = WithStrategy(
        Scrape(ScrapeDocket).date_filed, overwrite
    )
    case_name: str = WithStrategy(Scrape(ScrapeDocket).case_name, overwrite)
    case_name_full: str = WithStrategy(
        Scrape(ScrapeDocket).case_name_full, overwrite
    )
    case_name_short: str = WithStrategy(
        Scrape(ScrapeDocket).case_name_short, overwrite
    )
    docket_number: str | None = WithStrategy(
        Scrape(ScrapeDocket).docket_number, overwrite
    )
    docket_number_raw: str = WithStrategy(
        Scrape(ScrapeDocket).docket_number, overwrite
    )
    parties: list[Party] = PartyRelation()
