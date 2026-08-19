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
from abc import ABC
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, ClassVar

from django.db import DatabaseError, transaction
from django.db.models import Model
from pydantic import BaseModel, ValidationError

from cl.corpus_importer.state.merger import Merger
from cl.corpus_importer.state.utils import MergeResult

logger = logging.getLogger(__name__)


class UnusableScrape(Exception):
    """Raised by `normalize` for a row it refuses to merge.

    Use this where merging the row would write something wrong -- a scrape
    that stopped short of data the merger prunes against, say -- as opposed to
    a row there is simply nothing to do with. The distinction is what the load
    report is counted on: returning `None` from `normalize` counts the row as
    skipped, which an operator reads as routine, while raising this counts it
    as failed, which says the run needs looking at.

    The message is logged, so it should name the row and say what is wrong
    with it.
    """


class RowOutcome(Enum):
    """What became of one row on the way from the run database to a scrape."""

    OK = auto()
    SKIPPED = auto()
    """`normalize` returned `None`."""
    INVALID = auto()
    """The payload did not validate against `scrape_model`."""
    FAILED = auto()
    """`normalize` raised `UnusableScrape`."""


@dataclass
class LoadReport:
    """What a load run did.

    The four rejection counts are separate because they call for different
    responses: `skipped` is the loader's own judgment and expected, `invalid`
    means the scrape does not fit the model and usually points at scraper
    drift, `rejected` is the merger declining data it cannot place, and
    `failed` is data that should have merged and did not.

    :ivar seen: Rows the query returned.
    :ivar skipped: Rows `normalize` discarded.
    :ivar invalid: Payloads that failed validation against `scrape_model`.
    :ivar rejected: Scrapes the merger's `validate` turned away.
    :ivar failed: Rows `normalize` refused with `UnusableScrape`, plus merges
        that ran and reported failures.
    :ivar merged: Merges that came out clean.
    :ivar result: The union of every merge result, so callers can see which
        objects were created and updated across the whole run.
    """

    seen: int = 0
    skipped: int = 0
    invalid: int = 0
    rejected: int = 0
    failed: int = 0
    merged: int = 0
    result: MergeResult[Any] = field(default_factory=MergeResult)

    def __str__(self) -> str:
        return (
            f"{self.seen} seen, {self.merged} merged, {self.skipped} skipped, "
            f"{self.invalid} invalid, {self.rejected} rejected, "
            f"{self.failed} failed"
        )


class JKentScrapeLoader[ScrapeType: BaseModel](ABC):
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
    :cvar merger: The merger to run for each scrape.
    """

    query: ClassVar[str]
    payload_column: ClassVar[str] = "data_json"
    scrape_model: type[ScrapeType]
    merger: type[Merger[ScrapeType, None, Model]]

    def __init__(
        self,
        database: Path | str,
        *,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> None:
        """
        :param database: Path to the run's SQLite database.
        :param limit: Stop after this many rows. For trying a loader out
            against a large run.
        :param dry_run: Roll back everything the load writes. The merge still
            runs in full, so the report is real; only the writes are undone.
        """
        self.database = Path(database)
        self.limit = limit
        self.dry_run = dry_run

    def rows(self) -> Iterator[sqlite3.Row]:
        """Stream the rows `query` selects, honouring `limit`.

        The connection is read-only: a run database is a record of what a
        scraper saw, and loading it must not change it."""
        if not self.database.exists():
            raise FileNotFoundError(f"No run database at {self.database}")
        uri = f"file:{self.database.resolve()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            with closing(connection.execute(self.query)) as cursor:
                for count, row in enumerate(cursor, start=1):
                    yield row
                    if self.limit is not None and count >= self.limit:
                        return

    def normalize(
        self, payload: dict[str, Any], row: sqlite3.Row
    ) -> dict[str, Any] | None:
        """Reshape one row's payload into something `scrape_model` accepts.

        The default passes the payload through, which is right when the
        scraper already emits the standard docket format. Override to do the
        reshaping SQL is a poor fit for -- nesting children under their
        parent, folding in columns the query joined on, deriving fields the
        scraper does not state.

        :param payload: The decoded `payload_column` JSON.
        :param row: The whole row, for anything else the query selected.
        :return: The payload to validate, or `None` to skip this row. Skipping
            is for a row there is nothing useful to do with; a payload that
            *should* merge but does not fit the model is better left to fail
            validation, which says so loudly.
        :raises UnusableScrape: For a row that should count as a failure
            rather than a routine skip. See `UnusableScrape`."""
        return payload

    def _prepare(
        self, row: sqlite3.Row
    ) -> tuple[ScrapeType | None, RowOutcome]:
        """Turn one row into a scrape, saying why if it did not become one."""
        payload = json.loads(row[self.payload_column])
        try:
            normalized = self.normalize(payload, row)
        except UnusableScrape as error:
            logger.error("Refusing a row of %s: %s", self.database.name, error)
            return None, RowOutcome.FAILED
        if normalized is None:
            return None, RowOutcome.SKIPPED
        try:
            return self.scrape_model.model_validate(normalized), RowOutcome.OK
        except ValidationError as error:
            logger.error(
                "Could not validate %s from %s: %s",
                self.scrape_model.__name__,
                self.database.name,
                error,
            )
            return None, RowOutcome.INVALID

    def scrapes(self) -> Iterator[ScrapeType]:
        """Yield the scrape for every row that produced one.

        Rows are streamed and bad ones are logged and passed over rather than
        raising, so one malformed docket in a run of thousands does not cost
        the rest. Useful on its own for inspecting what the query and
        `normalize` produce without writing anything."""
        for row in self.rows():
            scrape, outcome = self._prepare(row)
            if outcome is RowOutcome.OK and scrape is not None:
                yield scrape

    def merge_one(self, scrape: ScrapeType) -> MergeResult[Any] | None:
        """Merge a single scrape, or return `None` if the merger turned it
        away. Exists as a seam for subclasses that need to pass merger
        parameters or handle a merger failure specially."""
        if not self.merger.validate(scrape):
            return None
        return self.merger(scrape, params=None).merge()

    def load(self) -> LoadReport:
        """Merge everything the query returns and report what happened.

        Each docket is merged independently: one that fails is logged and the
        run continues, because a single malformed docket in a run of thousands
        should not cost the rest."""
        if not self.dry_run:
            return self._load()
        # The merge still runs; `set_rollback` discards it on the way out.
        with transaction.atomic():
            report = self._load()
            transaction.set_rollback(True)
        logger.info("Dry run: rolled back %s", report)
        return report

    def _load(self) -> LoadReport:
        report = LoadReport()
        for row in self.rows():
            report.seen += 1
            scrape, outcome = self._prepare(row)
            if outcome is RowOutcome.SKIPPED:
                report.skipped += 1
                continue
            if outcome is RowOutcome.FAILED:
                report.failed += 1
                # Recorded against the merger's own model so the run's
                # failures are all in one place, with no PK because nothing
                # was ever looked up.
                report.result |= MergeResult.failed(self.merger.model.__name__)
                continue
            if outcome is RowOutcome.INVALID or scrape is None:
                report.invalid += 1
                continue
            try:
                result = self.merge_one(scrape)
            except (DatabaseError, ValueError) as error:
                logger.exception(
                    "Merge raised for row %s of %s: %s",
                    report.seen,
                    self.database.name,
                    error,
                )
                report.failed += 1
                continue
            if result is None:
                report.rejected += 1
                continue
            report.result |= result
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
            if report.seen % 250 == 0:
                logger.info("Loading %s: %s", self.database.name, report)
        return report
