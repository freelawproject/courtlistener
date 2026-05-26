"""Kent-backed merger base class.

A :class:`KentMerger` consumes a kent run's sqlite ``results`` table and
feeds each row through the merger framework. The shape every subclass
implements:

- ``aggregate_cls``: the Pydantic ``Aggregate`` class for the root tree.
- ``sql_path``: filename of a sibling ``.sql`` file producing one row
  per aggregate with a single ``scrape_json`` TEXT column.
- ``normalize(row) -> row``: Python-side transformation (override).

The base class wires the loop: open the kent.db, run the SQL, JSON-load
each row, normalize, validate against ``aggregate_cls``, merge, and
accumulate the resulting ``MergeOutcome``. Per-aggregate exceptions are
caught and logged so a single bad row doesn't abort the run.

Follow-ups produced by lifecycle hooks land in
``outcome.follow_ups``. Drivers that want to surface "process this file
through doctor and extract its plain text" emit :class:`IngestFile`
records; ``dispatch_ingest_files`` iterates them with a caller-chosen
dispatch mode (per-file or batch).
"""

import contextlib
import json
import logging
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cl.scrapers.mergers.follow_up import FollowUp
from cl.scrapers.mergers.nodes import Aggregate
from cl.scrapers.mergers.orchestrator import merge_one
from cl.scrapers.mergers.outcome import MergeOutcome

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IngestFile follow-up
# ---------------------------------------------------------------------------


def _ingest_file_default_dispatch(ingest: "IngestFile") -> Any:
    """Default per-file dispatcher invoked by ``IngestFile.__call__``.

    Enqueues the ``process_scraper_file`` Celery task with the
    IngestFile's typed payload. The task resolves ``model_label`` via
    ``django.apps.apps.get_model`` and writes its results back to the
    named fields on the target row.

    Lazy import so schema modules that pull this in don't drag Celery
    into contexts that don't need it.
    """
    from cl.scrapers.tasks import process_scraper_file

    process_scraper_file.delay(
        storage_url=ingest.storage_url,
        model_label=ingest.model_label,
        pk=ingest.pk,
        filepath_field=ingest.filepath_field,
        plain_text_field=ingest.plain_text_field,
        sha1_field=ingest.sha1_field,
        page_count_field=ingest.page_count_field,
        file_size_field=ingest.file_size_field,
        ocr_status_field=ingest.ocr_status_field,
    )


@dataclass(frozen=True, kw_only=True)
class IngestFile(FollowUp):
    """A ``FollowUp`` that asks the post-merge pipeline to fetch a file
    from S3, consult doctor for its suffix, and (for text-extractable
    types) extract plain text into the target Django model.

    The payload is fully self-describing: ``storage_url`` points at the
    file in S3; ``model_label`` + ``pk`` identify the Django row to
    update; the ``*_field`` strings name the columns that doctor's
    response should be written into. Drivers thus don't have to encode
    AbstractPDF's field names — they pass them in. (Future
    non-AbstractPDF target models work too.)

    Subclass of ``FollowUp`` so a single iteration of
    ``outcome.follow_ups`` returns both ordinary callables and
    IngestFile records; callers branch via isinstance.

    All new fields are kw-only to side-step the
    default-vs-non-default ordering trap inherent in frozen-dataclass
    inheritance.
    """

    # File location (S3 URL of the form ``s3://<bucket>/<key>``).
    storage_url: str

    # Target Django row.
    model_label: str  # 'app_label.ModelName' for ``apps.get_model``
    pk: int

    # Field-name knobs. Defaults match AbstractPDF; drivers using a
    # different target model override as needed.
    filepath_field: str = "filepath_local"
    plain_text_field: str = "plain_text"
    sha1_field: str = "sha1"
    page_count_field: str = "page_count"
    file_size_field: str = "file_size"
    ocr_status_field: str = "ocr_status"

    # ``name`` and ``fn`` are inherited from ``FollowUp`` — re-declare
    # with defaults so a caller can construct an ``IngestFile`` purely
    # from the typed payload fields above without specifying them.
    name: str = "ingest-file"
    fn: Callable[..., Any] = _ingest_file_default_dispatch

    def __call__(self) -> Any:
        """Override ``FollowUp.__call__`` to pass ``self`` to ``fn`` so
        the dispatcher receives the full typed payload rather than
        having to look it up via ``args`` / ``kwargs``.
        """
        return self.fn(self)


# ---------------------------------------------------------------------------
# KentMerger base
# ---------------------------------------------------------------------------


class KentMerger[AggregateT: Aggregate]:
    """Base class for mergers driven by a kent sqlite ``results`` table.

    Subclass contract:

    - Set ``aggregate_cls`` to the Pydantic Aggregate class for the root
      tree the merger writes.
    - Set ``sql_path`` to the filename of a sibling ``.sql`` file. The
      file is resolved relative to the *subclass's* module, so each
      driver keeps its query next to its code.
    - Override :meth:`normalize` for Python-side post-load transformation.

    Use:

    .. code-block:: python

        merger = NYCoAMerger("/path/to/NYCoA-2026-05-19.db")
        outcome = merger.run()
        # outcome.follow_ups now contains IngestFile records ready to
        # dispatch via your worker / batch infrastructure.
    """

    aggregate_cls: type[AggregateT]
    sql_path: str

    def __init__(
        self,
        kent_db_path: str | Path,
        *,
        using: str = "default",
    ) -> None:
        self.kent_db_path = Path(kent_db_path)
        self.using = using

    # -- SQL plumbing -------------------------------------------------------

    def _resolve_sql_path(self) -> Path:
        """Resolve ``sql_path`` relative to the subclass's module
        directory. Each driver lives in its own package, so siblings
        are the natural unit of co-location.
        """
        module = type(self).__module__
        module_file = __import__(module, fromlist=[""]).__file__
        if module_file is None:
            raise RuntimeError(
                f"Cannot resolve sql_path: module {module!r} has no __file__"
            )
        return Path(module_file).parent / self.sql_path

    def _load_sql(self) -> str:
        return self._resolve_sql_path().read_text()

    def _iter_scrape_rows(self) -> Iterator[dict[str, Any]]:
        """Open the kent.db read-only, run the configured SQL, and yield
        one parsed JSON dict per row. The SQL is expected to produce a
        single column named ``scrape_json``.
        """
        # ``uri=True`` + ``mode=ro`` enforces read-only access; the kent
        # run is a source artifact and should not be mutated by us.
        # ``contextlib.closing`` wraps the connection because
        # ``sqlite3.Connection``'s own context manager commits/rolls
        # back but does *not* close — see the sqlite3 docs. Without
        # this wrap, every ``run()`` leaks a connection (and trips
        # ResourceWarning floods under Hypothesis property tests).
        uri = f"file:{self.kent_db_path}?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            sql = self._load_sql()
            for row in conn.execute(sql):
                raw = row["scrape_json"]
                if raw is None:
                    continue
                yield json.loads(raw)

    # -- Subclass hook ------------------------------------------------------

    def normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        """Python-side normalization of a single SQL row before
        Pydantic validation. Default is identity; override for
        per-driver cleanup (string-stripping, file→entry matching, etc.).
        """
        return row

    # -- Aggregate construction --------------------------------------------

    def iter_aggregates(self) -> Iterator[AggregateT]:
        """Yield validated Aggregate instances. SQL rows that fail
        normalization or Pydantic validation are logged and skipped
        (the rest of the run continues).
        """
        for raw in self._iter_scrape_rows():
            try:
                normalized = self.normalize(raw)
                yield self.aggregate_cls.model_validate(normalized)
            except Exception:
                logger.exception(
                    "KentMerger %s: failed to construct Aggregate from row; "
                    "skipping. Row keys: %s",
                    type(self).__name__,
                    sorted(raw.keys()) if isinstance(raw, dict) else "N/A",
                )

    # -- Run loop ----------------------------------------------------------

    def run(self) -> MergeOutcome:
        """Iterate every aggregate, merge it, and accumulate the
        outcomes. Per-aggregate exceptions are logged and the run
        continues — a single bad docket doesn't abort the rest. The
        returned outcome is the union accumulated via ``|``.
        """
        outcome = MergeOutcome[Any]()
        for aggregate in self.iter_aggregates():
            try:
                one = merge_one(aggregate, using=self.using)
            except Exception:
                logger.exception(
                    "KentMerger %s: merge_one raised; skipping aggregate.",
                    type(self).__name__,
                )
                continue
            outcome = outcome | one
        return outcome

    # -- Follow-up dispatch ------------------------------------------------

    def dispatch_ingest_files(
        self, outcome: MergeOutcome
    ) -> list[IngestFile]:
        """Invoke every :class:`IngestFile` in ``outcome.follow_ups``.

        Each IngestFile's ``__call__`` enqueues its
        ``process_scraper_file`` Celery task. Returns the list of
        IngestFile records found so callers can log or post-process.
        """
        ingests = [
            fu for fu in outcome.follow_ups if isinstance(fu, IngestFile)
        ]
        for ingest in ingests:
            ingest()
        return ingests
