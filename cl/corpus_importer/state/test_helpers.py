"""Shared scaffolding for tests that load a jkent run database."""

import logging
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from cl.corpus_importer.state.ledger import PARTS as LEDGER_PARTS
from cl.corpus_importer.state.ledger import LoadLedger
from cl.corpus_importer.state.loader import JKentScrapeLoader
from cl.lib.redis_utils import get_redis_interface
from cl.tests.cases import TestCase

RESULTS_TABLE = (
    "CREATE TABLE results ("
    "  id INTEGER PRIMARY KEY,"
    "  result_type VARCHAR NOT NULL,"
    "  data_json VARCHAR NOT NULL,"
    "  is_valid BOOLEAN DEFAULT 1 NOT NULL"
    ")"
)
ARCHIVED_FILES_TABLE = (
    "CREATE TABLE archived_files ("
    "  id INTEGER PRIMARY KEY,"
    "  file_path VARCHAR NOT NULL,"
    "  content_hash VARCHAR,"
    "  file_size INTEGER,"
    "  expected_type VARCHAR"
    ")"
)
ARCHIVED_FILE_INSERT = (
    "INSERT INTO archived_files "
    "(file_path, content_hash, file_size, expected_type) "
    "VALUES (?, ?, ?, ?)"
)

#: An `archived_files` row: the stored path, its content hash, its size, and
#: the kind of file the scraper expected.
ArchivedFile = tuple[str, str | None, int | None, str | None]


def write_run_database(
    path: Path,
    results: Iterable[tuple[str, str]],
    archive: Iterable[ArchivedFile] = (),
) -> None:
    """Write a minimal stand-in for a jkent run database.

    Only the columns the loaders and the preflight checks read are created,
    since a loader's contract is with the `results` and `archived_files`
    tables rather than with the whole schema.

    Args:
        path: Where to write the database.
        results: The scrape results, as `(result_type, data_json)` pairs. The
            JSON is stored as given, so a test can write a blob that will not
            decode.
        archive: One row per file the run downloaded.
    """
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(RESULTS_TABLE)
        connection.execute(ARCHIVED_FILES_TABLE)
        connection.executemany(
            "INSERT INTO results (result_type, data_json) VALUES (?, ?)",
            results,
        )
        connection.executemany(ARCHIVED_FILE_INSERT, archive)
        connection.commit()


class RunDatabaseTestCase(TestCase):
    """A run database path in a temporary directory, and the Redis keys a load over it writes.

    The ledger and the checkpoint go to the real Redis, since the point of both
    is that they outlive the process that wrote them. Each test keys its run
    off its own id, so tests running in parallel never share one.

    Subclasses supply `loader_class`, the loader `loader()` builds by default.
    """

    def setUp(self) -> None:
        super().setUp()
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "run.db"
        self.key = f"state_scrape_load:test:{self.id()}"
        self.redis = get_redis_interface("CACHE")
        self.clear_run_keys()
        self.addCleanup(self.clear_run_keys)

    def clear_run_keys(self, key: str | None = None) -> None:
        """Take away a run's checkpoint and every part of its ledger.

        Args:
            key: The run key to clear, defaulting to the test's own. A load
                left to key itself off the run database needs its own cleanup.
        """
        key = key or self.key
        self.redis.delete(key, *(f"{key}:{part}" for part in LEDGER_PARTS))

    def ledger(self) -> LoadLedger:
        """The ledger the test's loads report into."""
        return LoadLedger(self.key)

    def enable_logging(self) -> None:
        """Let `assertLogs` see the loader's records for the rest of the test.

        The test settings disable logging, which would otherwise hide every
        record a test means to assert on.
        """
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable)

    def loader_class(self) -> type[JKentScrapeLoader[Any, Any]]:
        """The loader class `loader()` builds when given none."""
        raise NotImplementedError

    def loader(
        self,
        loader_class: type[JKentScrapeLoader[Any, Any]] | None = None,
        **kwargs: Any,
    ) -> JKentScrapeLoader[Any, Any]:
        """A loader over the test database, keeping a ledger by default.

        Neither wait sleeps by default. Celery runs eagerly under test, so the
        merges are already done and the ledger already full; anything a single
        pass finds outstanding really is outstanding for good, which is what a
        zero `in_flight_time` says. Tests that want the other exit set
        `in_flight_time` high and leave `verify_timeout` at zero.

        Args:
            loader_class: The class to build, defaulting to `loader_class()`.
            kwargs: Passed through to the loader.

        Returns:
            The loader.
        """
        kwargs.setdefault("run_key", self.key)
        kwargs.setdefault("in_flight_time", 0)
        kwargs.setdefault("verify_timeout", 0)
        return (loader_class or self.loader_class())(self.database, **kwargs)
