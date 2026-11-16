"""Base mergers for scraped parties, their attorneys, and their roles."""

from collections.abc import Callable, Iterable
from typing import Any, ClassVar, cast

from django.db.models import Model, QuerySet
from juriscraper.state.docket import Party as ScrapeParty
from juriscraper.state.docket import Representative as ScrapeRepresentative

from cl.corpus_importer.state.merger import (
    Ancestor,
    Fn,
    ManyStrategy,
    ManyToManyRelation,
    Merger,
    Params,
    RelatedParams,
    Scrape,
    ThroughParameters,
)
from cl.corpus_importer.state.merger.specifications import AttributeMerger
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.search.models import Docket


class RoleMerger[AttyType: ScrapeRepresentative, ParamType](
    Merger[AttyType, ThroughParameters[ParamType], Role]
):
    """Merger for the role linking an attorney to a party on the parent docket."""

    model: ClassVar[type[Model]] = Role

    docket: Docket = Ancestor(Docket)


class AttorneyMerger[AttyType: ScrapeRepresentative, ParamType](
    Merger[AttyType, RelatedParams[RelatedParams[ParamType]], Attorney]
):
    """Merger for a scraped party representative into an ``Attorney``."""

    model: ClassVar[type[Model]] = Attorney

    name: str = Scrape(ScrapeRepresentative).name

    def query(self) -> QuerySet[Attorney]:
        """Find attorneys with the representative's name on the parent docket."""
        # Attorneys have no natural key, so treat the name as unique within
        # the parent docket, like the RECAP mergers do.
        docket = cast(Docket, self.params.params.parent)
        return self.manager.filter(
            name=self.transformed["name"], roles__docket=docket
        ).distinct()


def _party_representatives[RType: ScrapeRepresentative](
    party: ScrapeParty[RType], params: Any
) -> list[RType]:
    return party.representatives


def AttorneyRelation(
    *,
    attorney: type[Merger[Any, Any, Any]] = AttorneyMerger,
    role: type[Merger[Any, Any, Any]] = RoleMerger,
    transform: Callable[[Any, Any], list[Any]] = _party_representatives,
) -> list[Attorney]:
    """Declare a party's attorneys as a many-to-many relation through roles.

    Defaults to merging the scraped party's representatives.
    """
    return ManyToManyRelation(
        attorney,
        cast(AttributeMerger, Fn(transform)(Scrape(Any), Params(Any))),
        role,
        strategy=ManyStrategy.DISASSOCIATE,
    )


class PartyMerger[PType: ScrapeParty[ScrapeRepresentative], ParamType](
    Merger[PType, RelatedParams[ParamType], Party]
):
    """Merger for a scraped party and its attorneys into a ``Party``."""

    model: ClassVar[type[Model]] = Party
    key: ClassVar[Iterable[str]] = ["name"]

    attorneys: list[Attorney] = AttorneyRelation()
    name: str = Scrape(ScrapeParty).name

    def query(self) -> QuerySet[Party]:
        """Find the party by its natural key within the parent docket.

        The default key is the name, like the RECAP mergers use; a source that
        identifies parties more reliably sets `key` to that field instead.
        """
        docket = cast(Docket, self.params.parent)
        return super().query().filter(party_types__docket=docket).distinct()


class PartyTypeMerger[PType: ScrapeParty[ScrapeRepresentative], ParamType](
    Merger[PType, ThroughParameters[ParamType], PartyType]
):
    """Merger for the party type linking a party to the parent docket."""

    model: ClassVar[type[Model]] = PartyType

    name: str = Scrape(ScrapeParty).party_type.value.title()
