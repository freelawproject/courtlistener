from typing import Any, ClassVar, cast

from django.db.models import Model
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


class AttorneyMerger[AttyType: ScrapeRepresentative, ParamType](
    Merger[AttyType, ParamType, Attorney]
):
    model: ClassVar[type[Model]] = Attorney


def _party_representatives[RType: ScrapeRepresentative](
    party: ScrapeParty[RType], params: Any
) -> list[RType]:
    return party.representatives


def _party_name(party: ScrapeParty[ScrapeRepresentative], params: Any) -> str:
    return party.name


class PartyMerger[PType: ScrapeParty[ScrapeRepresentative], ParamType](
    Merger[PType, RelatedParams[ParamType], Party]
):
    model: ClassVar[type[Model]] = Party

    attorneys: list[Attorney] = ManyToManyRelation(
        AttorneyMerger, RoleMerger, _party_representatives
    )
    name: str = Attribute(_party_name)


def _party_type_name(
    party: ScrapeParty[ScrapeRepresentative], params: Any
) -> str:
    return party.party_type.value


class PartyTypeMerger[PType: ScrapeParty[ScrapeRepresentative], ParamType](
    Merger[PType, ThroughParameters[ParamType], PartyType]
):
    model: ClassVar[type[Model]] = PartyType

    name: str = Attribute(_party_type_name)
