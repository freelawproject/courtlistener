"""Integrity checks for scrape DBs.

There are a bunch of questions we might want to ask about a DB before
we start the process of loading it into postgres. Preflight checks
are a mechanism to run those queries, report on their results,
and potentially stop the load if we think those results say we should.

A check is a question put to the run database once, before anything is
dispatched, and an answer the load acts on:

- `PASSED` check passed, reported for sanity/record.
- `PARTIAL` says the load can go ahead but will not come out whole: rows the
  loader's query filters out, or files a merge will decline to publish.
- `FAILED` stops the load, because reading on would write something wrong.

Checks state what they are checking, so a report can name what ran as well as
what it found. `STANDARD_CHECKS` are the ones every jkent run database
answers; a loader adds its own through `JKentScrapeLoader.extra_checks`.
"""

import logging
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, ClassVar, Final

logger = logging.getLogger(__name__)

ERRORS_SHOWN: Final = 20


class CheckOutcome(Enum):
    PASSED = auto()
    PARTIAL = auto()
    FAILED = auto()

    @property
    def stops_the_load(self) -> bool:
        """Whether a load that got this answer must not go on."""
        return self is CheckOutcome.FAILED

    @property
    def is_failure(self) -> bool:
        """Whether this answer is worth an operator's attention."""
        return self is not CheckOutcome.PASSED


@dataclass(frozen=True)
class CheckError:
    """One thing a check found wrong.

    :ivar summary: What was found, as a line an operator can act on. This is
        what reaches the log and so Sentry.
    :ivar detail: The same finding in fields, which ride along to Sentry as
        `extra` so an issue can be read without parsing the summary back
        apart. Keep it small: Sentry truncates, and a check that wants to hand
        over a whole table wants a narrower question instead.
    """

    summary: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.summary


@dataclass(frozen=True)
class CheckResult:
    """One check's answer, and what it found getting there.

    :ivar description: What the check was checking, for the report.
    :ivar outcome: What it made of the answer.
    :ivar errors: What it found, empty for a check that passed. Materialised
        rather than lazy: the same findings are logged, sent to Sentry and
        printed in the report, and the cursor they were read from is closed
        by the time any of that happens.
    """

    description: str
    outcome: CheckOutcome
    errors: tuple[CheckError, ...] = ()

    def __str__(self) -> str:
        if not self.errors:
            return f"{self.outcome.name} {self.description}"
        shown = "; ".join(str(error) for error in self.errors[:ERRORS_SHOWN])
        rest = len(self.errors) - ERRORS_SHOWN
        more = f"; and {rest} more" if rest > 0 else ""
        return f"{self.outcome.name} {self.description}: {shown}{more}"


class PreflightFailed(Exception):
    """A run database failed a check that a load cannot read past.

    Raised for the operator rather than for a caller to recover from: every
    finding has already been logged and sent to Sentry by the time this is
    raised, and the message is the summary.
    """


class PreflightCheck(ABC):
    """One question put to a run database before a load reads it.

    A subclass supplies `description`, the `query` to ask, and `evaluate` to
    say what the answer means. The query is run and drained here, so an
    implementation is handed rows rather than a cursor and can neither leak
    one nor read from a closed one.
    """

    description: ClassVar[str]
    query: ClassVar[str]

    def run(self, connection: sqlite3.Connection) -> CheckResult:
        """Run the preflight check query.

        :param connection: An open, read-only connection to the run database,
            with `row_factory` set to `sqlite3.Row`.
        :return: What the check made of it.
        """
        try:
            with closing(connection.execute(self.query)) as cursor:
                rows = cursor.fetchall()
        except sqlite3.Error as error:
            return self.failed(
                [
                    CheckError(
                        f"the run database would not answer it ({error}), so "
                        "it is not one this loader can read",
                        {"query_error": str(error)},
                    )
                ]
            )
        return self.evaluate(rows)

    @abstractmethod
    def evaluate(self, rows: Sequence[sqlite3.Row]) -> CheckResult:
        """Say what the query's answer means.

        :param rows: Everything `query` returned, already read off the cursor.
        :return: The check's verdict, built with `passed`, `partial` or
            `failed`.
        """

    def passed(self) -> CheckResult:
        """This check found nothing wrong."""
        return CheckResult(self.description, CheckOutcome.PASSED)

    def partial(self, errors: Iterable[CheckError]) -> CheckResult:
        """The load can go on, but will not see everything.

        :param errors: What was found.
        """
        return CheckResult(
            self.description, CheckOutcome.PARTIAL, tuple(errors)
        )

    def failed(self, errors: Iterable[CheckError]) -> CheckResult:
        """The load must not go on.

        :param errors: What was found.
        """
        return CheckResult(
            self.description, CheckOutcome.FAILED, tuple(errors)
        )


class InvalidRows(PreflightCheck):
    """Rows the scraper itself marked unusable.

    Every jkent loader is responsible for skipping these.
    """

    description = "rows the scrape marked invalid"
    query = """
        SELECT
            result_type,
            SUM(CASE WHEN is_valid = 1 THEN 1 ELSE 0 END) AS valid,
            SUM(CASE WHEN is_valid = 1 THEN 0 ELSE 1 END) AS invalid
        FROM results
        GROUP BY result_type
        ORDER BY result_type
    """

    def evaluate(self, rows: Sequence[sqlite3.Row]) -> CheckResult:
        """Report every result type holding rows the load will not read.

        :param rows: One row per result type, with its valid and invalid
            counts.
        :return: `PARTIAL` where any result type has invalid rows, since the
            load can read the rest, and `PASSED` where none has.
        """
        errors = [
            CheckError(
                f"{row['invalid']} of {row['valid'] + row['invalid']} "
                f"{row['result_type']} rows are marked invalid, and no load "
                "will read them",
                {
                    "result_type": row["result_type"],
                    "invalid": row["invalid"],
                    "valid": row["valid"],
                },
            )
            for row in rows
            if row["invalid"]
        ]
        return self.partial(errors) if errors else self.passed()


class UnhashedFiles(PreflightCheck):
    """Downloaded files the archive recorded no content hash for.

    A merge will not publish a file it cannot name by content, so each of
    these becomes a document with no file.
    """

    description = "downloaded files with no content hash"
    query = """
        SELECT
            COUNT(*) AS total,
            COALESCE(
                SUM(
                    CASE WHEN COALESCE(content_hash, '') <> '' THEN 1 ELSE 0 END
                ),
                0
            ) AS hashed
        FROM archived_files
    """

    def evaluate(self, rows: Sequence[sqlite3.Row]) -> CheckResult:
        """Report anything short of every downloaded file being hashed.

        :param rows: The one row an aggregate with no `GROUP BY` always
            returns, even over an empty archive.
        :return: `PARTIAL` unless every file has a hash; an empty archive
            passes.
        """
        total, hashed = rows[0]["total"], rows[0]["hashed"]
        if hashed == total:
            return self.passed()
        return self.partial(
            [
                CheckError(
                    f"{total - hashed} of {total} downloaded files have no "
                    "content hash, so no merge will publish them and the "
                    "documents pointing at them will be written with no file",
                    {
                        "unhashed": total - hashed,
                        "hashed": hashed,
                        "total": total,
                    },
                )
            ]
        )


STANDARD_CHECKS: Final[tuple[PreflightCheck, ...]] = (
    InvalidRows(),
    UnhashedFiles(),
)
"""What every jkent run database is asked, whichever loader is reading it.

Kept apart from a loader's own `extra_checks` so that a loader adding a check
of its own cannot drop these by forgetting to repeat them."""


def run_checks(
    connection: sqlite3.Connection, checks: Iterable[PreflightCheck]
) -> tuple[CheckResult, ...]:
    """Put every check to the run database, in order.

    Every check runs even once one has failed, so an operator gets the whole
    picture from one attempt rather than fixing the database one check at a
    time. Acting on the results -- logging them, and stopping the load -- is
    the caller's.

    :param connection: An open, read-only connection to the run database,
        with `row_factory` set to `sqlite3.Row`.
    :param checks: The checks to run.
    :return: What each of them made of it, in the order they were given.
    """
    return tuple(check.run(connection) for check in checks)
