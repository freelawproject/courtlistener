from collections.abc import Sequence
from datetime import date
from typing import Any, ClassVar

from django.db.models import Model
from juriscraper.state.docket import (
    Docket as ScrapeDocket,
)
from juriscraper.state.docket import Party as ScrapeParty

from cl.corpus_importer.state.common.party import PartyMerger, PartyTypeMerger
from cl.corpus_importer.state.merger import (
    Attribute,
    ManyToManyRelation,
    Merger,
    overwrite,
)
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


class DocketMerger[DType: ScrapeDocket[Any, Any, Any], ParamType](
    Merger[DType, ParamType, Docket]
):
    model: ClassVar[type[Model]] = Docket

    atomic = True

    source: int = Attribute(
        lambda _, params: Docket.SCRAPER,
        strategy=add_scraper_source,
    )
    date_filed: date | None = Attribute(
        lambda d, params: d.date_filed,
        strategy=overwrite,
    )
    case_name: str = Attribute(
        lambda d, params: d.case_name, strategy=overwrite
    )
    case_name_full: str = Attribute(
        lambda d, params: d.case_name_full,
        strategy=overwrite,
    )
    case_name_short: str = Attribute(
        lambda d, params: d.case_name_short, strategy=overwrite
    )
    docket_number: str = Attribute(
        lambda d, params: d.docket_number,
        strategy=overwrite,
    )
    docket_number_raw: str = Attribute(
        lambda d, params: d.docket_number, strategy=overwrite
    )
    parties: list[Party] = ManyToManyRelation(
        PartyMerger,
        through=PartyTypeMerger,
        transform=_docket_parties,
    )
