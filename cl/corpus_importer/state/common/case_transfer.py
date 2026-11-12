"""Base merger for ``CaseTransfer`` rows created while merging a docket.

Transfers come from the ``transfers`` list of Juriscraper's standard state
docket format. Only inbound transfers are merged: the docket being merged is
the transfer's destination and the scraped ``DocketTransfer`` describes the
origin. The origin docket FK is intentionally left unset here; back-filling
both FKs is handled later by ``CaseTransfer.fill_null_dockets``.
"""

import logging
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, ClassVar, cast, override

from juriscraper.state.docket import Docket as ScrapeDocket
from juriscraper.state.docket import (
    DocketTransfer,
    TransferDirection,
    TransferReason,
)

from cl.corpus_importer.state.merger import (
    Ancestor,
    Constant,
    Fn,
    ManyStrategy,
    Merger,
    MergerConfig,
    MergerState,
    OneToManyRelation,
    Params,
    RelatedParams,
    Scrape,
    WithStrategy,
    overwrite,
)
from cl.corpus_importer.state.merger.specifications import AttributeMerger
from cl.search.models import CaseTransfer, Docket

logger = logging.getLogger(__name__)

TRANSFER_REASON_MAP: dict[TransferReason, int] = {
    TransferReason.APPEAL: CaseTransfer.APPEAL,
    TransferReason.WORKLOAD: CaseTransfer.WORKLOAD,
    TransferReason.JURISDICTION: CaseTransfer.JURISDICTION,
}


def inbound_transfers[TransferType: DocketTransfer](
    docket_data: ScrapeDocket[TransferType, Any, Any], params: Any
) -> list[TransferType]:
    """Filter a docket's transfers down to the ones a `CaseTransfer` can be created for. Skipped transfers are logged but do not fail the merge.

    Args:
        docket_data: The scraped docket.
        params: Unused.

    Returns:
        The transfers to merge.
    """
    transfers = []
    for transfer in docket_data.transfers:
        if transfer.direction is not TransferDirection.INBOUND:
            # Outbound transfers are not merged yet; the destination court's
            # docket will report the same transfer as inbound.
            logger.warning(
                "Skipping outbound CaseTransfer for docket %s to court %s",
                docket_data.docket_number,
                transfer.court_id,
            )
            continue
        if transfer.reason not in TRANSFER_REASON_MAP:
            logger.warning(
                "Skipping CaseTransfer for docket %s: unsupported transfer reason %s",
                docket_data.docket_number,
                transfer.reason,
            )
            continue
        if not transfer.docket_number:
            logger.warning(
                "Skipping CaseTransfer for docket %s: transfer from court %s has no docket number",
                docket_data.docket_number,
                transfer.court_id,
            )
            continue
        transfers.append(transfer)
    return transfers


def _destination_docket_id(
    transfer: DocketTransfer, params: RelatedParams[Any]
) -> int | None:
    if params.parent is not None:
        return params.parent.pk
    return None


class CaseTransferMerger[
    TransferType: DocketTransfer,
    ParamType: RelatedParams,
](Merger[TransferType, ParamType, CaseTransfer]):
    """Base merger for transfers into the docket being merged.

    The destination fields come from the parent docket and the origin docket
    number and transfer type from the scraped transfer; subclasses must
    define the ``origin_court_id`` attribute to translate the transfer's
    Juriscraper court ID to a CourtListener one.
    """

    config: ClassVar[MergerConfig] = MergerConfig(
        model=CaseTransfer,
        key=(
            "origin_court_id",
            "origin_docket_number",
            "destination_court_id",
            "destination_docket_number",
            "transfer_type",
        ),
    )

    destination_docket_id: int | None = Fn(_destination_docket_id)(
        Scrape(DocketTransfer), Params(RelatedParams)
    )
    origin_docket_number: str = WithStrategy(
        Scrape(DocketTransfer).docket_number, overwrite
    )
    transfer_type: int = WithStrategy(
        Constant(TRANSFER_REASON_MAP)[Scrape(DocketTransfer).reason], overwrite
    )
    destination_court_id: str = WithStrategy(
        Ancestor(Docket).court_id, overwrite
    )
    destination_docket_number: str = WithStrategy(
        Fn(lambda v: v or "")(Ancestor(Docket).docket_number), overwrite
    )
    # The standard docket format doesn't include transfer dates, so treat the
    # destination docket's filing date as the date the transfer occurred.
    transfer_date: date | None = WithStrategy(
        Ancestor(Docket).date_filed, overwrite
    )

    @override
    def lookup(
        self,
        state: MergerState.Lookup[
            TransferType,
            ParamType,
            CaseTransfer,
        ],
    ) -> MergerState.LookupOutput[
        TransferType,
        ParamType,
        CaseTransfer,
    ]:
        """Find an existing transfer to merge into.

        Prefer a partial transfer missing its destination docket FK so the FK
        can be filled in (see `update`); otherwise match a transfer
        already attached to the parent docket.

        Returns:
            The state resolving the candidate transfers.
        """
        # `super().lookup()` can't be used here. For a related merger
        # `self.manager` is the parent docket's reverse FK manager, so it would
        # constrain the lookup to `destination_docket = parent` and hide the
        # very partial transfers this method exists to find.
        candidates = CaseTransfer.objects.filter(
            **{name: getattr(self, name) for name in self.config.key}
        )
        fillable = candidates.filter(destination_docket__isnull=True)
        if fillable.exists():
            return state.resolve(fillable)

        return state.resolve(
            candidates.filter(destination_docket=state.params.parent)
        )


def CaseTransferRelation(
    merger: type[Merger[Any, Any, Any]],
    transform: Callable[[Any, Any], Sequence[Any]] = inbound_transfers,
    *,
    strategy: ManyStrategy = ManyStrategy.APPEND,
) -> list[CaseTransfer]:
    return OneToManyRelation(
        merger,
        cast(AttributeMerger, Fn(transform)(Scrape(Any), Params(Any))),
        strategy=strategy,
    )
