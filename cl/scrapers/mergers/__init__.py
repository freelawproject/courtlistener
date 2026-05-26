"""CourtListener merger framework.

Public API. See cl/scrapers/MERGERS_IN_THEORY.md for the design.

Typical use:

.. code-block:: python

    from cl.scrapers.mergers import (
        Aggregate, InternalNode, ExternalNodeRef, PreResolvedRef,
        ScrapeWins, ScrapeClobbers, parent, merge_one,
    )

    class TexasDocket(
        Aggregate[Docket],
        default_field=ScrapeWins,
        default_collection=ScrapeClobbers,
        lock_for_update=True,
    ):
        natural_key = ("court", "docket_number_core")
        court: PreResolvedRef[Court]
        docket_number_core: str
        ...

    outcome = merge_one(scrape)
    for fu in outcome.follow_ups:
        transaction.on_commit(fu)
"""

from cl.scrapers.mergers.apply import apply
from cl.scrapers.mergers.diff import (
    CreateOp,
    DeleteOp,
    DiffedChildren,
    DiffedNode,
    NoOp,
    UpdateOp,
    reconcile,
)
from cl.scrapers.mergers.follow_up import FollowUp
from cl.scrapers.mergers.kent import IngestFile, KentMerger
from cl.scrapers.mergers.nodes import (
    AbsencePolicy,
    Aggregate,
    BridgeNode,
    CreateIfMissing,
    ErrorIfMissing,
    InternalNode,
    ExternalNodeRef,
    Node,
    NoopIfMissing,
    OwnedChild,
    PreResolvedRef,
    bound_django_model,
)
from cl.scrapers.mergers.orchestrator import merge_one
from cl.scrapers.mergers.outcome import MergeOutcome
from cl.scrapers.mergers.paired import (
    ChildNodes,
    PairedNode,
    build_paired_tree,
)
from cl.scrapers.mergers.refs import parent
from cl.scrapers.mergers.strategies import (
    CollectionStrategy,
    Custom,
    CustomCollection,
    DBClobbers,
    DBWins,
    ScalarStrategy,
    ScrapeClobbers,
    ScrapeWins,
    ScrapeWinsIfPresent,
    Union,
)
from cl.scrapers.mergers.validate import SchemaError, validate_schema

__all__ = [
    # Phase functions + orchestrator
    "merge_one",
    "build_paired_tree",
    "reconcile",
    "apply",
    # Node bases + policies
    "Node",
    "Aggregate",
    "InternalNode",
    "ExternalNodeRef",
    "OwnedChild",
    "BridgeNode",
    "PreResolvedRef",
    "AbsencePolicy",
    "CreateIfMissing",
    "ErrorIfMissing",
    "NoopIfMissing",
    "bound_django_model",
    # Strategies
    "ScalarStrategy",
    "ScrapeWins",
    "ScrapeWinsIfPresent",
    "DBWins",
    "Custom",
    "CollectionStrategy",
    "ScrapeClobbers",
    "DBClobbers",
    "Union",
    "CustomCollection",
    # Reference helpers
    "parent",
    # Kent driver base
    "KentMerger",
    "IngestFile",
    # Result types
    "MergeOutcome",
    "FollowUp",
    "PairedNode",
    "ChildNodes",
    "DiffedNode",
    "DiffedChildren",
    "CreateOp",
    "UpdateOp",
    "DeleteOp",
    "NoOp",
    # Validation
    "validate_schema",
    "SchemaError",
]
