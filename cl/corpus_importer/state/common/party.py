from collections.abc import Callable, Sequence
from typing import Any, ClassVar, cast, override

from juriscraper.state.docket import Party as ScrapeParty
from juriscraper.state.docket import Representative as ScrapeRepresentative

from cl.corpus_importer.state.merger import (
    Ancestor,
    Fn,
    ManyStrategy,
    ManyToManyRelation,
    Merger,
    MergerConfig,
    MergerState,
    Params,
    RelatedParams,
    Scrape,
    ThroughParameters,
)
from cl.people_db.models import Attorney, Party, PartyType, Role
from cl.search.models import Docket


class RoleMerger[AttyType: ScrapeRepresentative, ParamType](
    Merger[AttyType, ThroughParameters[ParamType], Role]
):
    config: ClassVar[MergerConfig[Role]] = MergerConfig(model=Role)

    docket: Docket = Ancestor(Docket)


class AttorneyMerger[
    AttyType: ScrapeRepresentative,
    ParamType: RelatedParams[RelatedParams],
](Merger[AttyType, ParamType, Attorney]):
    config: ClassVar[MergerConfig[Attorney]] = MergerConfig(model=Attorney)

    name: str = Scrape(ScrapeRepresentative).name

    @override
    def lookup(
        self,
        state: MergerState.Lookup[
            AttyType,
            ParamType,
            Attorney,
        ],
    ) -> MergerState.LookupOutput[
        AttyType,
        ParamType,
        Attorney,
    ]:
        # Attorneys have no natural key, so treat the name as unique within
        # the parent docket, like the RECAP mergers do.
        docket = cast(Docket, state.params.params.parent)

        return state.resolve(
            self.manager.filter(
                name=self.name, roles__docket=docket
            ).distinct(),
        )


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
    config: ClassVar[MergerConfig[Party]] = MergerConfig(
        model=Party, key=("name",)
    )

    attorneys: Sequence[Attorney] = AttorneyRelation()
    name: str = Scrape(ScrapeParty).name

    @override
    def lookup(
        self,
        state: MergerState.Lookup[
            PType,
            ParamType,
            Party,
        ],
    ) -> MergerState.LookupOutput[
        PType,
        ParamType,
        Party,
    ]:
        """Find the party by its natural key within the parent docket.

        The default key is the name, like the RECAP mergers use; a source that
        identifies parties more reliably sets `key` to that field instead.
        """
        docket = cast(Docket, state.params.parent)
        return state.resolve(
            self._key_query(state)
            .filter(party_types__docket=docket)
            .distinct()
            .order_by("date_created"),
        )


class PartyTypeMerger[PType: ScrapeParty[ScrapeRepresentative], ParamType](
    Merger[PType, ThroughParameters[ParamType], PartyType]
):
    config: ClassVar[MergerConfig[PartyType]] = MergerConfig(model=PartyType)

    name: str = Scrape(ScrapeParty).party_type.value.title()
