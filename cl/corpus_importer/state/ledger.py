"""The record of outstanding loader work.

This is additional bookkeeping to verify that we haven't dropped anything
during our celery run. We keep track of mergers/extractions in flight, and
report in the end if anything is missing.

Every key is written with a TTL, so a run nobody comes back to verify does not
leave its ledger behind for good.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from django.utils import timezone
from redis import Redis

from cl.corpus_importer.state.utils import MergeResult
from cl.lib.redis_utils import get_redis_interface

logger = logging.getLogger(__name__)

LEDGER_TTL: Final = 60 * 60 * 24 * 7
"""Seconds a ledger outlives its last write. A week is long enough to come
back to a weekend's run on Monday and short enough that abandoned runs clear
themselves out."""

PARTS: Final = ("pending", "counts", "creates", "updates", "started")
"""Every key a ledger writes, for `clear` to take away together."""


@dataclass(frozen=True)
class LedgerTotals:
    """What a run's ledger adds up to.

    These span the run database rather than any one pass over it: a load
    resumed with `--auto-resume` adds to the totals its first attempt left,
    which is the point of not clearing them.

    :ivar dispatched: Rows sent to the merge queue.
    :ivar merged: Rows whose merge came back clean.
    :ivar rejected: Rows whose merge ran and reported failures.
    :ivar errored: Rows whose merge could not run to a verdict at all.
    :ivar documents: Documents sent to the extraction queue.
    :ivar creates: Objects created, counted per model name.
    :ivar updates: Objects updated, counted per model name.
    """

    dispatched: int = 0
    merged: int = 0
    rejected: int = 0
    errored: int = 0
    documents: int = 0
    creates: dict[str, int] = field(default_factory=dict)
    updates: dict[str, int] = field(default_factory=dict)

    @property
    def failed(self) -> int:
        """Rows that did not merge."""
        return self.rejected + self.errored


class LoadLedger:
    """One run's ledger, keyed off the run database it loads."""

    def __init__(self, key: str, ttl: int = LEDGER_TTL) -> None:
        """
        :param key: The run's key, which the ledger's own keys hang off.
        :param ttl: Seconds each key outlives its last write.
        """
        self.key = key
        self.ttl = ttl

    @property
    def _redis(self) -> Redis:
        """The Redis the ledger is kept in."""
        return get_redis_interface("CACHE")

    def _name(self, part: str) -> str:
        """The Redis key holding one part of the ledger."""
        return f"{self.key}:{part}"

    def clear(self) -> None:
        """Drop the whole ledger, for a run starting over from the top."""
        try:
            self._redis.delete(*(self._name(part) for part in PARTS))
        except Exception:
            logger.exception("Could not clear the ledger at %s", self.key)

    def start(self) -> datetime:
        """Mark when this run began, and say when that was.

        :return: When the run began, whether this call set it or an earlier
            one did.
        """
        now = timezone.now()
        try:
            name = self._name("started")
            # NX so a resumed run keeps the moment its first attempt set.
            self._redis.set(name, now.isoformat(), nx=True, ex=self.ttl)
            if stored := self._redis.get(name):
                return datetime.fromisoformat(stored)
        except Exception:
            logger.exception("Could not start the ledger at %s", self.key)
        return now

    def started(self) -> datetime | None:
        """When this run began, or `None` if nothing recorded it."""
        try:
            if stored := self._redis.get(self._name("started")):
                return datetime.fromisoformat(stored)
        except Exception:
            logger.exception("Could not read the ledger at %s", self.key)
        return None

    def dispatched(self, row: int, label: str) -> None:
        """Record that `row` has gone to the merge queue.

        :param row: The row's position in the run database's query.
        :param label: Something to recognise the row by, such as its docket
            number, so the report can name it without a second lookup.
        """
        try:
            name = self._name("pending")
            pipeline = self._redis.pipeline()
            pipeline.hset(name, str(row), label or str(row))
            pipeline.expire(name, self.ttl)
            pipeline.execute()
        except Exception:
            logger.exception("Could not dispatch row %s to %s", row, self.key)
        self._count("dispatched")

    def merged(self, row: int, result: MergeResult[Any]) -> None:
        """Record that `row` merged cleanly, and what its merge wrote.

        :param row: The row's position in the run database's query.
        :param result: The merge's result, counted into the run's totals.
        """
        self._settle(row, "merged", result)

    def rejected(self, row: int, result: MergeResult[Any]) -> None:
        """Record that `row`'s merge failed.

        :param row: The row's position in the run database's query.
        :param result: The merge's result. A merge that failed partway still
            created and updated objects worth counting.
        """
        self._settle(row, "rejected", result)

    def errored(self, row: int) -> None:
        """Record that `row`'s merge never reached a verdict.

        Kept apart from `rejected` because the two want different people: a
        rejected row is a scrape to go and fix, an errored one is a row to
        re-run. See `LedgerTotals`.

        :param row: The row's position in the run database's query.
        """
        self._settle(row, "errored", None)

    def extracting(self, documents: int) -> None:
        """Record document sent for text extraction, to check up on later.

        :param documents: How many went to the extraction queue.
        """
        if documents:
            self._count("documents", documents)

    def outstanding_count(self) -> int:
        """How many dispatched rows are pending an outcome.

        This is what a load's wait polls on.
        """
        try:
            return int(self._redis.hlen(self._name("pending")))
        except Exception:
            logger.exception("Could not read the ledger at %s", self.key)
            return 0

    def outstanding(self, limit: int) -> dict[int, str]:
        """Some(limit) of the rows that never reported either way, to name in a
        report.

        :param limit: The most to return.
        :return: Row number to the label it was dispatched under, lowest rows
            first.
        """
        try:
            _, pending = self._redis.hscan(self._name("pending"), count=limit)
        except Exception:
            logger.exception("Could not read the ledger at %s", self.key)
            return {}
        rows = sorted((int(row), label) for row, label in pending.items())
        return dict(rows[:limit])

    def pending_key(self) -> str:
        """The Redis key holding every outstanding row, for a report to point
        at when it can only name a few of them."""
        return self._name("pending")

    def totals(self) -> LedgerTotals:
        """Everything the run's merges reported, added up."""
        try:
            counts = self._redis.hgetall(self._name("counts"))
            creates = self._redis.hgetall(self._name("creates"))
            updates = self._redis.hgetall(self._name("updates"))
        except Exception:
            logger.exception("Could not read the ledger at %s", self.key)
            return LedgerTotals()
        return LedgerTotals(
            dispatched=int(counts.get("dispatched", 0)),
            merged=int(counts.get("merged", 0)),
            rejected=int(counts.get("rejected", 0)),
            errored=int(counts.get("errored", 0)),
            documents=int(counts.get("documents", 0)),
            creates={model: int(n) for model, n in creates.items()},
            updates={model: int(n) for model, n in updates.items()},
        )

    def _settle(
        self, row: int, outcome: str, result: MergeResult[Any] | None
    ) -> None:
        """Take `row` off the pending hash and count what its merge did."""
        try:
            self._redis.hdel(self._name("pending"), str(row))
        except Exception:
            logger.exception("Could not settle row %s of %s", row, self.key)
        self._count(outcome)
        if result is None:
            return
        for part, counts in (
            ("creates", result.creates),
            ("updates", result.updates),
        ):
            if not counts:
                continue
            try:
                name = self._name(part)
                pipeline = self._redis.pipeline()
                for model, pks in counts.items():
                    pipeline.hincrby(name, model, len(pks))
                pipeline.expire(name, self.ttl)
                pipeline.execute()
            except Exception:
                logger.exception(
                    "Could not count %s against %s", part, self.key
                )

    def _count(self, field_name: str, by: int = 1) -> None:
        """Add to one of the run's counters, and keep it alive."""
        try:
            name = self._name("counts")
            pipeline = self._redis.pipeline()
            pipeline.hincrby(name, field_name, by)
            pipeline.expire(name, self.ttl)
            pipeline.execute()
        except Exception:
            logger.exception(
                "Could not count %s against %s", field_name, self.key
            )
