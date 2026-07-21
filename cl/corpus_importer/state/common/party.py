from collections.abc import Callable
from typing import Any, ClassVar, cast

from django.db.models import Model, QuerySet
from juriscraper.state.docket import Party as ScrapeParty
from juriscraper.state.docket import Representative as ScrapeRepresentative

from cl.corpus_importer.state.merger import (
    Attribute,
    ManyToManyRelation,
    Merger,
    RelatedParams,
    ThroughParameters,
)
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.search.models import Docket


def _role_docket(
    representative: ScrapeRepresentative,
    params: ThroughParameters[ThroughParameters[Any]],
) -> Docket:
    return cast(Docket, params.params.parent)


class RoleMerger[AttyType: ScrapeRepresentative, ParamType](
    Merger[AttyType, ThroughParameters[ParamType], Role]
):
    model: ClassVar[type[Model]] = Role

    docket: Docket = Attribute(_role_docket)


def _representative_name(
    representative: ScrapeRepresentative, params: Any
) -> str:
    return representative.name


class AttorneyMerger[AttyType: ScrapeRepresentative, ParamType](
    Merger[AttyType, RelatedParams[RelatedParams[ParamType]], Attorney]
):
    model: ClassVar[type[Model]] = Attorney

    name: str = Attribute(_representative_name)

    def query(self) -> QuerySet[Attorney]:
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


def _party_name(party: ScrapeParty[ScrapeRepresentative], params: Any) -> str:
    return party.name


def AttorneyRelation(
    *,
    attorney: type[Merger[Any, Any, Any]] = AttorneyMerger,
    role: type[Merger[Any, Any, Any]] = RoleMerger,
    transform: Callable[[Any, Any], list[Any]] = _party_representatives,
) -> list[Attorney]:
    return ManyToManyRelation(attorney, role, transform)


class PartyMerger[PType: ScrapeParty[ScrapeRepresentative], ParamType](
    Merger[PType, RelatedParams[ParamType], Party]
):
    model: ClassVar[type[Model]] = Party

    attorneys: list[Attorney] = AttorneyRelation()
    name: str = Attribute(_party_name)

    def query(self) -> QuerySet[Party]:
        # Parties have no natural key, so treat the name as unique within the
        # parent docket, like the RECAP mergers do.
        docket = cast(Docket, self.params.parent)
        return self.manager.filter(
            name=self.transformed["name"], party_types__docket=docket
        ).distinct()


def _party_type_name(
    party: ScrapeParty[ScrapeRepresentative], params: Any
) -> str:
    return party.party_type.value.title()


class PartyTypeMerger[PType: ScrapeParty[ScrapeRepresentative], ParamType](
    Merger[PType, ThroughParameters[ParamType], PartyType]
):
    model: ClassVar[type[Model]] = PartyType

    name: str = Attribute(_party_type_name)
