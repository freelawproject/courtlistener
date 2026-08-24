"""Load the output of a jkent scrape run into CourtListener.

A jkent run leaves behind a SQLite database whose `results` table holds one row
per object the scraper yielded, each as a JSON blob in `data_json` tagged with
the scraper model that produced it.

`JKentScrapeLoader` bridges the two. A subclass supplies three things:

* `query`, the SQL that pulls one row per docket out of `results`, doing
  whatever joining and de-duplication the run needs;
* `normalize`, an optional hook that reshapes each row's payload in Python,
  for the part of the work SQL is a poor fit for;
* `scrape_model` and `merger`, the Pydantic model the payload is validated
  into and the merger that writes it to the database.

The run database is opened read-only, so a loader can never damage the record
of a scrape.
"""

import json
import logging
import sqlite3
import time
from abc import ABC
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, ClassVar, cast

from django.db import DatabaseError, transaction
from django.db.models import Model
from pydantic import BaseModel, ValidationError

from cl.corpus_importer.state.merger import Merger
from cl.corpus_importer.state.utils import MergeResult
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.indexing_utils import log_last_document_indexed
from cl.lib.redis_utils import get_redis_interface
from cl.search.state.shared import AbstractStateDocument

logger = logging.getLogger(__name__)

CHECKPOINT_EVERY = 250
"""Rows between checkpoints, and between progress logs. A load that dies
loses at most this many rows' worth of position, which it then re-merges on
resume -- harmless, because merging is idempotent."""


class UnusableScrape(Exception):
    """Raised by `normalize` for a row it refuses to merge.

    Use this where merging the row would write something wrong -- a scrape
    that stopped short of data the merger prunes against, say -- as opposed to
    a row there is simply nothing to do with. The distinction is what the load
    report is counted on: returning `None` from `normalize` counts the row as
    invalid, alongside the payloads that don't fit the model, while raising
    this counts it as failed, which says the run needs looking at.

    The message is logged, so it should name the row and say what is wrong
    with it.
    """


class RowOutcome(Enum):
    """Why a row did not become a scrape."""

    INVALID = auto()
    """The payload did not decode, did not validate against `scrape_model`,
    or `normalize` returned `None` for it."""
    FAILED = auto()
    """`normalize` raised `UnusableScrape`."""


@dataclass
class LoadReport:
    """What a load run did.

    The two rejection counts are separate because they call for different
    responses: `invalid` means the loader could not make a scrape of the row,
    which usually points at scraper drift, while `failed` is data that should
    have merged and did not.

    :ivar seen: Rows the query returned.
    :ivar invalid: Payloads that would not decode, failed validation against
        `scrape_model`, or that `normalize` passed over by returning `None`.
    :ivar failed: Rows `normalize` refused with `UnusableScrape`, plus merges
        that ran and reported failures -- which includes a merger turning a
        scrape away in its own `validate`.
    :ivar merged: Merges that came out clean.
    :ivar result: The union of every merge result, so callers can see which
        objects were created and updated across the whole run.
    """

    seen: int = 0
    invalid: int = 0
    failed: int = 0
    merged: int = 0
    result: MergeResult[Any] = field(default_factory=MergeResult)

    def __str__(self) -> str:
        return (
            f"{self.seen} seen, {self.merged} merged, "
            f"{self.invalid} invalid, {self.failed} failed"
        )


class JKentScrapeLoader[ScrapeType: BaseModel, ParamType = None](ABC):
    """Loads one jkent run database into CourtListener.

    See the module docstring for what a subclass provides. Typical use is
    `Loader(path).load()`; `scrapes()` is public so a caller can inspect what
    the query and `normalize` produce without writing anything.

    :cvar query: SQL run against the run database, returning one row per
        object to merge. It must select the payload column (`payload_column`),
        and may select anything else `normalize` needs. Rows are streamed, so
        a query over a large run does not have to fit in memory.
    :cvar payload_column: The column holding the scraper's JSON blob.
    :cvar scrape_model: The Pydantic model each normalized payload is
        validated into. This is the merger's input type.
    :cvar merger: The merger to run for each scrape. A merger that takes
        parameters gets them from `params`.
    :cvar document_model: The state document model this loader's merges write,
        whose rows are sent for text extraction as the load goes. Leave `None`
        for a loader that writes no documents.
    """

    query: ClassVar[str]
    payload_column: ClassVar[str] = "data_json"
    scrape_model: type[ScrapeType]
    merger: type[Merger[ScrapeType, ParamType, Model]]
    document_model: ClassVar[type[AbstractStateDocument] | None] = None

    def __init__(
        self,
        database: Path | str,
        *,
        limit: int | None = None,
        dry_run: bool = False,
        extract: bool = True,
        extraction_queue: str = "celery",
        extraction_throttle: int = 0,
        db_delay: float = 0.0,
        start_row: int = 0,
        checkpoint_key: str | None = None,
    ) -> None:
        """
        :param database: Path to the run's SQLite database.
        :param limit: Stop after this many rows, counted from `start_row`. For
            trying a loader out against a large run. A limited run keeps no
            checkpoint, since the position it stopped at means nothing to a
            later full load.
        :param dry_run: Roll back everything the load writes. The merge still
            runs in full, so the report is real; only the writes are undone.
            Writes no checkpoint either, having written nothing to resume from.
        :param extract: Dispatch text extraction for the documents the load
            writes.
        :param extraction_queue: The celery queue to extract on.
        :param extraction_throttle: Keep the extraction queue at roughly this
            many tasks, waiting for it to drain when it runs longer. Zero
            dispatches as fast as the merge goes, which for a whole run is
            enough to bury the queue; see the command's `--skip-extraction`
            for the other way to pace a backfill.
        :param db_delay: Seconds to wait after each row, to keep a long load
            from monopolising the database. Zero runs flat out.
        :param start_row: Skip this many rows before merging anything. The
            rows a query returns are ordered, and a run database never
            changes, so a row's position in one is stable enough to resume
            from.
        :param checkpoint_key: Redis key to record progress under as the load
            goes, for a later run to resume from. The key is deleted once the
            load reaches the end of the query, so that a finished load leaves
            nothing behind for the next one to trip over. `None` records
            nothing.
        """
        self.database = Path(database)
        self.limit = limit
        self.dry_run = dry_run
        self.extract = extract
        self.extraction_queue = extraction_queue
        self.db_delay = db_delay
        self.start_row = start_row
        self.checkpoint_key = checkpoint_key
        self.throttle = (
            CeleryThrottle(
                min_items=extraction_throttle, queue_name=extraction_queue
            )
            if extraction_throttle and extract and self.document_model
            else None
        )

    def rows(self) -> Iterator[sqlite3.Row]:
        """Stream the rows `query` selects, honouring `start_row` and `limit`.

        The connection is read-only: a run database is a record of what a
        scraper saw, and loading it must not change it."""
        if not self.database.exists():
            raise FileNotFoundError(f"No run database at {self.database}")
        uri = f"file:{self.database.resolve()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            with closing(connection.execute(self.query)) as cursor:
                for count, row in enumerate(cursor, start=1):
                    if count <= self.start_row:
                        continue
                    if (
                        self.limit is not None
                        and count - self.start_row > self.limit
                    ):
                        return
                    yield row

    def normalize(
        self, payload: dict[str, Any], row: sqlite3.Row
    ) -> dict[str, Any] | None:
        """Reshape one row's payload into something `scrape_model` accepts.

        :param payload: The decoded `payload_column` JSON.
        :param row: The whole row, for anything else the query selected.
        :return: The payload to validate, or `None` to pass over this row,
            which the report counts as invalid. Pass over a row there is
            nothing useful to do with; a payload that *should* merge but does
            not fit the model is better left to fail validation, which names
            the fields at fault.
        :raises UnusableScrape: For a row that should count as a failure
            rather than a routine skip. See `UnusableScrape`."""
        return payload

    def params(self, scrape: ScrapeType) -> ParamType:
        """The parameters to merge `scrape` with.

        Defaults to `None`, which is what a merger that takes no parameters
        wants. Override it for one that takes them."""
        return cast(ParamType, None)

    def _prepare(self, row: sqlite3.Row) -> ScrapeType | RowOutcome:
        """Turn one row into a scrape, or say why it did not become one."""
        try:
            payload = json.loads(row[self.payload_column])
        except (json.JSONDecodeError, TypeError) as error:
            logger.error(
                "Could not decode %s from %s: %s",
                self.payload_column,
                self.database.name,
                error,
            )
            return RowOutcome.INVALID
        try:
            normalized = self.normalize(payload, row)
        except UnusableScrape as error:
            logger.error("Refusing a row of %s: %s", self.database.name, error)
            return RowOutcome.FAILED
        if normalized is None:
            return RowOutcome.INVALID
        try:
            return self.scrape_model.model_validate(normalized)
        except ValidationError as error:
            logger.error(
                "Could not validate %s from %s: %s",
                self.scrape_model.__name__,
                self.database.name,
                error,
            )
            return RowOutcome.INVALID

    def scrapes(self) -> Iterator[ScrapeType]:
        """Yield the scrape for every row that produced one.

        Rows are streamed and bad ones are logged and passed over rather than
        raising, so one malformed docket in a run of thousands does not cost
        the rest. Useful on its own for inspecting what the query and
        `normalize` produce without writing anything."""
        for row in self.rows():
            prepared = self._prepare(row)
            if not isinstance(prepared, RowOutcome):
                yield prepared

    def merge_one(self, scrape: ScrapeType) -> MergeResult[Any]:
        """Merge a single scrape. Exists as a seam for subclasses that need to
        do something around the merge, such as handling a failure specially."""
        return self.merger(scrape, params=self.params(scrape)).merge()

    def load(self) -> LoadReport:
        """Merge everything the query returns and report what happened.

        Each docket is merged independently: one that fails is logged and the
        run continues, because a single malformed docket in a run of thousands
        should not cost the rest."""
        if not self.dry_run:
            return self._load()
        if not self.merger.atomic:
            logger.warning(
                "%s is not atomic: a row that errors at the database will "
                "cost every row after it in this dry run.",
                self.merger.__name__,
            )
        if self.extract and self.document_model is not None:
            logger.info("Dry run: dispatching no extraction.")
        with transaction.atomic():
            report = self._load()
            transaction.set_rollback(True)
        logger.info("Dry run: rolled back %s", report)
        return report

    @property
    def checkpointing(self) -> str | None:
        """The key this load's position is worth recording under, if any."""
        if self.dry_run or self.limit is not None:
            return None
        return self.checkpoint_key

    def _checkpoint(self, row: int) -> None:
        """Record that the load has finished every row up to and including
        `row`, counting from the start of the query rather than `start_row`.

        :param row: The last row the load got through."""
        if (key := self.checkpointing) is None:
            return
        try:
            log_last_document_indexed(row, key)
        except Exception:
            logger.exception("Could not checkpoint %s", key)

    def _clear_checkpoint(self) -> None:
        """Drop the checkpoint, the load having reached the end of the query.

        Leaving it in place would have the next load of the same run database
        start at the end of the last one, silently merging nothing."""
        if (key := self.checkpointing) is None:
            return
        try:
            get_redis_interface("CACHE").delete(key)
        except Exception:
            logger.exception("Could not clear checkpoint %s", key)

    def _load(self) -> LoadReport:
        report = LoadReport()
        if self.start_row:
            logger.info(
                "Loading %s from row %s", self.database.name, self.start_row
            )
        for row in self.rows():
            report.seen += 1
            if report.seen % CHECKPOINT_EVERY == 0:
                logger.info("Loading %s: %s", self.database.name, report)
                self._checkpoint(self.start_row + report.seen - 1)
            prepared = self._prepare(row)
            if prepared is RowOutcome.FAILED:
                report.failed += 1
                report.result |= MergeResult.failed(self.merger.model.__name__)
                continue
            if prepared is RowOutcome.INVALID:
                report.invalid += 1
                continue
            try:
                result = self.merge_one(prepared)
            except (DatabaseError, ValueError) as error:
                logger.exception(
                    "Merge raised for row %s of %s: %s",
                    report.seen,
                    self.database.name,
                    error,
                )
                report.failed += 1
                report.result |= MergeResult.failed(self.merger.model.__name__)
                continue
            report.result |= result
            try:
                self.dispatch_extraction(result)
            except Exception as error:
                logger.exception(
                    "Could not dispatch extraction for row %s of %s: %s",
                    report.seen,
                    self.database.name,
                    error,
                )
            if result.success:
                report.merged += 1
            else:
                report.failed += 1
                logger.error(
                    "Merge reported failures for row %s of %s: %s",
                    report.seen,
                    self.database.name,
                    result.failures,
                )
            if self.db_delay:
                time.sleep(self.db_delay)
        self._clear_checkpoint()
        return report

    def dispatch_extraction(self, result: MergeResult[Any]) -> None:
        """Send the documents one merge touched for text extraction.

        :param result: One merge's result, read for the document PKs it
            created or updated."""
        if (model := self.document_model) is None or not self.extract:
            return
        if self.dry_run:
            return
        pks = result.creates.get(model.__name__, set()) | result.updates.get(
            model.__name__, set()
        )
        if not pks:
            return
        logger.info(
            "Dispatching extraction for %s %s", len(pks), model.__name__
        )
        for document in model._default_manager.filter(pk__in=pks):
            if self.throttle is not None:
                self.throttle.maybe_wait()
            document.extract(self.extraction_queue)
