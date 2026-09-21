import csv
import json
import os
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from django.conf import settings
from django.core.management.base import CommandError, CommandParser
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from cl.corpus_importer.management.commands.audit_transposed_opinions import (
    FILE_FIELDS,
    PROFILES,
    docket_numbers,
)
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.search.models import Opinion

# What travels with a scraped file: the four file columns, the hash of the
# file's bytes, and the two facts the extraction pass recorded about it.
MOVED_FIELDS = FILE_FIELDS + ["sha1", "page_count", "extracted_by_ocr"]
# html_with_citations is rebuilt from whichever text a record ends up with,
# so it is saved for rollback but never moved.
SAVED_FIELDS = MOVED_FIELDS + ["html_with_citations"]
# The file facts the audit report records for every source.
AUDITED_FIELDS = ["sha1", "download_url", "local_path"]
EMPTY: dict[str, Any] = {
    "download_url": "",
    "local_path": "",
    "html": "",
    "plain_text": "",
    "sha1": "",
    "page_count": None,
    "extracted_by_ocr": False,
}
# Text that does not come from the scraped file. A record holding any of
# these builds its citations and its search text from it, not from the file.
OTHER_TEXT = ["xml_harvard", "html_anon_2020", "html_columbia", "html_lawbox"]

READY = "ready"
APPLIED = "applied"
ALREADY_APPLIED = "already applied"
SKIPPED = "skipped"
RESTORED = "restored"
ALREADY_RESTORED = "already restored"

CYCLE = "cycle"
CHAIN = "chain"

# The map file links every record for a reader outside the code.
SITE = "https://www.courtlistener.com"

GIVES_AND_RECEIVES = "gives and receives"
RECEIVES = "receives"
GIVES = "gives"


@dataclass
class Group:
    """One cycle or chain from the plan, ready to check and apply.

    :param key: stable name, the kind and the first member
    :param kind: cycle or chain
    :param court_id: the plan's court label, "mixed" for nd and ndctapp
    :param moves: source opinion id to receiving opinion id, in application
        order
    :param orphan: the chain start that loses its file and receives none
    :param end: the fileless record a chain ends on
    """

    key: str
    kind: str
    court_id: str
    moves: list[tuple[int, int]]
    orphan: int | None = None
    end: int | None = None

    @property
    def ids(self) -> list[int]:
        """Every opinion the group touches."""
        seen: dict[int, None] = {}
        for source, target in self.moves:
            seen.setdefault(source)
            seen.setdefault(target)
        return list(seen)

    @property
    def size(self) -> int:
        """How many files move."""
        return len(self.moves)


@dataclass
class Outcome:
    """What happened to one group.

    :param status: ready, applied, already applied, skipped, restored or
        already restored
    :param reason: why it was skipped
    :param citation_ids: records whose citation markup must be rebuilt
    """

    status: str
    reason: str | None = None
    citation_ids: list[int] = field(default_factory=list)


def load_groups(plan: dict[str, Any]) -> list[Group]:
    """Read the planner's cycles and chains.

    :param plan: the parsed plan file
    :return: the groups in plan order
    """
    groups = []
    for cycle in plan["cycles"]:
        groups.append(
            Group(
                key=f"{CYCLE}:{cycle['members'][0]}",
                kind=CYCLE,
                court_id=cycle["court_id"],
                moves=[
                    (m["file_on"], m["belongs_on"]) for m in cycle["moves"]
                ],
            )
        )
    for chain in plan["chains"]:
        groups.append(
            Group(
                key=f"{CHAIN}:{chain['members'][0]}",
                kind=CHAIN,
                court_id=chain["court_id"],
                moves=[
                    (m["file_on"], m["belongs_on"]) for m in chain["moves"]
                ],
                orphan=chain["orphan"],
                end=chain["end"],
            )
        )
    return groups


def snapshot(opinion: Opinion) -> dict[str, Any]:
    """The saved columns of a record as plain values."""
    values = {f: getattr(opinion, f) for f in SAVED_FIELDS}
    values["local_path"] = opinion.local_path.name or ""
    return values


def file_numbers(record: dict[str, Any]) -> set[str]:
    """The docket numbers the audit read from a record's file."""
    numbers = set(record.get("numbers_in_file") or [])
    if record.get("docket_number_in_file"):
        numbers.add(record["docket_number_in_file"])
    return numbers


def holds_no_file(values: dict[str, Any]) -> bool:
    """Whether none of the four file columns is set."""
    return not any(values[f] for f in FILE_FIELDS)


def check_group(
    group: Group,
    rows: dict[int, dict[str, Any]],
    audit: dict[int, dict[str, Any]],
) -> Outcome:
    """Decide whether a group can be applied to the rows as they are now.

    The rows are the current database values of every record the group
    touches: the saved columns plus court_id, docket_number, type,
    main_version_id and has_versions. A group is ready when every source
    still holds exactly the file the audit saw, every receiver either gives
    its own file away in the same group or holds none, and every receiver's
    docket carries a number the audit read from the file it receives. A
    group whose receivers already hold their files, and whose sources no
    longer hold theirs, is reported as already applied. Should a chain end
    also be a source elsewhere (the real plan has none), whichever group
    runs first wins and the other is skipped by these checks.

    :param group: the cycle or chain
    :param rows: current values by opinion id
    :param audit: audit records by opinion id
    :return: the outcome, with the reason when skipped
    """
    missing = [i for i in group.ids if i not in rows]
    if missing:
        return Outcome(SKIPPED, f"records not found: {missing}")
    for i in group.ids:
        if not rows[i]["type"]:
            return Outcome(SKIPPED, f"{i} has an empty type")
        if rows[i]["main_version_id"]:
            return Outcome(SKIPPED, f"{i} is a version of another opinion")
        if rows[i]["has_versions"]:
            return Outcome(SKIPPED, f"{i} has versions pointing at it")
    unaudited = [s for s, _ in group.moves if s not in audit]
    if unaudited:
        return Outcome(SKIPPED, f"sources not in the audit: {unaudited}")

    def holds(i: int, seen: dict[str, Any]) -> bool:
        return all(rows[i][f] == seen[f] for f in AUDITED_FIELDS)

    untouched = all(holds(s, audit[s]) for s, _ in group.moves)
    done = all(holds(t, audit[s]) for s, t in group.moves)
    if done and group.orphan is not None:
        done = (
            holds_no_file(rows[group.orphan])
            and not rows[group.orphan]["sha1"]
        )
    # Two sources holding one identical file would satisfy `done` before
    # any move, so the sources must have given their files away as well.
    if done and not untouched:
        return Outcome(ALREADY_APPLIED)

    for source, target in group.moves:
        row, seen = rows[source], audit[source]
        for f in AUDITED_FIELDS:
            if row[f] != seen[f]:
                return Outcome(
                    SKIPPED,
                    f"{source} {f} changed since the audit: "
                    f"{row[f]!r} is not {seen[f]!r}",
                )
        if target == group.end and not holds_no_file(rows[target]):
            return Outcome(SKIPPED, f"chain end {target} holds a file now")
        profile = PROFILES.get(rows[target]["court_id"])
        if profile is None:
            return Outcome(
                SKIPPED, f"{target} is in court {rows[target]['court_id']}"
            )
        owned = docket_numbers(rows[target]["docket_number"], profile)
        if not owned & file_numbers(seen):
            return Outcome(
                SKIPPED,
                f"{target} docket {rows[target]['docket_number']!r} carries "
                f"none of the numbers in the file from {source}: "
                f"{sorted(file_numbers(seen))}",
            )
    return Outcome(READY)


def needs_citations(values: dict[str, Any]) -> bool:
    """Whether a record's citation markup comes from its scraped file."""
    return not any(values.get(f) for f in OTHER_TEXT)


def find_collisions(
    plan_groups: list[Group], audit: dict[int, dict[str, Any]]
) -> list[tuple[int, str]]:
    """Records outside the plan that already carry one of the moving hashes.

    A second row with the same sha1 is what the duplicate deleter removes,
    so the moves must not create one. Records inside the plan are left to
    the per-group checks: after a chain is applied its end holds a moving
    hash, and that is the intended state.

    :param plan_groups: the groups about to be applied
    :param audit: audit records by opinion id
    :return: (opinion id, sha1) pairs that would collide
    """
    touched = {i for g in plan_groups for i in g.ids}
    hashes = {
        audit[s]["sha1"]
        for g in plan_groups
        for s, _ in g.moves
        if s in audit and audit[s]["sha1"]
    }
    return list(
        Opinion.objects.filter(sha1__in=hashes)
        .exclude(pk__in=touched)
        .values_list("pk", "sha1")
    )


def load_rows(ids: list[int], lock: bool) -> dict[int, Opinion]:
    """Fetch the records a group touches, locked when writing.

    Every column is loaded, because the search index update compares the
    saved values against the loaded ones and skips deferred columns. Locks
    are taken in id order so two runs cannot deadlock.
    """
    qs = (
        Opinion.objects.select_related("cluster__docket")
        .filter(pk__in=ids)
        .order_by("pk")
    )
    if lock:
        qs = qs.select_for_update(of=("self",))
    return {o.pk: o for o in qs}


def row_values(opinion: Opinion, has_versions: bool) -> dict[str, Any]:
    """The facts check_group needs about one record."""
    values = snapshot(opinion)
    values.update(
        {f: getattr(opinion, f) for f in OTHER_TEXT},
        court_id=opinion.cluster.docket.court_id,
        docket_number=opinion.cluster.docket.docket_number,
        type=opinion.type,
        main_version_id=opinion.main_version_id,
        has_versions=has_versions,
    )
    return values


def versioned(ids: list[int]) -> set[int]:
    """The ids among these that other opinions point at as their main version.

    Such versions are skipped by the search index, so a file moved onto
    their main record would leave them stale.
    """
    return set(
        Opinion.objects.filter(main_version_id__in=ids)
        .values_list("main_version_id", flat=True)
        .distinct()
    )


def apply_group(
    group: Group,
    audit: dict[int, dict[str, Any]],
    rollback: TextIO | None,
    wait: Callable[[int], None],
) -> Outcome:
    """Move the files of one group inside one transaction.

    Source values are captured before anything is assigned, so a rotation
    of any length is correct. Each receiver takes the seven moved columns
    of its source; the orphan is emptied. An orphan left with no text at
    all also loses its citation markup, which was built from the file that
    left. The saves go through the ORM so the search index follows.

    :param group: the cycle or chain
    :param audit: audit records by opinion id
    :param rollback: where to record the previous values, or None for a
        dry run
    :param wait: called with the number of saves about to happen, so the
        caller can hold back while the index queue is full
    :return: the outcome
    """
    lock = rollback is not None
    with transaction.atomic():
        rows = load_rows(group.ids, lock)
        versions = versioned(group.ids)
        outcome = check_group(
            group,
            {i: row_values(o, i in versions) for i, o in rows.items()},
            audit,
        )
        # A receiver whose text is the file it gets needs new citation
        # markup, whether the move happens now or happened in an earlier
        # run. The orphan never does: markup built from other text is
        # unchanged, and markup built from the departed file is cleared.
        if outcome.status in (READY, ALREADY_APPLIED):
            for _, target in group.moves:
                if needs_citations(row_values(rows[target], False)):
                    outcome.citation_ids.append(target)
        if outcome.status != READY or rollback is None:
            return outcome

        before = {i: snapshot(o) for i, o in rows.items()}
        after: dict[int, dict[str, Any]] = {}
        origin: dict[int, int | None] = {}
        for source, target in group.moves:
            after[target] = {f: before[source][f] for f in MOVED_FIELDS}
            origin[target] = source
        if group.orphan is not None:
            after[group.orphan] = dict(EMPTY)
            origin[group.orphan] = None

        # The rollback line names the record whose values this one takes,
        # so a restore can recognise the fixed state from the same file
        # without writing every value twice.
        for i in after:
            rollback.write(
                json.dumps(
                    {
                        "group": group.key,
                        "opinion_id": i,
                        "before": before[i],
                        "after_from": origin[i],
                    }
                )
                + "\n"
            )
        rollback.flush()
        os.fsync(rollback.fileno())

        wait(len(after))
        for i, values in after.items():
            opinion = rows[i]
            for f, value in values.items():
                setattr(opinion, f, value)
            if i == group.orphan and not any(
                getattr(opinion, f) for f in OTHER_TEXT
            ):
                opinion.html_with_citations = ""
            opinion.save()
        outcome.status = APPLIED
        return outcome


def fixed_state(
    entry: dict[str, Any], befores: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    """The seven moved columns a record holds once its group was applied."""
    source = entry["after_from"]
    if source is None:
        return dict(EMPTY)
    return {f: befores[source][f] for f in MOVED_FIELDS}


def restore_group(
    key: str,
    entries: list[dict[str, Any]],
    dry_run: bool,
    wait: Callable[[int], None],
) -> Outcome:
    """Put one group's records back to their recorded previous values.

    A record is restored only when its seven moved columns still show the
    state the fix wrote; one that already shows the previous state is left
    alone. Any other state means something else changed the record, and
    the whole group is skipped. An orphan's fixed state is "no file", which
    any emptied record matches; the previous-state check runs first, so
    only a record emptied by something other than this fix could be
    restored to its old wrong file.

    :param key: the group's name, for the reasons
    :param entries: the rollback lines of that group
    :param dry_run: check only
    :param wait: called with the number of saves about to happen
    :return: the outcome
    """
    befores = {e["opinion_id"]: e["before"] for e in entries}
    with transaction.atomic():
        rows = load_rows(list(befores), not dry_run)
        pending = []
        for entry in entries:
            opinion = rows.get(entry["opinion_id"])
            if opinion is None:
                return Outcome(
                    SKIPPED, f"{key}: {entry['opinion_id']} not found"
                )
            now = snapshot(opinion)
            if all(now[f] == entry["before"][f] for f in SAVED_FIELDS):
                continue
            expected = fixed_state(entry, befores)
            if any(now[f] != expected[f] for f in MOVED_FIELDS):
                return Outcome(
                    SKIPPED,
                    f"{key}: {opinion.pk} is neither in the fixed nor the "
                    f"previous state (sha1 {now['sha1']!r}, local_path "
                    f"{now['local_path']!r})",
                )
            pending.append((opinion, entry["before"]))
        if not pending:
            return Outcome(ALREADY_RESTORED)
        if dry_run:
            return Outcome(READY)
        wait(len(pending))
        for opinion, values in pending:
            for f, value in values.items():
                setattr(opinion, f, value)
            opinion.save()
        return Outcome(RESTORED)


def write_map(
    path: Path,
    groups: list[Group],
    audit: dict[int, dict[str, Any]],
    outcomes: dict[str, Outcome],
) -> None:
    """Write one row per touched record: what it holds and what it will hold.

    :param path: the CSV to write
    :param groups: the plan's groups
    :param audit: audit records by opinion id
    :param outcomes: outcome by group key
    :return: None
    """
    ids = sorted({i for g in groups for i in g.ids})
    facts = {
        pk: (cluster_id, slug, court_id, docket_number, case_name)
        for pk, cluster_id, slug, court_id, docket_number, case_name in (
            Opinion.objects.filter(pk__in=ids).values_list(
                "pk",
                "cluster_id",
                "cluster__slug",
                "cluster__docket__court_id",
                "cluster__docket__docket_number",
                "cluster__case_name",
            )
        )
    }
    columns = [
        "opinion_id",
        "url",
        "court_id",
        "docket_number",
        "case_name",
        "group",
        "kind",
        "role",
        "method",
        "confidence",
        "file_before_local_path",
        "file_before_sha1",
        "file_goes_to",
        "file_after_from",
        "file_after_local_path",
        "file_after_sha1",
        "outcome",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for group in groups:
            outcome = outcomes[group.key]
            receives = {t: s for s, t in group.moves}
            gives = {s: t for s, t in group.moves}
            for i in group.ids:
                seen = audit.get(i, {})
                source = receives.get(i)
                origin = audit.get(source, {}) if source else {}
                cluster_id, slug, court_id, docket_number, case_name = (
                    facts.get(i, (None, "", "", "", ""))
                )
                writer.writerow(
                    {
                        "opinion_id": i,
                        "url": SITE
                        + reverse("view_case", args=[cluster_id, slug])
                        if cluster_id
                        else "",
                        "court_id": court_id,
                        "docket_number": docket_number,
                        "case_name": case_name,
                        "group": group.key,
                        "kind": group.kind,
                        "role": GIVES_AND_RECEIVES
                        if i in gives and i in receives
                        else RECEIVES
                        if i in receives
                        else GIVES,
                        "method": seen.get("target_method", ""),
                        "confidence": seen.get("confidence", ""),
                        "file_before_local_path": seen.get("local_path", ""),
                        "file_before_sha1": seen.get("sha1", ""),
                        "file_goes_to": gives.get(i, ""),
                        "file_after_from": source or "",
                        "file_after_local_path": origin.get("local_path", ""),
                        "file_after_sha1": origin.get("sha1", ""),
                        "outcome": outcome.status
                        + (f": {outcome.reason}" if outcome.reason else ""),
                    }
                )


def read_rollback(path: Path) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Yield each group's rollback lines in turn, without holding the file.

    A group's lines are written together, so the file streams group by
    group; the real file is a few hundred megabytes of text columns.
    """
    key, entries = None, []
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            if key is not None and entry["group"] != key:
                yield key, entries
                entries = []
            key = entry["group"]
            entries.append(entry)
    if key is not None:
        yield key, entries


class Command(VerboseCommand):
    help = (
        "Apply a plan from audit_transposed_opinions --plan: move each scraped "
        "file, with its sha1, page count and OCR flag, onto the record it "
        "belongs to, one cycle or chain per transaction. Dry run by default; "
        "--apply writes. Every applied group's previous values go to a "
        "rollback file that --restore reads back, again with --apply."
    )
    throttle: CeleryThrottle | None = None

    def add_arguments(self, parser: CommandParser) -> None:
        """Register the arguments.

        :param parser: the command's argument parser
        :return: None
        """
        parser.add_argument(
            "--plan", help="Plan JSON from audit_transposed_opinions --plan."
        )
        parser.add_argument(
            "--reports",
            nargs="+",
            default=[],
            help="The audit reports the plan was built from.",
        )
        parser.add_argument(
            "--output-dir",
            required=True,
            help="Where the result, map and rollback files are written.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Write to the database. Without it, --plan and --restore "
                "only check and report."
            ),
        )
        parser.add_argument(
            "--restore",
            help=(
                "A rollback file from an earlier --apply run to reverse. "
                "Records put back need find_citations again if it already "
                "ran on them."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Apply at most this many groups; the rest are only checked.",
        )
        parser.add_argument(
            "--queue-min",
            type=int,
            default=100,
            help=(
                "Pause while the search index queue holds more than this "
                "many tasks. Each saved record queues one."
            ),
        )
        parser.add_argument(
            "--no-throttle",
            action="store_true",
            help="Do not watch the queue; for a local run without Redis.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the chosen mode and write the result files.

        :return: None
        """
        super().handle(*args, **options)
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        if options["apply"] and not options["no_throttle"]:
            self.throttle = CeleryThrottle(
                min_items=options["queue_min"],
                queue_name=settings.CELERY_ETL_TASK_QUEUE,
            )

        if options["restore"]:
            result = self.restore(Path(options["restore"]), options["apply"])
        elif options["plan"]:
            result = self.fix(options, output_dir, stamp)
        else:
            raise CommandError("Give --plan or --restore.")

        result["generated_at"] = timezone.now().isoformat()
        result_path = output_dir / f"result_{stamp}.json"
        result_path.write_text(json.dumps(result, indent=2))
        logger.info("summary: %s", result["summary"])
        logger.info("Wrote %s", result_path)

    def wait(self, count: int) -> None:
        """Hold back until the index queue has room for count more tasks."""
        if self.throttle is None:
            return
        for _ in range(count):
            self.throttle.maybe_wait()

    def fix(
        self, options: dict[str, Any], output_dir: Path, stamp: str
    ) -> dict[str, Any]:
        """Check every group and, with --apply, move the files.

        :param options: the command options
        :param output_dir: where the files go
        :param stamp: the run's timestamp for file names
        :return: the result to write
        """
        plan_path = Path(options["plan"])
        if not plan_path.is_file():
            raise CommandError(f"No such plan: {plan_path}")
        if not options["reports"]:
            raise CommandError("--reports is required with --plan.")
        audit: dict[int, dict[str, Any]] = {}
        for name in options["reports"]:
            path = Path(name)
            if not path.is_file():
                raise CommandError(f"No such report: {path}")
            for record in json.loads(path.read_text())["records"]:
                audit[record["opinion_id"]] = record
        groups = load_groups(json.loads(plan_path.read_text()))
        applying = options["apply"]

        # A dry run reports the collisions; a write refuses them.
        collisions = find_collisions(groups, audit)
        if collisions and applying:
            raise CommandError(
                f"{len(collisions)} records outside the plan already carry "
                f"a moving file's sha1; the first: {collisions[:5]}"
            )
        if collisions:
            logger.warning(
                "%s records outside the plan carry a moving file's sha1; "
                "--apply will refuse to run",
                len(collisions),
            )

        rollback_path = output_dir / f"rollback_{stamp}.jsonl"
        rollback = rollback_path.open("w") if applying else None
        outcomes: dict[str, Outcome] = {}
        applied = 0
        limit = options["limit"]
        try:
            for group in groups:
                writing = (
                    rollback if limit is None or applied < limit else None
                )
                outcome = apply_group(group, audit, writing, self.wait)
                outcomes[group.key] = outcome
                if outcome.status == APPLIED:
                    applied += 1
                logger.info(
                    "%s %s %s", group.key, outcome.status, outcome.reason or ""
                )
        finally:
            if rollback is not None:
                rollback.close()

        map_path = output_dir / f"moves_{stamp}.csv"
        write_map(map_path, groups, audit, outcomes)
        citation_ids = sorted(
            i for o in outcomes.values() for i in o.citation_ids
        )
        ids_path = output_dir / f"find_citations_ids_{stamp}.txt"
        ids_path.write_text(" ".join(map(str, citation_ids)))

        by_status = Counter(o.status for o in outcomes.values())
        return {
            "mode": "apply" if applying else "dry run",
            "plan": str(plan_path),
            "reports": options["reports"],
            "summary": {
                "groups": len(groups),
                "groups_by_status": dict(by_status),
                "moves": sum(
                    g.size for g in groups if outcomes[g.key].status == APPLIED
                ),
                "moves_ready": sum(
                    g.size for g in groups if outcomes[g.key].status == READY
                ),
                "citation_ids": len(citation_ids),
                "sha1_collisions": len(collisions),
            },
            "collisions": [
                {"opinion_id": i, "sha1": h} for i, h in collisions
            ],
            "files": {
                "map": str(map_path),
                "rollback": str(rollback_path) if applying else None,
                "find_citations_ids": str(ids_path),
            },
            "groups": [
                {
                    "key": g.key,
                    "kind": g.kind,
                    "court_id": g.court_id,
                    "size": g.size,
                    "status": outcomes[g.key].status,
                    "reason": outcomes[g.key].reason,
                }
                for g in groups
            ],
        }

    def restore(self, path: Path, applying: bool) -> dict[str, Any]:
        """Reverse the groups recorded in a rollback file.

        :param path: the rollback file
        :param applying: write, rather than check only
        :return: the result to write
        """
        if not path.is_file():
            raise CommandError(f"No such rollback file: {path}")
        outcomes = {}
        for key, entries in read_rollback(path):
            outcomes[key] = restore_group(
                key, entries, not applying, self.wait
            )
            logger.info(
                "%s %s %s",
                key,
                outcomes[key].status,
                outcomes[key].reason or "",
            )
        return {
            "mode": "restore" if applying else "restore dry run",
            "rollback": str(path),
            "note": (
                "Records put back need find_citations again if it already "
                "ran on them after the fix."
            ),
            "summary": {
                "groups": len(outcomes),
                "groups_by_status": dict(
                    Counter(o.status for o in outcomes.values())
                ),
            },
            "groups": [
                {"key": k, "status": o.status, "reason": o.reason}
                for k, o in outcomes.items()
            ],
        }
