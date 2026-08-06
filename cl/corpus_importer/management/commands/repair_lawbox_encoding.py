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
ad-hoc indexing code. ``html_with_citations`` is itself derived from
``html_lawbox`` (see ``cl.citations.annotate_citations.create_cited_html``),
so for each repaired opinion this command also re-dispatches the citation
annotation task to regenerate it.

The command is idempotent: ``repair_lawbox_cp1252`` only mutates flagged rows,
so a second run is a no-op.
"""

from typing import cast

from django.core.management.base import CommandParser
from django.db import transaction

from cl.citations.tasks import (
    find_citations_and_parentheticals_for_opinion_by_pks,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.string_utils import repair_lawbox_content_if_needed
from cl.lib.types import OptionsType
from cl.search.models import Opinion, OpinionContent

DEFAULT_BATCH_SIZE = 1_000


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
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help="Number of opinions to repair per database transaction.",
        )

    def handle(self, *args: list, **options: OptionsType) -> None:
        super().handle(*args, **options)

        dry_run = bool(options.get("dry_run"))
        skip_annotate = bool(options.get("skip_annotate"))
        disable_citation_count_update = bool(
            options.get("disable_citation_count_update")
        )
        queue = cast(str, options["queue"])
        batch_size = cast(int, options["batch_size"])

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
        annotation_pks: list[int] = []

        opinion_pks = queryset.values_list("pk", flat=True).iterator(
            chunk_size=batch_size
        )
        for opinion_pk in opinion_pks:
            scanned += 1
            changed = self._repair_one_opinion(opinion_pk, dry_run=dry_run)
            if changed:
                repaired += 1
                annotation_pks.append(opinion_pk)

            if scanned % 1000 == 0:
                logger.info(
                    "Scanned %d/%d, repaired %d.",
                    scanned,
                    total,
                    repaired,
                )

        logger.info(
            "Done. Scanned %d opinion(s): repaired %d, left %d unchanged "
            "(no corruption detected or mixed-content skipped).",
            scanned,
            repaired,
            scanned - repaired,
        )

        if dry_run or skip_annotate or not annotation_pks:
            return

        logger.info(
            "Re-dispatching citation annotation for %d repaired opinion(s) "
            "on the '%s' queue so html_with_citations is regenerated from "
            "the repaired html_lawbox.",
            len(annotation_pks),
            queue,
        )
        find_citations_and_parentheticals_for_opinion_by_pks.apply_async(
            args=(
                annotation_pks,
                True,  # disable_parenthetical_groups (bulk-safe)
                disable_citation_count_update,
            ),
            queue=queue,
        )

    def _repair_one_opinion(self, opinion_pk: int, dry_run: bool) -> bool:
        """Repair html_lawbox (and any LAWBOX OpinionContent) for one opinion.

        Returns True if the opinion's html_lawbox was changed (or would be,
        under --dry-run). Saves through the ORM so the Elasticsearch update
        path (``es_o_field_tracker`` -> ``update_es_document``) fires
        automatically, and so pghistory snapshots the change.
        """
        opinion = Opinion.objects.get(pk=opinion_pk)
        new_html_lawbox, html_lawbox_changed = repair_lawbox_content_if_needed(
            opinion.html_lawbox
        )

        # Defensively repair any OpinionContent rows that mirror the Lawbox
        # field. OpinionContent is a normalized table introduced by migration
        # 0055; today no production writer copies Lawbox content into it, but
        # if a future backfill does, this keeps the two stores consistent.
        contents_changed = False
        new_contents: list[OpinionContent] = []
        for content in opinion.contents.filter(
            source=OpinionContent.LAWBOX
        ):
            new_content_text, content_changed = (
                repair_lawbox_content_if_needed(content.content)
            )
            if content_changed:
                contents_changed = True
                content.content = new_content_text
                new_contents.append(content)

        if not html_lawbox_changed and not contents_changed:
            return False

        if dry_run:
            logger.info(
                "[dry-run] Opinion %s: would repair html_lawbox "
                "(html_lawbox_changed=%s, opinioncontent_changed=%s).",
                opinion_pk,
                html_lawbox_changed,
                contents_changed,
            )
            return html_lawbox_changed or contents_changed

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
        return html_lawbox_changed or contents_changed
