"""Base merger for scraped state dockets, with their parties and entries."""

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, ClassVar

from juriscraper.state.docket import (
    Docket as ScrapeDocket,
)
from juriscraper.state.docket import DocketEntry as ScrapeDocketEntry
from juriscraper.state.docket import Party as ScrapeParty

from cl.corpus_importer.state.common.docket_entry import DocketEntryMerger
from cl.corpus_importer.state.common.party import PartyMerger, PartyTypeMerger
from cl.corpus_importer.state.merger import (
    Database,
    Fn,
    ManyStrategy,
    ManyToManyRelation,
    Merger,
    MergerConfig,
    OneToManyRelation,
    Params,
    Scrape,
)
from cl.people_db.models import Party
from cl.search.models import Docket


def add_scraper_source(db: int | None) -> int:
    """Add the scraper to a docket's stored source, ignoring the scraped value.

    A missing source is treated as 0. Sources that already include the
    scraper are kept as they are.
    """
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
) -> Sequence[Party]:
    """Merge a docket's parties.

    A re-scrape with no parties (or a party with no representatives) keeps the
    existing links and roles.
    """
    return ManyToManyRelation(
        merger,
        Fn(transform)(Scrape(Any), Params(Any)),
        party_type,
        strategy=ManyStrategy.DISASSOCIATE,
    )


def DocketEntryRelation(
    merger: type[Merger[Any, Any, Any]] = DocketEntryMerger,
    *,
    transform: Callable[[Any, Any], Sequence[Any]] = _docket_entries,
    strategy: ManyStrategy = ManyStrategy.APPEND,
) -> list[Any]:
    """Declare a docket's entries as a one-to-many relation.

    Defaults to merging the scraped docket's entries and appending them to
    the docket's existing entries. Entries resolve the party that filed them
    against the docket's parties, so those are merged first.
    """
    return OneToManyRelation(
        merger,
        Fn(transform)(Scrape(Any), Params(Any)),
        strategy=strategy,
        after=["parties"],
    )


class DocketMerger[DType: ScrapeDocket[Any, Any, Any], ParamType](
    Merger[DType, ParamType, Docket], abstract=True
):
    """Base merger for a scraped state docket into a ``Docket``.

    Merges the docket's names, number, filing date, source, and parties.
    """

    config: ClassVar[MergerConfig[Docket]] = MergerConfig(model=Docket)

    source: int = Fn(add_scraper_source)(Database(Docket.source))
    date_filed: date | None = Scrape(ScrapeDocket).date_filed
    case_name: str = Scrape(ScrapeDocket).case_name
    case_name_full: str = Scrape(ScrapeDocket).case_name_full
    case_name_short: str = Scrape(ScrapeDocket).case_name_short
    docket_number: str | None = Scrape(ScrapeDocket).docket_number
    docket_number_raw: str = Scrape(ScrapeDocket).docket_number
    parties: Sequence[Party] = PartyRelation()
