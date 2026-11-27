"""Base mergers for scraped parties, their attorneys, and their roles."""

from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from django.db.models import F
from juriscraper.state.docket import Party as ScrapeParty
from juriscraper.state.docket import Representative as ScrapeRepresentative

from cl.corpus_importer.state.merger import (
    Ancestor,
    Fn,
    Key,
    ManyStrategy,
    ManyToManyRelation,
    Match,
    Merger,
    MergerConfig,
    Params,
    Pool,
    RelatedParams,
    Relatives,
    Scrape,
    ThroughParameters,
)
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.search.models import Docket


class RoleMerger[AttyType: ScrapeRepresentative, ParamType](
    Merger[AttyType, ThroughParameters[ParamType], Role]
):
    """Merger for the role linking an attorney to a party on the parent docket."""

    config: ClassVar[MergerConfig[Role]] = MergerConfig(model=Role)

    docket: Docket = Ancestor(Docket)


class AttorneyMerger[
    AttyType: ScrapeRepresentative,
    ParamType: RelatedParams[RelatedParams],
](Merger[AttyType, ParamType, Attorney]):
    """Merger for a scraped party representative into an ``Attorney``."""

    config: ClassVar[MergerConfig[Attorney]] = MergerConfig(model=Attorney)
    # Attorneys have no natural key, so the name is treated as unique within
    # the docket, like the RECAP mergers do.
    pool: ClassVar[Pool | None] = Relatives(roles__docket=Ancestor(Docket))
    match: ClassVar[Match] = Match(Key("name"))

    name: str = Scrape(ScrapeRepresentative).name


def _party_representatives[RType: ScrapeRepresentative](
    party: ScrapeParty[RType], params: Any
) -> Sequence[RType]:
    return party.representatives


def AttorneyRelation(
    *,
    attorney: type[Merger[Any, Any, Any]] = AttorneyMerger,
    role: type[Merger[Any, Any, Any]] = RoleMerger,
    transform: Callable[[Any, Any], Sequence[Any]] = _party_representatives,
) -> Sequence[Attorney]:
    """Declare a party's attorneys as a many-to-many relation through roles.

    Defaults to merging the scraped party's representatives.
    """
    return ManyToManyRelation(
        attorney,
        Fn(transform)(Scrape(Any), Params(Any)),
        role,
        strategy=ManyStrategy.DISASSOCIATE,
    )


class PartyMerger[
    PType: ScrapeParty[ScrapeRepresentative],
    ParamType: RelatedParams,
](Merger[PType, ParamType, Party]):
    """Merger for a scraped party and its attorneys into a ``Party``."""

    config: ClassVar[MergerConfig[Party]] = MergerConfig(model=Party)
    # The name is the default identity, like the RECAP mergers use; a source
    # that identifies parties more reliably declares its own `match`. The role
    # the party holds on the docket is annotated for matches that read it.
    pool: ClassVar[Pool | None] = Relatives(
        party_types__docket=Ancestor(Docket)
    ).annotate(role=F("party_types__name"))
    match: ClassVar[Match] = Match(Key("name"))

    attorneys: Sequence[Attorney] = AttorneyRelation()
    name: str = Scrape(ScrapeParty).name


class PartyTypeMerger[PType: ScrapeParty[ScrapeRepresentative], ParamType](
    Merger[PType, ThroughParameters[ParamType], PartyType]
):
    """Merger for the party type linking a party to the parent docket."""

    config: ClassVar[MergerConfig[PartyType]] = MergerConfig(model=PartyType)

    name: str = Scrape(ScrapeParty).party_type.value.title()
