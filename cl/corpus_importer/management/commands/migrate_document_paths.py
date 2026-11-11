"""Move non-PACER document files into the RECAP storage layout.

SCOTUS, Texas and Florida documents were originally stored under their own
directories in S3. This command copies each file server-side to its new
RECAP-layout key and points the row at it. Old objects are left in place so
existing links keep working until a separate cleanup pass deletes them using
the manifest this command writes.

Resumability comes from the database itself: a row is selected while its file
path still starts with the old prefix and leaves the queryset once updated, so
rerunning after a crash only touches what's left. Copies are idempotent, so a
copy that succeeded before the row update simply happens again.
"""

import csv
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import batched, islice
from pathlib import Path
from typing import Any, TextIO

from botocore.exceptions import BotoCoreError, ClientError
from django.core.management import CommandError
from django.db import connection
from django.db.models import FileField, Model
from django.utils.timezone import now
from storages.backends.s3 import S3Storage

from cl.corpus_importer.utils import paginate_docs_queryset
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.lib.recap_utils import (
    format_path_date,
    get_bucket_name,
    make_recap_style_path,
    scotus_document_number_segments,
)
from cl.search.models import ScotusDocketMetadata, SCOTUSDocument
from cl.search.state.florida.models import FloridaDocument, florida_local_date
from cl.search.state.texas.models import TexasDocument

MANIFEST_COLUMNS = ("pk", "old_key", "new_key", "status")

# Per-document outcomes, tallied for the final summary.
MIGRATED = "migrated"
PLANNED = "planned"
MISSING_SOURCE = "missing_source"
ETAG_MISMATCH = "etag_mismatch"
FAILED = "failed"


@dataclass(frozen=True)
class PathMigrationSpec:
    """How to migrate one model's files into the RECAP layout.

    :ivar model: The model whose files are being moved.
    :ivar file_field: The FileField holding the storage key.
    :ivar old_prefix: Rows whose key starts with this are still to be migrated.
    :ivar docket_id_field: `values()` lookup for the docket id. Rows sharing a
        docket are processed on the same thread so the duplicate-key guard
        never races against itself.
    :ivar court_id_field: `values()` lookup for the docket's court id.
    :ivar extra_fields: Additional `values()` lookups `build_segments` needs.
    :ivar build_segments: Builds the filename segments that follow the bucket
        name from a `values()` row.
    """

    model: type[Model]
    file_field: str
    old_prefix: str
    docket_id_field: str
    court_id_field: str
    extra_fields: tuple[str, ...]
    build_segments: Callable[[dict[str, Any]], list[str]]

    @property
    def value_fields(self) -> tuple[str, ...]:
        """Every `values()` lookup a row needs for building its new key."""
        return (
            "pk",
            self.file_field,
            self.docket_id_field,
            self.court_id_field,
            *self.extra_fields,
        )


def scotus_document_segments(row: dict[str, Any]) -> list[str]:
    """Filename segments for a SCOTUSDocument row: date, document and
    attachment numbers."""
    return [
        format_path_date(row["docket_entry__date_filed"]),
        *scotus_document_number_segments(
            row["document_number"], row["attachment_number"], row["pk"]
        ),
    ]


def scotus_qp_segments(row: dict[str, Any]) -> list[str]:
    """Filename segments for a questions-presented file: docket date, `qp`."""
    return [format_path_date(row["docket__date_filed"]), "qp"]


def texas_document_segments(row: dict[str, Any]) -> list[str]:
    """Filename segments for a TexasDocument row: entry date and pk."""
    return [format_path_date(row["docket_entry__date_filed"]), str(row["pk"])]


def florida_document_segments(row: dict[str, Any]) -> list[str]:
    """Filename segments for a FloridaDocument row: entry date converted to
    Florida's timezone, and pk."""
    return [
        format_path_date(florida_local_date(row["docket_entry__date_filed"])),
        str(row["pk"]),
    ]


SPECS: dict[str, PathMigrationSpec] = {
    "scotus": PathMigrationSpec(
        model=SCOTUSDocument,
        file_field="filepath_local",
        old_prefix="scotus/documents/",
        docket_id_field="docket_entry__docket_id",
        court_id_field="docket_entry__docket__court_id",
        extra_fields=(
            "docket_entry__date_filed",
            "document_number",
            "attachment_number",
        ),
        build_segments=scotus_document_segments,
    ),
    "scotus-qp": PathMigrationSpec(
        model=ScotusDocketMetadata,
        file_field="questions_presented_file",
        old_prefix="scotus/qp/",
        docket_id_field="docket_id",
        court_id_field="docket__court_id",
        extra_fields=("docket__date_filed",),
        build_segments=scotus_qp_segments,
    ),
    "texas": PathMigrationSpec(
        model=TexasDocument,
        file_field="filepath_local",
        old_prefix="us/state/tx/",
        docket_id_field="docket_entry__docket_id",
        court_id_field="docket_entry__docket__court_id",
        extra_fields=("docket_entry__date_filed",),
        build_segments=texas_document_segments,
    ),
    "florida": PathMigrationSpec(
        model=FloridaDocument,
        file_field="filepath_local",
        old_prefix="us/state/fl/",
        docket_id_field="docket_entry__docket_id",
        court_id_field="docket_entry__docket__court_id",
        extra_fields=("docket_entry__date_filed",),
        build_segments=florida_document_segments,
    ),
}


@dataclass(frozen=True)
class S3Target:
    """The S3 client, bucket and ACL to copy objects with."""

    client: Any
    bucket: str
    acl: str | None


def get_s3_target(spec: PathMigrationSpec) -> S3Target:
    """Resolve the S3 client behind a spec's file field storage.

    Reusing the field's own storage keeps the bucket, credentials and ACL in
    step with what normal uploads use.
    """
    field = spec.model._meta.get_field(spec.file_field)
    assert isinstance(field, FileField), (
        f"{spec.file_field} is not a FileField"
    )
    storage = field.storage
    assert isinstance(storage, S3Storage), f"{spec.file_field} is not on S3"
    # django-storages assigns bucket_name and default_acl from settings at
    # runtime, so they are invisible to the type checker.
    s3: Any = storage
    return S3Target(
        client=s3.connection.meta.client,
        bucket=s3.bucket_name,
        acl=s3.default_acl,
    )


def compose_redis_key(spec_name: str) -> str:
    """Redis key holding the last pk scheduled for a spec, for --auto-resume."""
    return f"migrate_document_paths:{spec_name}:log"


def build_new_key(spec: PathMigrationSpec, row: dict[str, Any]) -> str:
    """Build the RECAP-layout key for a row, keeping the file's extension."""
    ext = Path(row[spec.file_field]).suffix or ".pdf"
    return make_recap_style_path(
        row[spec.court_id_field],
        row[spec.docket_id_field],
        spec.build_segments(row),
        ext,
    )


def reserve_key(spec: PathMigrationSpec, pk: int, key: str) -> str:
    """Return `key`, or the first `_N` variant no other row already claims.

    Mirrors `IncrementingAWSMediaStorage` so migrated names interoperate with
    ones the storage picks for new uploads. Only rows already pointed at the
    new layout are visible here, so callers must not process two rows of the
    same docket concurrently.
    """
    path = Path(key)
    candidate = key
    suffix = 0
    while (
        spec.model._default_manager.filter(**{spec.file_field: candidate})
        .exclude(pk=pk)
        .exists()
    ):
        suffix += 1
        candidate = str(path.with_name(f"{path.stem}_{suffix}{path.suffix}"))
    if suffix:
        logger.warning(
            "%s %s: key %s is already taken by another document; using %s.",
            spec.model.__name__,
            pk,
            key,
            candidate,
        )
    return candidate


class Manifest:
    """Thread-safe CSV log of every planned or completed move.

    Lines are written before the database update, so a line whose row was
    never updated just records a plan. Cleanup must therefore only delete an
    old key when the row currently points at the new key on the same line.
    """

    def __init__(self, path: Path) -> None:
        self._lock = threading.Lock()
        write_header = not path.exists() or path.stat().st_size == 0
        self._file: TextIO = path.open("a", newline="")
        self._writer = csv.writer(self._file)
        if write_header:
            self._writer.writerow(MANIFEST_COLUMNS)
            self._file.flush()

    def write(self, pk: int, old_key: str, new_key: str, status: str) -> None:
        """Append one line and flush it so a crash loses nothing."""
        with self._lock:
            self._writer.writerow([pk, old_key, new_key, status])
            self._file.flush()

    def close(self) -> None:
        """Close the underlying file."""
        self._file.close()


class PathMigrator:
    """Copies one model's files to the RECAP layout and updates the rows."""

    def __init__(
        self,
        spec: PathMigrationSpec,
        target: S3Target,
        manifest: Manifest,
        dry_run: bool,
    ) -> None:
        self.spec = spec
        self.target = target
        self.manifest = manifest
        self.dry_run = dry_run

    def migrate_row(self, row: dict[str, Any]) -> str:
        """Copy one document's file and point its row at the new key.

        Copy first, update second: if the process dies in between, the row is
        still selected on the next run and the copy is repeated harmlessly.

        :return: One of the outcome constants, for the summary tally.
        """
        spec = self.spec
        pk = row["pk"]
        old_key = row[spec.file_field]
        new_key = reserve_key(spec, pk, build_new_key(spec, row))

        if self.dry_run:
            self.manifest.write(pk, old_key, new_key, PLANNED)
            logger.info(
                "%s %s: %s -> %s", spec.model.__name__, pk, old_key, new_key
            )
            return PLANNED

        try:
            outcome = self._copy_object(pk, old_key, new_key)
        except (ClientError, BotoCoreError) as e:
            logger.error(
                "%s %s: copying %s to %s failed: %s",
                spec.model.__name__,
                pk,
                old_key,
                new_key,
                e,
            )
            return FAILED
        if outcome != MIGRATED:
            return outcome

        self.manifest.write(pk, old_key, new_key, MIGRATED)
        # A queryset update keeps the FileField from re-uploading and skips
        # signals; date_modified is bumped so API clients see the new URL.
        spec.model._default_manager.filter(pk=pk).update(
            **{spec.file_field: new_key, "date_modified": now()}
        )
        logger.debug(
            "%s %s: %s -> %s", spec.model.__name__, pk, old_key, new_key
        )
        return MIGRATED

    def _copy_object(self, pk: int, old_key: str, new_key: str) -> str:
        """Server-side copy old_key to new_key, verifying the result.

        :return: MIGRATED on success, or the outcome explaining why not.
        """
        client, bucket = self.target.client, self.target.bucket
        try:
            source = client.head_object(Bucket=bucket, Key=old_key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in (
                "404",
                "NoSuchKey",
            ):
                raise
            logger.error(
                "%s %s: source object %s does not exist in S3.",
                self.spec.model.__name__,
                pk,
                old_key,
            )
            return MISSING_SOURCE

        params: dict[str, Any] = {
            "Bucket": bucket,
            "CopySource": {"Bucket": bucket, "Key": old_key},
            "Key": new_key,
            # Carry over Cache-Control and Expires set at upload time.
            "MetadataDirective": "COPY",
        }
        if self.target.acl:
            # ACLs are never copied, so re-apply the storage's default.
            params["ACL"] = self.target.acl
        response = client.copy_object(**params)

        # Multipart uploads get a "<md5>-<parts>" ETag that a single-part copy
        # won't reproduce, so only single-part sources can be verified this way.
        source_etag = source["ETag"]
        copied_etag = response["CopyObjectResult"]["ETag"]
        if "-" not in source_etag and source_etag != copied_etag:
            logger.error(
                "%s %s: ETag mismatch after copying %s to %s (%s != %s); "
                "leaving the row unchanged.",
                self.spec.model.__name__,
                pk,
                old_key,
                new_key,
                source_etag,
                copied_etag,
            )
            return ETAG_MISMATCH
        return MIGRATED

    def migrate_group(self, rows: list[dict[str, Any]]) -> Counter[str]:
        """Migrate every row of one docket, sequentially, on the calling
        thread."""
        tally: Counter[str] = Counter()
        for row in rows:
            tally[self.migrate_row(row)] += 1
        return tally

    def migrate_group_in_thread(
        self, rows: list[dict[str, Any]]
    ) -> Counter[str]:
        """`migrate_group` for pool threads, which don't get Django's
        request-cycle cleanup: the thread's DB connection is closed after
        each group so idle pool threads don't pin connections."""
        try:
            return self.migrate_group(rows)
        finally:
            connection.close()


def group_rows_by_docket(
    rows: Iterable[dict[str, Any]], docket_id_field: str
) -> list[list[dict[str, Any]]]:
    """Group rows by docket so each docket is handled by a single thread.

    The duplicate-key guard in `reserve_key` only sees committed rows, so two
    rows of the same docket in flight at once could both claim the same key.
    Grouping removes that race without any cross-thread coordination.
    """
    groups: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row[docket_id_field], []).append(row)
    return list(groups.values())


def pending_pks(
    spec: PathMigrationSpec, auto_resume: bool, spec_name: str
) -> Iterator[int]:
    """Yield the pks of rows still stored under the old prefix, in pk order."""
    pks = spec.model._default_manager.filter(
        **{f"{spec.file_field}__startswith": spec.old_prefix}
    ).values_list("pk", flat=True)
    if auto_resume:
        last_pk = get_last_parent_document_id_processed(
            compose_redis_key(spec_name)
        )
        if last_pk:
            logger.info("Auto-resuming from pk %s.", last_pk)
            pks = pks.filter(pk__gt=last_pk)
    return paginate_docs_queryset(pks)


def run_migration(
    spec_name: str,
    manifest_path: Path,
    workers: int,
    batch_size: int,
    limit: int | None,
    dry_run: bool,
    auto_resume: bool,
) -> Counter[str]:
    """Migrate every pending row of a spec and return the outcome tally.

    Pages of pks are fetched in pk order; each page is grouped by docket and
    the groups are spread over the thread pool. The next page only starts
    once the current one finishes, so a docket spanning two pages is never
    processed on two threads at once.
    """
    spec = SPECS[spec_name]
    manifest = Manifest(manifest_path)
    migrator = PathMigrator(spec, get_s3_target(spec), manifest, dry_run)
    executor = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
    tally: Counter[str] = Counter()
    processed = 0
    start = time.monotonic()
    try:
        pks: Iterator[int] = pending_pks(spec, auto_resume, spec_name)
        if limit is not None:
            pks = islice(pks, limit)
        for pk_page in batched(pks, batch_size):
            rows = list(
                spec.model._default_manager.filter(pk__in=pk_page).values(
                    *spec.value_fields
                )
            )
            groups = group_rows_by_docket(rows, spec.docket_id_field)
            if executor:
                results = executor.map(
                    migrator.migrate_group_in_thread, groups
                )
            else:
                results = map(migrator.migrate_group, groups)
            for group_tally in results:
                tally.update(group_tally)
            processed += len(rows)
            if not dry_run:
                log_last_document_indexed(
                    max(pk_page), compose_redis_key(spec_name)
                )
            logger.info(
                "%s: processed %s rows in %.0fs; %s",
                spec_name,
                processed,
                time.monotonic() - start,
                dict(tally),
            )
    finally:
        if executor:
            executor.shutdown(wait=True)
        manifest.close()
    return tally


def check_destination_prefixes(spec_name: str) -> dict[str, int]:
    """Count objects already under each court's destination prefix.

    Meant to run once before the first migration: a non-zero count means the
    new key space isn't empty and the names could collide with foreign objects
    the database knows nothing about.

    :return: Object counts keyed by prefix.
    """
    spec = SPECS[spec_name]
    target = get_s3_target(spec)
    court_ids = (
        spec.model._default_manager.order_by()
        .values_list(spec.court_id_field, flat=True)
        .distinct()
    )
    paginator = target.client.get_paginator("list_objects_v2")
    counts: dict[str, int] = {}
    for court_id in court_ids:
        # get_bucket_name with an empty case id yields "gov.uscourts.<court>.",
        # the trailing dot keeping "tex." from matching "texapp".
        prefix = f"recap/{get_bucket_name(court_id, '')}"
        counts[prefix] = sum(
            page.get("KeyCount", 0)
            for page in paginator.paginate(Bucket=target.bucket, Prefix=prefix)
        )
    return counts


class Command(VerboseCommand):
    help = (
        "Copy SCOTUS, Texas or Florida document files to the RECAP storage "
        "layout in S3 and point their rows at the new keys. Old objects are "
        "kept; the manifest records old->new keys for a later cleanup."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            required=True,
            choices=sorted(SPECS),
            help="Which documents to migrate.",
        )
        parser.add_argument(
            "--manifest",
            type=Path,
            help="CSV file to append pk, old key, new key and status to. "
            "Required unless --check-destination is given.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=1,
            help="Threads copying concurrently. Rows of one docket always "
            "share a thread. Default: 1 (sequential).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Rows fetched per page. Default: 500.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Stop after this many rows, e.g. to check a sample first.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Compute and log the new keys and write them to the "
            "manifest as planned, without copying or updating anything. "
            "Since no row is updated, duplicates are not suffixed here; "
            "they show up as repeated new_key values in the manifest.",
        )
        parser.add_argument(
            "--auto-resume",
            action="store_true",
            default=False,
            help="Skip pks at or below the last one logged in Redis. Finish "
            "with a run without this flag to sweep any rows that failed.",
        )
        parser.add_argument(
            "--check-destination",
            action="store_true",
            default=False,
            help="Only count objects already under the destination prefixes "
            "for this model's courts, then exit.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        spec_name = options["model"]

        if options["check_destination"]:
            for prefix, count in check_destination_prefixes(spec_name).items():
                logger.info("%s: %s objects", prefix, count)
            return

        if options["manifest"] is None:
            raise CommandError("--manifest is required.")
        if options["workers"] < 1:
            raise CommandError("--workers must be at least 1.")

        tally = run_migration(
            spec_name,
            manifest_path=options["manifest"],
            workers=options["workers"],
            batch_size=options["batch_size"],
            limit=options["limit"],
            dry_run=options["dry_run"],
            auto_resume=options["auto_resume"],
        )
        logger.info("%s: done. %s", spec_name, dict(tally))
