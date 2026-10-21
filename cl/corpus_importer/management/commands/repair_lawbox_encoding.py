"""Management command to repair CP1252-mis-encoded Lawbox content (issue #410).

The Lawbox importer (removed in commit 805877a36) decoded the corpus's HTML
files under the files' self-declared ``ISO-8859-1`` charset. Bytes in the
``0x80-0x9F`` range are actually CP1252 code points, so they were stored as
the C1 control characters (U+0080-U+009F) or the replacement character
(U+FFFD). The corruption lives only in stored ``Opinion.html_lawbox`` rows
(and, for already-annotated rows, in the derived ``Opinion.html_with_citations``
field); no current ingestion path writes ``html_lawbox``.

This command iterates ``Opinion`` rows that have ``html_lawbox`` content,
safely repairs the corruption (see ``cl.lib.string_utils.repair_lawbox_cp1252``)
and re-saves via ``Opinion.save(update_fields=[...])``. Saving through the ORM
is deliberate: ``html_lawbox`` and ``html_with_citations`` are members of
``Opinion.es_o_field_tracker``, so an ORM save triggers the project's standard
Elasticsearch partial-update path (``cl.lib.es_signal_processor``) without any
ad-hoc indexing code.

``html_with_citations`` is derived from whichever of an Opinion's text sources
ranks highest (see ``cl.citations.utils.make_get_citations_kwargs``), and
``html_lawbox`` is only that source when no higher-priority corpus — Harvard,
the scanning project, Columbia or the 2020 anonymous database — contributed to
the cluster. So this command re-dispatches citation annotation only for the
repaired opinions that qualify
(``cl.citations.utils.lawbox_is_citation_source_filter``); repairing the
others in the database is still correct, but re-annotating them would only
rebuild the same ``html_with_citations`` from their other source.

The command is idempotent: ``repair_lawbox_cp1252`` only mutates flagged rows,
so a second run is a no-op.
"""

from itertools import batched
from typing import Literal, cast

from django.core.management.base import CommandParser
from django.db import transaction
from django.db.models import Count

from cl.citations.tasks import (
    find_citations_and_parentheticals_for_opinion_by_pks,
)
from cl.citations.utils import lawbox_is_citation_source_filter
from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_utils import (
    looks_like_lawbox_cp1252_corruption,
    repair_lawbox_content_if_needed,
)
from cl.lib.types import OptionsType
from cl.search.cluster_sources import ClusterSources
from cl.search.models import Opinion, OpinionContent

DEFAULT_SCAN_CHUNK_SIZE = 1_000
DEFAULT_OPINIONS_PER_TASK = 50
DEFAULT_THROTTLE_MIN_ITEMS = 50

# Outcome of inspecting one Opinion. "unrecoverable" means corruption markers
# are present but the original bytes are gone (see repair_lawbox_cp1252).
RepairOutcome = Literal["repaired", "unrecoverable", "clean"]


class Command(VerboseCommand):
    help = (
        "Repair CP1252-mis-encoded Lawbox content in Opinion.html_lawbox "
        "(GitHub issue #410). Only rows flagged by the corruption detector "
        "are modified."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--doc-id",
            type=int,
            nargs="*",
            help="Specific Opinion ids to repair.",
        )
        parser.add_argument(
            "--start-id",
            type=int,
            help="Start of an Opinion.id range to repair (inclusive).",
        )
        parser.add_argument(
            "--end-id",
            type=int,
            help="End of an Opinion.id range to repair (inclusive).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Detect and report corruption but do not modify the DB.",
        )
        parser.add_argument(
            "--skip-annotate",
            action="store_true",
            default=False,
            help=(
                "Do not re-dispatch the citation annotation task for repaired "
                "opinions. Use this if you plan to re-run find_citations "
                "separately. html_with_citations will keep any corruption it "
                "already has until you do."
            ),
        )
        parser.add_argument(
            "--disable-citation-count-update",
            action="store_true",
            default=False,
            help=(
                "Forwarded to the annotation task. Mirrors the flag of the "
                "same name on `find_citations`."
            ),
        )
        parser.add_argument(
            "--queue",
            default="batch1",
            help=(
                "Celery queue for the citation annotation tasks. Mirrors "
                "`find_citations --queue`."
            ),
        )
        parser.add_argument(
            "--scan-chunk-size",
            type=int,
            default=DEFAULT_SCAN_CHUNK_SIZE,
            help="Number of Opinion rows fetched per database round-trip.",
        )
        parser.add_argument(
            "--opinions-per-task",
            type=int,
            default=DEFAULT_OPINIONS_PER_TASK,
            help=(
                "Number of opinions sent to a single citation annotation "
                "task. Mirrors `find_citations --opinions-per-task`; keep it "
                "small, since each task is processed by one Celery worker."
            ),
        )
        parser.add_argument(
            "--throttle-min-items",
            type=int,
            default=DEFAULT_THROTTLE_MIN_ITEMS,
            help=(
                "Control the max number of annotation tasks sent to Celery. "
                "Mirrors `find_citations --throttle-min-items`."
            ),
        )

    def handle(self, *args: list, **options: OptionsType) -> None:
        super().handle(*args, **options)

        dry_run = bool(options.get("dry_run"))
        skip_annotate = bool(options.get("skip_annotate"))
        disable_citation_count_update = bool(
            options.get("disable_citation_count_update")
        )
        queue = cast(str, options["queue"])
        scan_chunk_size = cast(int, options["scan_chunk_size"])
        opinions_per_task = cast(int, options["opinions_per_task"])
        throttle_min_items = cast(int, options["throttle_min_items"])

        queryset = Opinion.objects.exclude(html_lawbox="").order_by("pk")
        doc_ids = options.get("doc_id")
        if doc_ids:
            queryset = queryset.filter(pk__in=doc_ids)
        if options.get("start_id") is not None:
            queryset = queryset.filter(pk__gte=options["start_id"])
        if options.get("end_id") is not None:
            queryset = queryset.filter(pk__lte=options["end_id"])

        total = queryset.count()
        logger.info(
            "Scanning %d opinion(s) with html_lawbox content (dry_run=%s).",
            total,
            dry_run,
        )

        scanned = 0
        repaired = 0
        unrecoverable = 0
        annotation_pks: list[int] = []

        opinion_pks = queryset.values_list("pk", flat=True).iterator(
            chunk_size=scan_chunk_size
        )
        for opinion_pk in opinion_pks:
            scanned += 1
            outcome = self._repair_one_opinion(opinion_pk, dry_run=dry_run)
            if outcome == "repaired":
                repaired += 1
                annotation_pks.append(opinion_pk)
            elif outcome == "unrecoverable":
                unrecoverable += 1

            if scanned % 1000 == 0:
                logger.info(
                    "Scanned %d/%d, repaired %d.",
                    scanned,
                    total,
                    repaired,
                )

        logger.info(
            "Done. Scanned %d opinion(s): repaired %d, left %d unchanged "
            "(no corruption detected, or only markers whose original byte is "
            "unrecoverable).",
            scanned,
            repaired,
            scanned - repaired,
        )
        if unrecoverable:
            logger.warning(
                "%d opinion(s) carry corruption markers that cannot be "
                "repaired from the stored text: U+FFFD, or one of the five C1 "
                "bytes CP1252 leaves undefined (0x81, 0x8D, 0x8F, 0x90, "
                "0x9D). Those bytes are gone for good, so review those rows "
                "manually if they matter.",
                unrecoverable,
            )

        if dry_run:
            # Nothing was written, so there is nothing to re-annotate.
            return

        if skip_annotate:
            logger.info(
                "Skipping citation annotation for %d repaired opinion(s) "
                "(--skip-annotate). Re-run find_citations afterwards so "
                "html_with_citations picks up the repaired html_lawbox.",
                len(annotation_pks),
            )
            return

        self._dispatch_annotation(
            annotation_pks,
            queue=queue,
            disable_citation_count_update=disable_citation_count_update,
            opinions_per_task=opinions_per_task,
            throttle_min_items=throttle_min_items,
        )

    def _dispatch_annotation(
        self,
        opinion_pks: list[int],
        queue: str,
        disable_citation_count_update: bool,
        opinions_per_task: int,
        throttle_min_items: int,
    ) -> None:
        """Re-dispatch citation annotation for the repaired opinions that need
        it.

        Tasks are dispatched in small batches and throttled, mirroring
        ``find_citations``: one task iterates its opinions inside a single
        Celery worker, so a large batch is merely slow rather than parallel,
        and an unthrottled flood of tasks can overwhelm the queue.

        Only opinions whose ``html_with_citations`` derives from
        ``html_lawbox`` are dispatched. That filter is evaluated in SQL, so the
        higher-priority text columns are never loaded into Python.

        :param opinion_pks: The Opinion ids that were repaired.
        :param queue: The Celery queue to send the tasks to.
        :param disable_citation_count_update: Forwarded to the task.
        :param opinions_per_task: Opinions per annotation task.
        :param throttle_min_items: Keeps the queue between this and twice it.
        :return: None
        """
        if not opinion_pks:
            logger.info("No opinion was repaired; nothing to re-annotate.")
            return

        throttle = CeleryThrottle(queue_name=queue)
        throttle.update_min_items(throttle_min_items)
        tasks_sent = 0
        dispatched = 0
        for chunk in batched(opinion_pks, opinions_per_task):
            source_pks = list(
                Opinion.objects.filter(pk__in=list(chunk))
                .filter(lawbox_is_citation_source_filter())
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            if not source_pks:
                # Every opinion in this chunk prefers another corpus for
                # annotation; re-running it would only rebuild the same
                # html_with_citations from that other source.
                continue
            throttle.maybe_wait()
            find_citations_and_parentheticals_for_opinion_by_pks.apply_async(
                args=(
                    source_pks,
                    True,  # disable_parenthetical_groups (bulk-safe)
                    disable_citation_count_update,
                ),
                queue=queue,
            )
            tasks_sent += 1
            dispatched += len(source_pks)

        logger.info(
            "Re-dispatched citation annotation for %d of %d repaired "
            "opinion(s), in %d task(s) on the '%s' queue, so "
            "html_with_citations is regenerated from the repaired "
            "html_lawbox. The other %d prefer another corpus for annotation "
            "(see cl.citations.utils.CITATION_SOURCE_FIELDS).",
            dispatched,
            len(opinion_pks),
            tasks_sent,
            queue,
            len(opinion_pks) - dispatched,
        )
        self._log_cluster_sources(opinion_pks)

    def _log_cluster_sources(self, opinion_pks: list[int]) -> None:
        """Report how the repaired opinions' clusters are sourced.

        The per-Opinion filter used by :meth:`_dispatch_annotation` is
        authoritative, but an operator reasons about this data by cluster
        ``source``, so log the breakdown and call out how many repaired
        opinions sit in a Lawbox-preferred cluster. A large disagreement
        between the two means a cluster's source metadata and its Opinions'
        populated fields do not match, which is worth following up separately.

        :param opinion_pks: The Opinion ids that were repaired.
        :return: None
        """
        counts: dict[str, int] = {}
        for pk_chunk in batched(opinion_pks, DEFAULT_SCAN_CHUNK_SIZE):
            rows = (
                Opinion.objects.filter(pk__in=list(pk_chunk))
                .values("cluster__source")
                .annotate(n=Count("pk"))
                .values_list("cluster__source", "n")
            )
            for source, n in rows:
                counts[source] = counts.get(source, 0) + n

        lawbox_preferred = sum(
            n
            for source, n in counts.items()
            if ClusterSources.lawbox_is_best_source(source)
        )
        logger.info(
            "Repaired opinions by cluster source: %s. %d sit in a "
            "Lawbox-preferred cluster (%s); the rest also received content "
            "from the Columbia, scanning-project, Harvard or 2020 anonymous "
            "corpora.",
            counts,
            lawbox_preferred,
            ", ".join(sorted(ClusterSources.lawbox_citation_sources())),
        )

    def _repair_one_opinion(
        self, opinion_pk: int, dry_run: bool
    ) -> RepairOutcome:
        """Repair html_lawbox (and any LAWBOX OpinionContent) for one opinion.

        :param opinion_pk: The Opinion to repair.
        :param dry_run: When True, report what would change but write nothing.
        :return: "repaired" if the opinion was (or would be) modified,
            "unrecoverable" if it carries markers whose original byte is gone
            for good, and "clean" if there is nothing to do.

        Saving goes through the ORM on purpose: ``html_lawbox`` is a member of
        ``Opinion.es_o_field_tracker``, so ``Opinion.save()`` triggers the
        project's standard Elasticsearch partial-update path
        (``cl.lib.es_signal_processor``) without any ad-hoc indexing code, and
        pghistory snapshots the change.
        """
        # Only the fields this method actually touches are loaded; the rest
        # are deferred. The Elasticsearch signal handler skips deferred fields
        # (see cl.lib.es_signal_processor.check_fields_that_changed), so they
        # cost nothing there. The one exception is handle_es_save's
        # ``instance.main_version`` check, which is deferred here and so costs
        # one extra SELECT per repaired row -- negligible, since only repaired
        # rows are saved. Do not "fix" that by adding ``main_version`` to
        # only(): it would select_related the whole related Opinion on every
        # scanned row instead.
        opinion = (
            Opinion.objects.only(
                "html_lawbox",
                # Opinion.save() -> Opinion.clean() reads both of these.
                "type",
                "ordering_key",
            )
            .get(pk=opinion_pk)
        )
        new_html_lawbox, html_lawbox_changed = repair_lawbox_content_if_needed(
            opinion.html_lawbox
        )

        # Defensively repair any OpinionContent rows that mirror the Lawbox
        # field. OpinionContent is a normalized table introduced by migration
        # 0055; today no production writer copies Lawbox content into it, but
        # if a future backfill does, this keeps the two stores consistent.
        contents_changed = False
        new_contents: list[OpinionContent] = []
        for content in opinion.contents.filter(source=OpinionContent.LAWBOX):
            new_content_text, content_changed = (
                repair_lawbox_content_if_needed(content.content)
            )
            if content_changed:
                contents_changed = True
                content.content = new_content_text
                new_contents.append(content)

        if not html_lawbox_changed and not contents_changed:
            if looks_like_lawbox_cp1252_corruption(opinion.html_lawbox):
                # Markers are present, but their original bytes are
                # unrecoverable, so nothing can be rewritten.
                return "unrecoverable"
            return "clean"

        if dry_run:
            logger.info(
                "[dry-run] Opinion %s: would repair html_lawbox "
                "(html_lawbox_changed=%s, opinioncontent_changed=%s).",
                opinion_pk,
                html_lawbox_changed,
                contents_changed,
            )
            return "repaired"

        with transaction.atomic():
            if html_lawbox_changed:
                opinion.html_lawbox = new_html_lawbox
                # update_fields=[html_lawbox] keeps the save cheap and confines
                # the ES partial update / pghistory snapshot to this column.
                opinion.save(update_fields=["html_lawbox"])
            if contents_changed:
                OpinionContent.objects.bulk_update(new_contents, ["content"])

        logger.info(
            "Repaired opinion %s (html_lawbox_changed=%s, "
            "opinioncontent_changed=%s).",
            opinion_pk,
            html_lawbox_changed,
            contents_changed,
        )
        return "repaired"
