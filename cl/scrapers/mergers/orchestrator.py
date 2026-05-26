"""Phase orchestration.

``merge_one(scrape)`` is the convenience entry point — runs all four
phases inside a single ``transaction.atomic()`` and returns the
``MergeOutcome``.

Batch callers who want to span multiple merges in one transaction
should call the phase functions directly:

.. code-block:: python

    with transaction.atomic(using="default"):
        for scrape in batch:
            paired = build_paired_tree(scrape)
            diffed = reconcile(paired)
            outcome = apply(diffed)
            # ...handle outcome.follow_ups after commit...

Schema validation runs at class-definition time (see
``__pydantic_init_subclass__``) so ``merge_one`` doesn't re-validate.

See cl/scrapers/MERGERS_IN_THEORY.md.
"""

from cl.scrapers.mergers.apply import apply
from cl.scrapers.mergers.diff import reconcile
from cl.scrapers.mergers.nodes import Aggregate
from cl.scrapers.mergers.outcome import MergeOutcome
from cl.scrapers.mergers.paired import build_paired_tree


def merge_one[ModelT](
    scrape: Aggregate[ModelT], *, using: str = "default"
) -> MergeOutcome[ModelT]:
    """Run all four phases against ``scrape`` and commit atomically.

    Raises propagate out of the ``atomic()`` block so the entire merge
    rolls back on any error.

    :param scrape: the constructed Aggregate (phase 1's output).
    :param using: DB alias for the transaction. Defaults to
        ``"default"``; tests against the in-memory sqlite use
        ``"mergers_test"``.
    """
    from django.db import transaction

    with transaction.atomic(using=using):
        paired = build_paired_tree(scrape)
        diffed = reconcile(paired)
        return apply(diffed)
