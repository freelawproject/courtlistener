"""Base merger for ``CaseTransfer`` rows created while merging a docket.

Transfers come from the ``transfers`` list of Juriscraper's standard state
docket format. Only inbound transfers are merged: the docket being merged is
the transfer's destination and the scraped ``DocketTransfer`` describes the
origin. The origin docket FK is intentionally left unset here; back-filling
both FKs is handled later by ``CaseTransfer.fill_null_dockets``.
"""

import logging
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from typing import Any, ClassVar, cast, override

from django.db.models import Model, QuerySet
from juriscraper.state.docket import Docket as ScrapeDocket
from juriscraper.state.docket import (
    DocketTransfer,
    TransferDirection,
    TransferReason,
)

from cl.corpus_importer.state.merger import (
    Attribute,
    ManyStrategy,
    Merger,
    OneToManyRelation,
    RelatedParams,
    overwrite,
    overwrite_if_present,
)
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
    """Filter a docket's transfers down to the ones a `CaseTransfer` can be
    created for. Skipped transfers are logged but do not fail the merge.

    :param docket_data: The scraped docket.
    :return: The transfers to merge."""
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


def _origin_docket_number(transfer: DocketTransfer, params: Any) -> str:
    return transfer.docket_number


def _destination_docket_id(
    transfer: DocketTransfer, params: RelatedParams[Any]
) -> int | None:
    if params.parent is not None:
        return params.parent.pk
    return None


def _transfer_type(transfer: DocketTransfer, params: Any) -> int:
    return TRANSFER_REASON_MAP[transfer.reason]


def _destination_court_id(scrape: Any, params: RelatedParams[Any]) -> str:
    return cast(str, cast(Docket, params.parent).court_id)


def _destination_docket_number(scrape: Any, params: RelatedParams[Any]) -> str:
    return cast(Docket, params.parent).docket_number or ""


def _transfer_date(scrape: Any, params: RelatedParams[Any]) -> date | None:
    # The standard docket format doesn't include transfer dates, so treat the
    # destination docket's filing date as the date the transfer occurred.
    return cast(Docket, params.parent).date_filed


class CaseTransferMerger[TransferType: DocketTransfer, ParamType](
    Merger[TransferType, RelatedParams[ParamType], CaseTransfer], abstract=True
):
    """Base merger for transfers into the docket being merged.

    The destination fields come from the parent docket and the origin docket
    number and transfer type from the scraped transfer; subclasses must
    define the ``origin_court_id`` attribute to translate the transfer's
    Juriscraper court ID to a CourtListener one."""

    model: ClassVar[type[Model]] = CaseTransfer
    # Both ends are identified by court and docket number rather than by FK so
    # a transfer can be matched with only one end present in the DB. Matching
    # on `destination_docket_id` would restrict the lookup to transfers already
    # attached to this docket, making the partial transfer in `query` and the
    # back-fill in `update_existing` unreachable.
    key: ClassVar[Iterable[str]] = [
        "origin_court_id",
        "origin_docket_number",
        "destination_court_id",
        "destination_docket_number",
        "transfer_type",
    ]

    destination_docket_id: int = Attribute(
        _destination_docket_id,
        strategy=overwrite_if_present,
    )
    origin_docket_number: str = Attribute(
        _origin_docket_number, strategy=overwrite
    )
    transfer_type: int = Attribute(_transfer_type, strategy=overwrite)
    destination_court_id: str = Attribute(
        _destination_court_id, strategy=overwrite
    )
    destination_docket_number: str = Attribute(
        _destination_docket_number, strategy=overwrite
    )
    transfer_date: date | None = Attribute(_transfer_date, strategy=overwrite)

    @override
    def query(self) -> QuerySet[CaseTransfer]:
        """Find an existing transfer to merge into.

        Prefer a partial transfer missing its destination docket FK so the FK
        can be filled in (see `update_existing`); otherwise match a transfer
        already attached to the parent docket.

        :return: The queryset to find the transfer."""
        # `super().query()` can't be used here. For a related merger
        # `self.manager` is the parent docket's reverse FK manager, so it would
        # constrain the lookup to `destination_docket = parent` and hide the
        # very partial transfers this method exists to find.
        candidates = cast(
            QuerySet[CaseTransfer],
            CaseTransfer.objects.filter(
                **{name: self.transformed[name] for name in self.key}
            ),
        )
        fillable = candidates.filter(destination_docket__isnull=True)
        if fillable.exists():
            return fillable
        return candidates.filter(destination_docket=self.params.parent)


def CaseTransferRelation(
    merger: type[Merger[Any, Any, Any]],
    transform: Callable[[Any, Any], Sequence[Any]] = inbound_transfers,
    *,
    strategy: ManyStrategy = ManyStrategy.APPEND,
) -> list[CaseTransfer]:
    return OneToManyRelation(
        merger,
        transform,
        strategy=strategy,
    )
