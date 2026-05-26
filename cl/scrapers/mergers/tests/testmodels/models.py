"""Test-only Django models for exercising the merger framework.

These mirror the *shape* of real CL models (Docket / DocketEntry / Party /
PartyType / Court) but are deliberately minimal — no pghistory tracking,
no PG-specific fields, no foreign keys to apps outside testmodels. This
lets the merger framework's L4+ tests run against an in-memory SQLite
database without dragging in PG dependencies.

Routed to the ``mergers_test`` database via ``MergersTestRouter``.
"""

from django.db import models


class TCourt(models.Model):
    """Stand-in for ``cl.search.Court``. Pre-resolved by caller."""

    id = models.CharField(max_length=15, primary_key=True)
    name = models.CharField(max_length=255)

    class Meta:
        app_label = "mergers_testmodels"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"TCourt({self.id})"


class TDocket(models.Model):
    """Stand-in for ``cl.search.Docket`` (root aggregate model)."""

    court = models.ForeignKey(
        TCourt, on_delete=models.CASCADE, related_name="dockets"
    )
    docket_number_core = models.CharField(max_length=64)
    case_name = models.CharField(max_length=255, blank=True)
    date_filed = models.DateField(null=True, blank=True)
    source = models.IntegerField(default=0)
    # Forward OneToOne to TDocketHeader — exercises ``OwnedChild``
    # semantics in the framework (FK lives on the parent).
    header = models.OneToOneField(
        "TDocketHeader",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        app_label = "mergers_testmodels"
        unique_together = [("court", "docket_number_core")]

    def __str__(self) -> str:  # pragma: no cover
        return f"TDocket({self.court_id}/{self.docket_number_core})"


class TDocketEntry(models.Model):
    """Stand-in for a docket-entry-style child model."""

    docket = models.ForeignKey(
        TDocket, on_delete=models.CASCADE, related_name="entries"
    )
    date_filed = models.DateField(null=True, blank=True)
    entry_type = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    sequence_number = models.CharField(max_length=16, blank=True)

    class Meta:
        app_label = "mergers_testmodels"


class TParty(models.Model):
    """Stand-in for a shared external entity (Party-like).

    ``description`` is a non-NK scalar used by ExternalNodeRef field-update
    tests — its only role is to be a writable column on a matched
    ``ExternalNodeRef`` row.
    """

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        app_label = "mergers_testmodels"


class TPartyType(models.Model):
    """Join row connecting TDocket and TParty with extra role data."""

    docket = models.ForeignKey(
        TDocket, on_delete=models.CASCADE, related_name="party_types"
    )
    party = models.ForeignKey(
        TParty, on_delete=models.CASCADE, related_name="party_types"
    )
    role = models.CharField(max_length=64)
    extra_info = models.TextField(blank=True)

    class Meta:
        app_label = "mergers_testmodels"


class TDocument(models.Model):
    """Stand-in for a document/attachment hanging off a docket entry —
    third level of the aggregate tree (Docket -> Entry -> Document)."""

    entry = models.ForeignKey(
        TDocketEntry, on_delete=models.CASCADE, related_name="documents"
    )
    media_id = models.CharField(max_length=64)
    description = models.TextField(blank=True)

    class Meta:
        app_label = "mergers_testmodels"


class TCounsel(models.Model):
    """Stand-in for an attorney/counsel-association row reachable from
    ``TDocket`` via a *second* path to ``TParty`` (the first being
    ``TPartyType.party``).

    The merger framework needs to discover *every* declared path from
    the root to a given ``ExternalNodeRef`` class so the prefetched candidate
    set is the union of rows reachable via any path. This model exists
    only to exercise that multi-path behavior in tests — a Party
    reachable via ``Docket.party_types.party`` *or*
    ``Docket.counsels.party`` should resolve identically.
    """

    docket = models.ForeignKey(
        TDocket, on_delete=models.CASCADE, related_name="counsels"
    )
    party = models.ForeignKey(
        TParty, on_delete=models.CASCADE, related_name="counsels"
    )

    class Meta:
        app_label = "mergers_testmodels"


class TBridge(models.Model):
    """Stand-in for a cross-aggregate bridge row (CaseTransfer shape).

    Two FK columns point to ``TDocket`` with distinct ``related_name``
    values so the same row is reachable from either docket as
    ``docket.origin_bridges`` or ``docket.destination_bridges``. Both
    FKs are nullable so a merge can insert the row with only one side
    filled, leaving the other side for a later merge to fill in via
    ``BridgeNode``'s parent-FK auto-injection on matched-row update.

    The NK identifies the bridge globally — ``label`` is unique across
    all rows regardless of which dockets it links.
    """

    label = models.CharField(max_length=64, unique=True)
    origin_docket = models.ForeignKey(
        TDocket,
        on_delete=models.CASCADE,
        related_name="origin_bridges",
        null=True,
        blank=True,
    )
    destination_docket = models.ForeignKey(
        TDocket,
        on_delete=models.CASCADE,
        related_name="destination_bridges",
        null=True,
        blank=True,
    )
    note = models.TextField(blank=True)

    class Meta:
        app_label = "mergers_testmodels"


class TDocketHeader(models.Model):
    """Stand-in for a row owned by ``TDocket`` via a forward
    OneToOneField on ``TDocket`` (``OwnedChild`` test fixture).

    Note the FK direction: ``TDocket.header`` points to this row, not
    the other way around. That makes this row's lifecycle parent-owned
    but its FK column lives on ``TDocket``.
    """

    title = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        app_label = "mergers_testmodels"
