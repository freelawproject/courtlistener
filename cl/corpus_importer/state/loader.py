"""Load the output of a jkent scrape run into CourtListener.

A jkent run leaves behind a SQLite database whose `results` table holds one row
per object the scraper yielded, each as a JSON blob in `data_json` tagged with
the scraper model that produced it.

A subclass supplies five things:

* `name`, the key it is registered under in `cl.corpus_importer.state.registry`,
  which is how a merge task finds its way back to the loader that sent it;
* `query`, the SQL that pulls one row per docket out of `results`, doing
  whatever joining and de-duplication the run needs;
* `normalize`, an optional hook that reshapes each row's payload in Python,
  for the part of the work SQL is a poor fit for;
* `scrape_model`, the Pydantic model each payload is validated into;
* `merger`, which writes a validated scrape to the database.

The run database is opened read-only.
"""

import json
import logging
import sqlite3
import time
from abc import ABC
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, StrEnum, auto
from pathlib import Path
from typing import Any, ClassVar, Final, cast

from django.db.models import Model
from pydantic import BaseModel, ValidationError

from cl.corpus_importer.state.ledger import LoadLedger
from cl.corpus_importer.state.merger import Merger
from cl.corpus_importer.state.utils import MergeResult
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.indexing_utils import log_last_document_indexed
from cl.lib.redis_utils import get_redis_interface
from cl.search.state.shared import AbstractStateDocument

logger = logging.getLogger(__name__)

CHECKPOINT_EVERY: Final = 250
MERGE_POLL: Final = 10.0
EXTRACTION_POLL: Final = 60.0
DEFAULT_IN_FLIGHT_TIME: Final = 300.0  # Seconds
DEFAULT_VERIFY_TIMEOUT: Final = 1800.0  # Seconds
OUTSTANDING_SHOWN: Final = 20


class LoadPhase(StrEnum):
    """A phase of a load that can go wrong, and the Sentry issue it files
    under."""

    MERGE = "state-scrape-merge-failed"
    EXTRACTION = "state-scrape-extraction-incomplete"
    RECONCILIATION = "state-scrape-rows-dropped"


def fingerprint(loader: str, phase: LoadPhase) -> dict[str, list[str]]:
    """Sentry fingerprinting helper.

    :param loader: The loader's registered name, such as `nycoa`.
    :param phase: Which phase went wrong.
    :return: The `extra` to log the error with. See
        `cl.settings.third_party.sentry.fingerprint_sentry_error`.
    """
    return {"fingerprint": [loader, phase.value]}


class UnusableScrape(Exception):
    """Raised by `normalize` for a row it refuses to dispatch.

    Use this where merging the row would write something wrong. This is
    particularly useful in cases where a webpage gives us contradictory
    data like "There are 100 docket entries" and "0 docket entries found"
    """


class WaitOutcome(Enum):
    """How a load stopped waiting on one of its queues."""

    DRAINED = auto()  # Happy
    STALLED = auto()  # Steady but non-zero
    TIMED_OUT = auto()  # Timed out waiting for stability

    @property
    def conclusive(self) -> bool:
        """Whether this outcome says anything about the work still left."""
        return self is not WaitOutcome.TIMED_OUT


class RowOutcome(Enum):
    """Why a row did not become a scrape."""

    INVALID = auto()
    REFUSED = auto()


@dataclass
class ExtractionReport:
    """Running stats for extractions.

    :ivar dispatched: Documents the run's merges sent to the extraction queue.
        A document with no file to read, or one already extracted, is never
        sent and so is never expected back.
    :ivar outstanding: Documents written since the run began that extraction
        has not come back on.
    :ivar failed: Documents extraction ran on and could not read. A matter for
        the extraction pipeline rather than for the load.
    :ivar sample: A few outstanding PKs, to go and look at.
    :ivar since: The moment the window starts at, so a reader knows what the
        two window-scoped counts covered.
    :ivar wait: How the load stopped waiting on extraction, or `None` where it
        did not wait at all. `outstanding` only means "never going to happen"
        when this is `STALLED`.
    """

    dispatched: int = 0
    outstanding: int = 0
    failed: int = 0
    sample: list[int] = field(default_factory=list)
    since: datetime | None = None
    wait: WaitOutcome | None = None

    @property
    def complete(self) -> bool:
        """Whether extraction has come back on everything in the window."""
        return not self.outstanding

    @property
    def abandoned(self) -> bool:
        """Whether extraction demonstrably stopped, rather than merely not
        having finished by the time the load gave up watching."""
        return bool(self.outstanding) and self.wait is WaitOutcome.STALLED

    def __str__(self) -> str:
        window = f" since {self.since:%Y-%m-%d %H:%M}" if self.since else ""
        return (
            f"{self.dispatched} documents dispatched, {self.outstanding} "
            f"still unextracted, {self.failed} failed{window}"
        )


@dataclass
class LoadReport:
    """Summary stats for a load run.

    :ivar seen: Rows the query returned.
    :ivar invalid: Payloads that would not decode, failed validation against
        `scrape_model`, or that `normalize` passed over by returning `None`.
    :ivar refused: Rows `normalize` turned away with `UnusableScrape`.
    :ivar dispatched: Rows sent to the merge queue.
    :ivar merged: Dispatched rows whose merge came back clean.
    :ivar rejected: Dispatched rows whose merge ran and reported failures,
        which includes a merger turning a scrape away in its own `validate`.
        Reported apart from `errored` because the scrape is what is wrong.
    :ivar errored: Dispatched rows whose merge never reached a verdict: its
        retries ran out, the payload no longer validates against the deployed
        code, or something nothing expected was raised. Re-running the load
        over them is what settles these.
    :ivar missing_count: How many dispatched rows never reported anything at
        all. These are the ones celery lost; re-running the load over the same
        rows is how they get merged.
    :ivar missing: A sample of at most `OUTSTANDING_SHOWN` of them, keyed by
        row number and named by the label they were dispatched under. A
        sample, not the set, because there is no bound on how large the set
        can get: a broker that went down leaves the whole run in it. The rest
        stay in the ledger's `pending` key in Redis until its TTL expires.
    :ivar merge_wait: How the load stopped waiting on the merge queue, or
        `None` where it did not wait at all. `missing_count` only means "never
        going to happen" when this is `STALLED`.
    :ivar rows_read: Whether the run database was opened. False for a
        `verify_only` pass, whose zeroes for `seen`, `invalid` and `refused`
        mean "did not look" rather than "found none".
    :ivar creates: Objects created, counted per model name.
    :ivar updates: Objects updated, counted per model name.
    :ivar extraction: What became of the documents the run dispatched for text
        extraction, or `None` where the load did not check.
    """

    seen: int = 0
    invalid: int = 0
    refused: int = 0
    dispatched: int = 0
    merged: int = 0
    rejected: int = 0
    errored: int = 0
    missing_count: int = 0
    missing: dict[int, str] = field(default_factory=dict)
    merge_wait: WaitOutcome | None = None
    rows_read: bool = True
    creates: dict[str, int] = field(default_factory=dict)
    updates: dict[str, int] = field(default_factory=dict)
    extraction: ExtractionReport | None = None

    @property
    def failed(self) -> int:
        """Dispatched rows that did not merge, however they came not to."""
        return self.rejected + self.errored

    @property
    def accounted_for(self) -> bool:
        """Whether every row the load dispatched reported an outcome."""
        return not self.missing_count

    @property
    def dropped(self) -> bool:
        """Whether rows demonstrably went astray, as against a load that
        stopped waiting while its queue was still coming down."""
        return bool(self.missing_count) and self.merge_wait is (
            WaitOutcome.STALLED
        )

    def __str__(self) -> str:
        # A load that skipped dispatching has no stats from the scrape DB.
        parts = [f"{self.seen} seen"] if self.rows_read else []
        parts += [
            f"{self.dispatched} dispatched",
            f"{self.merged} merged",
            f"{self.rejected} rejected",
            f"{self.errored} errored",
        ]
        if self.rows_read:
            parts += [f"{self.invalid} invalid", f"{self.refused} refused"]
        parts.append(f"{self.missing_count} missing")
        return ", ".join(parts)


class JKentScrapeLoader[ScrapeType: BaseModel, ParamType = None](ABC):
    """Loads one jkent run database into CourtListener.

    :cvar name: The key this loader is registered under in
        `cl.corpus_importer.state.registry`. It travels on the celery message
        in place of the loader itself.
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
        whose rows are sent for text extraction as the merges land. Leave
        `None` for a loader that writes no documents.
    """

    name: ClassVar[str]
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
        extract: bool = True,
        ingest_queue: str = "celery",
        ingest_throttle: int = 0,
        extraction_queue: str = "celery",
        extraction_throttle: int = 0,
        db_delay: float = 0.0,
        start_row: int = 0,
        run_key: str | None = None,
        verify: bool = True,
        in_flight_time: float = DEFAULT_IN_FLIGHT_TIME,
        verify_timeout: float = DEFAULT_VERIFY_TIMEOUT,
    ) -> None:
        """
        :param database: Path to the run's SQLite database.
        :param limit: Stop after this many rows, counted from `start_row`. For
            trying a loader out against a large run. A limited run keeps no
            checkpoint, since the position it stopped at means nothing to a
            later full load.
        :param extract: Have each merge dispatch text extraction for the
            documents it writes.
        :param ingest_queue: The celery queue to merge dockets on.
        :param ingest_throttle: Keep the merge queue at roughly this many
            tasks, waiting for it to drain when it runs longer. Zero
            dispatches as fast as the run database can be read, which buries
            the queue and hands the workers a whole run's merges at once.
        :param extraction_queue: The celery queue to extract documents on.
        :param extraction_throttle: Keep the extraction queue at roughly this
            many tasks the same way. Merges dispatch their own extraction, so
            throttling the merge queue paces this one indirectly; set this as
            well to hold extraction to a rate of its own, or see the command's
            `--skip-extraction` for the other way to pace a backfill.
        :param db_delay: Seconds to wait after each row, to keep a long load
            from monopolising the queue. Zero runs flat out.
        :param start_row: Skip this many rows before dispatching anything. The
            rows a query returns are ordered, and a run database never
            changes, so a row's position in one is stable enough to resume
            from.
        :param run_key: Redis key this run's checkpoint and ledger hang off.
            The checkpoint records progress as the load goes, for a later run
            to resume from, and is deleted once the load reaches the end of
            the query so that a finished load leaves nothing behind for the
            next one to trip over. The ledger is what `verify` reads. Defaults
            to `default_run_key()` which should work for almost all cases.
        :param verify: Wait for the dispatched merges to report back and check
            what came of them. See `verify`.
        :param in_flight_time: Seconds a phase's outstanding count has to hold
            steady before the load concludes the rest is never coming. Has to
            exceed the longest legitimate gap between two decrements -- a
            merge's whole retry envelope, or the slowest extraction job -- or
            slow work reads as lost work.
        :param verify_timeout: Seconds to wait on a phase whose count is still
            coming down before giving up and reporting it as outstanding. Each
            phase gets its own.
        """
        self.database = Path(database)
        self.limit = limit
        self.extract = extract
        self.ingest_queue = ingest_queue
        self.extraction_queue = extraction_queue
        self.db_delay = db_delay
        self.start_row = start_row
        self.run_key = run_key or self.default_run_key()
        self.ledger = LoadLedger(self.run_key)
        self.should_verify = verify
        self.in_flight_time = in_flight_time
        self.verify_timeout = verify_timeout
        self.throttles = [
            CeleryThrottle(min_items=minimum, queue_name=queue)
            for minimum, queue in (
                (ingest_throttle, ingest_queue),
                (extraction_throttle if extract else 0, extraction_queue),
            )
            if minimum
        ]

    def default_run_key(self) -> str:
        """The Redis key a load keys its ledger and checkpoint off, unless overridden.

        :return: The key.
        """
        return f"state_scrape_load:{self.name}:{self.database.name}"

    def rows(self) -> Iterator[tuple[int, sqlite3.Row]]:
        """Stream the rows `query` selects, honouring `start_row` and `limit`.

        :yield: The row's position in the query, counting from one and
            counting the rows `start_row` skipped, and the row itself. The
            position is what a checkpoint and the ledger name a row by, so it
            has to be the absolute one.
        """
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
                    yield count, row

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
        :raises UnusableScrape: For a row that should count as refused rather
            than a routine skip. See `UnusableScrape`."""
        return payload

    @classmethod
    def params(cls, scrape: ScrapeType) -> ParamType:
        """Optional merger parameters."""
        return cast(ParamType, None)

    @classmethod
    def label(cls, scrape: ScrapeType) -> str:
        """Something to recognise `scrape` by in a log line or the ledger.

        Defaults to the scrape's docket number."""
        return str(getattr(scrape, "docket_number", "") or "")

    @staticmethod
    def _identify(payload: object, number: int) -> str:
        """Narrowest identity for a row, docket_number | row number."""

        if isinstance(payload, dict) and (
            docket := payload.get("docket_number")
        ):
            return f"{docket} (row {number})"
        return f"row {number}"

    def _prepare(
        self, number: int, row: sqlite3.Row
    ) -> ScrapeType | RowOutcome:
        """Error handling wrapper over normalize.

        :param number: The row's position in the query.
        :param row: The run database row.
        :return: The scrape, or the outcome that stopped it.
        """
        try:
            payload = json.loads(row[self.payload_column])
        except (json.JSONDecodeError, TypeError) as error:
            logger.error(
                "%s of %s: could not decode %s: %s",
                self._identify(None, number),
                self.database.name,
                self.payload_column,
                error,
            )
            return RowOutcome.INVALID
        try:
            normalized = self.normalize(payload, row)
        except UnusableScrape as error:
            logger.error(
                "%s of %s: refusing to merge it: %s",
                self._identify(payload, number),
                self.database.name,
                error,
            )
            return RowOutcome.REFUSED
        if normalized is None:
            return RowOutcome.INVALID
        try:
            return self.scrape_model.model_validate(normalized)
        except ValidationError as error:
            logger.exception(
                "%s of %s: does not fit %s: %s",
                self._identify(normalized, number),
                self.database.name,
                self.scrape_model.__name__,
                error,
            )
            return RowOutcome.INVALID

    def scrapes(self) -> Iterator[ScrapeType]:
        """Yield the scrape for every row that produced one."""
        for number, row in self.rows():
            prepared = self._prepare(number, row)
            if not isinstance(prepared, RowOutcome):
                yield prepared

    @classmethod
    def merge_one(cls, scrape: ScrapeType) -> MergeResult[Any]:
        """Merge a single scrape. Runs in celery worker."""
        return cls.merger(scrape, params=cls.params(scrape)).merge()

    @classmethod
    def merge_payload(cls, payload: str) -> tuple[str, MergeResult[Any]]:
        """Merge one dispatched row, given the payload celery carried.

        :param payload: The scrape, as the load dumped it at dispatch.
        :return: The scrape's label and the result of merging it.
        :raises pydantic.ValidationError: If the payload no longer fits
            `scrape_model` -- which, since the load validated the scrape it
            dumped before dispatching it, means the message and the code that
            will merge it were deployed out of step, and no amount of retrying
            will reconcile them.
        """
        scrape = cls.scrape_model.model_validate_json(payload)
        return cls.label(scrape), cls.merge_one(scrape)

    @classmethod
    def dispatch_extraction(
        cls, result: MergeResult[Any], queue: str
    ) -> set[int]:
        """Sends doc pks to celery queue for extraction.

        :param result: One merge's result, read for the document PKs it
            created or updated.
        :param queue: The celery queue to extract on.
        :return: The PKs actually sent. A document with no file to read, or
            one already extracted, is skipped and left out, so that what comes
            back is exactly the set worth expecting extraction of.
        """
        if (model := cls.document_model) is None:
            return set()
        pks = result.creates.get(model.__name__, set()) | result.updates.get(
            model.__name__, set()
        )
        if not pks:
            return set()
        dispatched = {
            document.pk
            for document in model._default_manager.filter(pk__in=pks)
            if document.extract(queue)
        }
        logger.info(
            "Dispatched extraction for %s of %s %s",
            len(dispatched),
            len(pks),
            model.__name__,
        )
        return dispatched

    def load(self) -> LoadReport:
        """Dispatch every row to celery for merging + extraction.

        :return: What the run dispatched, and -- unless `verify` was turned
            off -- what came of it.
        """
        report = self._dispatch_all()
        self.verify(report)
        return report

    def verify_only(self) -> LoadReport:
        """Check up on a load that already ran, without reading its run
        database.

        The other half of `load`, for settling a run that stopped watching its
        queues while they were still coming down. This is what the command's
        `--skip-load` calls.

        :return: What the ledger says became of the run, with the counts only
            the run database could have supplied left at zero. See
            `LoadReport.rows_read`.
        """
        report = LoadReport(rows_read=False)
        self.verify(report)
        return report

    @property
    def checkpointing(self) -> str | None:
        """The key this load's position is worth recording under, if any."""
        if self.limit is not None:
            return None
        return self.run_key

    def _checkpoint(self, row: int) -> None:
        """Record that the load has dispatched every row up to and including
        `row`, counting from the start of the query rather than `start_row`.

        :param row: The last row the load dispatched."""
        if (key := self.checkpointing) is None:
            return
        try:
            log_last_document_indexed(row, key)
        except Exception:
            logger.exception("Could not checkpoint %s", key)

    def _clear_checkpoint(self) -> None:
        """Drop the checkpoint, load completed."""
        if (key := self.checkpointing) is None:
            return
        try:
            get_redis_interface("CACHE").delete(key)
        except Exception:
            logger.exception("Could not clear checkpoint %s", key)

    def _dispatch_all(self) -> LoadReport:
        """Read the run database and hand every usable row to the queue."""
        report = LoadReport()
        if self.start_row:
            logger.info(
                "Loading %s from row %s", self.database.name, self.start_row
            )
        else:
            # Starting from 0, fresh ledger
            self.ledger.clear()
        self.ledger.start()
        for number, row in self.rows():
            report.seen += 1
            if report.seen % CHECKPOINT_EVERY == 0:
                logger.info(
                    "Loading %s: %s seen, %s dispatched",
                    self.database.name,
                    report.seen,
                    report.dispatched,
                )
                self._checkpoint(number - 1)
            prepared = self._prepare(number, row)
            if prepared is RowOutcome.REFUSED:
                report.refused += 1
                continue
            if prepared is RowOutcome.INVALID:
                report.invalid += 1
                continue
            self._dispatch(number, prepared)
            report.dispatched += 1
            if self.db_delay:
                time.sleep(self.db_delay)
        self._clear_checkpoint()
        logger.info(
            "Dispatched %s rows of %s", report.dispatched, self.database.name
        )
        return report

    def _dispatch(self, number: int, scrape: ScrapeType) -> None:
        """Send one row's merge to the queue, writing it down as it goes.

        :param number: The row's position in the query.
        :param scrape: The validated scrape. Its own dump is what the worker
            gets, so what the worker validates is what this load read.
        """
        # Imported here because the task module imports the registry, which
        # imports every loader, which imports this module.
        from cl.corpus_importer.tasks import merge_state_scrape_row

        for throttle in self.throttles:
            throttle.maybe_wait()
        self.ledger.dispatched(number, self.label(scrape))
        merge_state_scrape_row.si(
            loader=self.name,
            row=number,
            payload=scrape.model_dump_json(),
            run_key=self.run_key,
            extract=self.extract,
            extraction_queue=self.extraction_queue,
        ).set(queue=self.ingest_queue).apply_async()

    def verify(self, report: LoadReport) -> None:
        """Wait for the dispatched merges, then say what never came back.

        A load's own process cannot tell a merge that is queued from one that
        will never run: celery drops a task whose retries run out or whose
        worker is killed, and says nothing to anyone. This reads the ledger
        instead, which both sides write to, and fills in the half of the
        report the loading process could not know -- including `missing`, the
        rows that were dispatched and never heard from again.

        Where the load wrote documents, it goes on to check those against the
        database, since a merge reporting success says only that extraction
        was dispatched, not that it ran.

        Each wait ends one of three ways, and which one it was is what the
        report is read on. A count that reaches zero is a clean run. A count
        that holds steady for `in_flight_time` says the rest is not coming, and
        that is the finding. A count still falling when `verify_timeout` runs
        out says only that the load stopped watching -- see `WaitOutcome`.

        This establishes the facts and then hands them to `alert`, which is
        what decides any of it is worth waking someone over.

        :param report: The report to fill in, modified in place.
        """
        if not self.should_verify:
            return
        ledger = self.ledger
        report.missing_count, report.merge_wait = self._await_drain(
            ledger.outstanding_count, poll=MERGE_POLL, work="merges"
        )
        if report.missing_count:
            report.missing = ledger.outstanding(OUTSTANDING_SHOWN)
        totals = ledger.totals()
        report.dispatched = totals.dispatched or report.dispatched
        report.merged = totals.merged
        report.rejected = totals.rejected
        report.errored = totals.errored
        report.creates = totals.creates
        report.updates = totals.updates
        if self.extract and (model := self.document_model) is not None:
            report.extraction = self._await_extraction(ledger, model)
        self.alert(report)
        # The ledger is left where it is. It expires on its own, and until it
        # does it is the only account of what a run did -- which a run that
        # was resumed partway adds to rather than replaces.

    def alert(self, report: LoadReport) -> None:
        """Raise, to the log and so to Sentry, whatever a load got wrong.

        The one place that decides what is worth an alert, kept apart from the
        checks that established the facts so that neither is buried in the
        other. It stays on the loader rather than moving to the command that
        usually drives one, because anything calling `load()` wants these
        raised and a caller that is not a management command has no other way
        to hear about them.

        Each category is fingerprinted so the three arrive in Sentry as three
        issues rather than one heap: a docket the database would not take, a
        docket celery lost, and a document nothing ever read are three
        different problems with three different people to chase. See
        `fingerprint` for why they group by loader and not by run.

        Note the asymmetry with the per-docket failures the workers report:
        those reach Sentry whether or not this ever runs. Everything here
        depends on a load having stayed to verify itself.

        :param report: The filled-in report.
        """
        if report.failed:
            # Each worker already logged the docket it gave up on. This is the
            # run-level count, filed under the same issue.
            logger.error(
                "%s of %s dockets of the %s run would not merge: %s rejected "
                "by a merge that ran, %s errored before one could.",
                report.failed,
                report.dispatched,
                self.name,
                report.rejected,
                report.errored,
                extra=fingerprint(self.name, LoadPhase.MERGE),
            )
        if report.dropped:
            logger.error(
                "%s dockets of the %s run were dispatched and never reported "
                "back, which means celery lost them: a worker died mid-merge "
                "or the message went astray. Nothing else will say so. "
                "Re-run the load over them; merging is idempotent. "
                "Run database %s. Here are %s of them, and every one is in "
                "Redis at %s until that key expires: %s",
                report.missing_count,
                self.name,
                self.database.name,
                len(report.missing),
                self.ledger.pending_key(),
                report.missing,
                extra=fingerprint(self.name, LoadPhase.RECONCILIATION),
            )
        if (extraction := report.extraction) and extraction.abandoned:
            logger.error(
                "%s documents written by the %s run have no extracted text "
                "and no failure recorded against them, so extraction never "
                "ran on them. A call to the extraction service that fails "
                "leaves no other trace. `state_document_download "
                "--skip-download` will pick them up. Run database %s, first "
                "%s of them: %s",
                extraction.outstanding,
                self.name,
                self.database.name,
                len(extraction.sample),
                extraction.sample,
                extra=fingerprint(self.name, LoadPhase.EXTRACTION),
            )

    def _await_drain(
        self,
        count: Callable[[], int],
        *,
        poll: float,
        work: str,
    ) -> tuple[int, WaitOutcome]:
        """Watch `count` come down, and say why the watching stopped.

        The signal is our own outstanding count, not anything celery is asked
        about. That matters for three reasons: celery cannot see a task a dead
        worker took with it, an `inspect` broadcast costs every worker in the
        fleet a reply, and a task name says nothing about which run dispatched
        it -- a concurrent load of the same court would look like work in
        flight forever. A count that keeps falling, however slowly, says
        somebody is still working on our rows; a count that stops says nobody
        is.

        Each call gets its own `verify_timeout`, so no phase is starved by
        another running long, and none of the budget is spent dispatching --
        `load` sends everything before it verifies anything.

        :param count: Reads how much is still outstanding. Called once per
            pass, so it wants to be cheap.
        :param poll: Seconds between passes.
        :param work: What is being waited on, for the log line.
        :return: What is still outstanding, and how the wait ended.
        """
        deadline = time.monotonic() + self.verify_timeout
        outstanding = count()
        steady_since = time.monotonic()
        while outstanding:
            now = time.monotonic()
            if now - steady_since >= self.in_flight_time:
                return outstanding, WaitOutcome.STALLED
            if now >= deadline:
                return outstanding, WaitOutcome.TIMED_OUT
            logger.info(
                "Waiting on %s %s of %s",
                outstanding,
                work,
                self.database.name,
            )
            time.sleep(poll)
            if (current := count()) != outstanding:
                outstanding, steady_since = current, time.monotonic()
        return 0, WaitOutcome.DRAINED

    def _await_extraction(
        self, ledger: LoadLedger, model: type[AbstractStateDocument]
    ) -> ExtractionReport:
        """Wait for the documents the run dispatched to come back extracted.

        Waits and reports; whether what it finds is worth an alert is `alert`'s
        to decide.

        :param ledger: The run's ledger, read for the count dispatched and the
            moment the run began.
        :param model: The document model the run's merges wrote.
        :return: What became of them.
        """
        totals = ledger.totals()
        since = ledger.started()
        if not totals.documents or since is None:
            return ExtractionReport(dispatched=totals.documents, since=since)
        # Polling asks only for the count; the full picture, which costs two
        # more queries, is put together once at the end.
        _, wait = self._await_drain(
            lambda: model.unextracted(since).count(),
            poll=EXTRACTION_POLL,
            work="extractions",
        )
        # Always ask for the full picture, even where nothing is outstanding: a
        # document extraction ran on and could not read leaves nothing
        # outstanding but is still worth reporting, and it is three queries
        # once at the end of a run.
        return self._extraction_status(model, totals.documents, since, wait)

    @staticmethod
    def _extraction_status(
        model: type[AbstractStateDocument],
        dispatched: int,
        since: datetime,
        wait: WaitOutcome,
    ) -> ExtractionReport:
        """Ask the database what became of this run's documents.

        Two counts and a sample, so three queries. Called once, after the wait
        has ended -- polling uses `unextracted` alone.

        :param model: The document model the run's merges wrote.
        :param dispatched: How many documents the run sent to be extracted.
        :param since: The moment the run began.
        :param wait: How the wait on extraction ended.
        :return: What the database says.
        """
        unextracted = model.unextracted(since)
        return ExtractionReport(
            dispatched=dispatched,
            outstanding=unextracted.count(),
            failed=model.written_since(since)
            .filter(ocr_status=model.OCR_FAILED)
            .count(),
            sample=list(
                unextracted.values_list("pk", flat=True)[:OUTSTANDING_SHOWN]
            ),
            since=since,
            wait=wait,
        )
