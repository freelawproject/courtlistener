"""Repair child documents whose denormalized parent fields have drifted.

Child documents in our parent/child indices copy a subset of their parent's
fields (a RECAPDocument copies `suitNature` from its Docket, an Opinion copies
`caseName` from its cluster) so that they can be matched without a join. Those
copies are kept current by `update_children_docs_by_query`, which finds children
with a search and therefore silently skips any child that isn't searchable when
it runs. A child missed that way keeps a stale copy indefinitely.

Stale copies are not merely cosmetic: search runs the user's query against the
parent and the children and returns the case if *either* matches, so a single
child with a stale value makes a case match queries its parent doesn't --
negations most visibly (see #7965).

This command re-pushes the parent's values onto every child, which is
idempotent, and can also report drift without writing anything.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db.models import QuerySet

from cl.lib.celery_utils import CeleryThrottle
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.indexing_utils import (
    get_last_parent_document_id_processed,
    log_last_document_indexed,
)
from cl.search.documents import (
    DocketDocument,
    ESRECAPDocument,
    OpinionClusterDocument,
    OpinionDocument,
)
from cl.search.models import SEARCH_TYPES, Docket, OpinionCluster
from cl.search.signals import o_field_mapping, recap_document_field_mapping
from cl.search.tasks import (
    get_parent_fields_for_children,
    update_children_docs_by_query,
)
from cl.search.types import ESDocumentClassType, ESModelType

SUPPORTED_SEARCH_TYPES = [SEARCH_TYPES.RECAP, SEARCH_TYPES.OPINION]

# The `timestamp` field records when a document was last written rather than
# anything copied from the parent, so it is never a sign of drift.
NON_CONTENT_FIELDS = {"timestamp"}


def compose_redis_key(search_type: str) -> str:
    """Compose the Redis key this command logs its progress to.

    :param search_type: The search type being processed.
    :return: A Redis key as a string.
    """
    return f"es_sync_child_docs_{search_type}:log"


@dataclass(frozen=True)
class ChildSyncConfig:
    """The parent/child pair a single run of this command operates on.

    :param parent_doc_class: The parent Elasticsearch Document class.
    :param child_doc_class: The child Elasticsearch Document class.
    :param child_join_type: The child's name in the index's join field.
    :param fields_map: A mapping from parent model field names to the child
    Elasticsearch fields they feed.
    """

    parent_doc_class: ESDocumentClassType
    child_doc_class: ESDocumentClassType
    child_join_type: str
    fields_map: dict[str, list[str]]

    @property
    def fields_to_update(self) -> list[str]:
        """The parent model field names to push onto children.

        :return: A list of parent model field names.
        """
        return list(self.fields_map.keys())


def get_sync_config(search_type: str) -> ChildSyncConfig:
    """Build the configuration for the given search type.

    The field maps are the same ones the save signals use, so this command
    repairs exactly the fields the live update path is responsible for.

    :param search_type: One of SUPPORTED_SEARCH_TYPES.
    :return: The ChildSyncConfig for that search type.
    """

    if search_type == SEARCH_TYPES.RECAP:
        return ChildSyncConfig(
            parent_doc_class=DocketDocument,
            child_doc_class=ESRECAPDocument,
            child_join_type="recap_document",
            fields_map=recap_document_field_mapping["save"][Docket][
                "docket_entry__docket"
            ],
        )
    return ChildSyncConfig(
        parent_doc_class=OpinionClusterDocument,
        child_doc_class=OpinionDocument,
        child_join_type="opinion",
        fields_map=o_field_mapping["save"][OpinionCluster]["sub_opinions"],
    )


def get_parent_queryset(search_type: str, pk_offset: int) -> QuerySet:
    """Build the queryset of parent instances to process.

    :param search_type: One of SUPPORTED_SEARCH_TYPES.
    :param pk_offset: The parent PK to start from.
    :return: A QuerySet of parents ordered by PK.
    """

    if search_type == SEARCH_TYPES.RECAP:
        # Only RECAP dockets are indexed, so anything else has no children to
        # repair.
        return Docket.objects.filter(
            pk__gte=pk_offset, source__in=Docket.RECAP_SOURCES()
        ).order_by("pk")
    return OpinionCluster.objects.filter(pk__gte=pk_offset).order_by("pk")


def get_comparable_fields(
    child_doc_class: ESDocumentClassType, field_names: Iterable[str]
) -> set[str]:
    """Pick the fields whose stored values can be compared against a parent's.

    Only string-valued fields are comparable. Dates and numbers are serialized
    into `_source` differently from how they're held on the model, so comparing
    them would report drift that isn't there; deciding that by Elasticsearch
    type rather than by the value in hand also keeps an empty parent field from
    looking like drift against a child's date.

    :param child_doc_class: The child Elasticsearch Document class.
    :param field_names: The Elasticsearch field names to consider.
    :return: The subset of those names that are worth comparing.
    """

    mapping = child_doc_class._doc_type.mapping
    comparable = set()
    for field_name in field_names:
        if field_name in NON_CONTENT_FIELDS:
            continue
        field = mapping.resolve_field(field_name)
        if field is not None and field.name in ("text", "keyword"):
            comparable.add(field_name)
    return comparable


def get_out_of_sync_fields(
    child_source: dict[str, Any],
    expected_fields: dict[str, Any],
    comparable_fields: set[str],
) -> list[str]:
    """Compare one child document against the values its parent should supply.

    :param child_source: The child document's `_source`, as a dict.
    :param expected_fields: Elasticsearch field name to expected value, as
    returned by `get_parent_fields_for_children`.
    :param comparable_fields: The fields to compare, as returned by
    `get_comparable_fields`.
    :return: The names of the fields that disagree with the parent.
    """

    out_of_sync = []
    for field_name, expected_value in expected_fields.items():
        if field_name not in comparable_fields:
            continue
        actual_value = child_source.get(field_name)
        if not isinstance(expected_value, str | None) or not isinstance(
            actual_value, str | None
        ):
            # A keyword field can still hold a non-string, such as a related
            # object's ID.
            continue
        # A missing value and an empty one are the same thing to a user, and to
        # a query: neither puts a term in the index.
        if (expected_value or "") != (actual_value or ""):
            out_of_sync.append(field_name)
    return out_of_sync


def get_drifted_children(
    config: ChildSyncConfig,
    parent_instance: ESModelType,
    comparable_fields: set[str],
    max_children: int,
) -> dict[str, list[str]]:
    """Find the children of one parent that hold stale copies of its fields.

    :param config: The ChildSyncConfig in use.
    :param parent_instance: The parent model instance to compare against.
    :param comparable_fields: The fields to compare, as returned by
    `get_comparable_fields`.
    :param max_children: The most children to inspect for this parent.
    :return: A dict of child document ID to the field names that disagree.
    """

    expected_fields = get_parent_fields_for_children(
        config.parent_doc_class,
        parent_instance,
        config.fields_to_update,
        config.fields_map,
    )
    search = (
        config.child_doc_class.search()
        .query("parent_id", type=config.child_join_type, id=parent_instance.pk)
        .source(list(expected_fields.keys()))
        .extra(size=max_children)
    )
    drifted = {}
    for hit in search.execute():
        out_of_sync = get_out_of_sync_fields(
            hit.to_dict(), expected_fields, comparable_fields
        )
        if out_of_sync:
            drifted[hit.meta.id] = out_of_sync
    return drifted


class Command(VerboseCommand):
    help = (
        "Re-push denormalized parent fields onto child documents in "
        "Elasticsearch, repairing children that the live update path missed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--search-type",
            type=str,
            required=True,
            choices=SUPPORTED_SEARCH_TYPES,
            help=f"The parent/child documents to sync: "
            f"({', '.join(SUPPORTED_SEARCH_TYPES)})",
        )
        parser.add_argument(
            "--pk-offset",
            type=int,
            default=0,
            help="The parent document pk to start from.",
        )
        parser.add_argument(
            "--pk-limit",
            type=int,
            help="Stop after this parent pk. Useful for sampling a range.",
        )
        parser.add_argument(
            "--queue",
            type=str,
            default=settings.CELERY_ETL_TASK_QUEUE,
            help="The celery queue where the tasks should be processed.",
        )
        parser.add_argument(
            "--throttle-min-items",
            type=int,
            default=100,
            help="The minimum number of items to keep in the celery queue.",
        )
        parser.add_argument(
            "--auto-resume",
            action="store_true",
            help="Auto resume the command using the last parent ID logged in "
            "Redis. If --pk-offset is provided, it'll be ignored.",
        )
        parser.add_argument(
            "--report-only",
            action="store_true",
            help="Report how many parents have out-of-sync children without "
            "writing anything. This inspects documents from the command "
            "process rather than from celery, so scope it with --pk-offset "
            "and --pk-limit instead of running it over the whole corpus.",
        )
        parser.add_argument(
            "--max-children-per-parent",
            type=int,
            default=100,
            help="With --report-only, the most children to inspect per parent.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        search_type = options["search_type"]
        pk_offset = options["pk_offset"]
        if options["auto_resume"]:
            pk_offset = get_last_parent_document_id_processed(
                compose_redis_key(search_type)
            )
            self.stdout.write(
                f"Auto-resume enabled, starting from ID: {pk_offset}."
            )

        config = get_sync_config(search_type)
        queryset = get_parent_queryset(search_type, pk_offset)
        if options["pk_limit"]:
            queryset = queryset.filter(pk__lte=options["pk_limit"])

        if options["report_only"]:
            self.report_drift(
                config, queryset, options["max_children_per_parent"]
            )
            return

        self.sync_children(config, queryset, search_type, options)

    def report_drift(
        self,
        config: ChildSyncConfig,
        queryset: QuerySet,
        max_children: int,
    ) -> None:
        """Report parents whose children hold stale copies of their fields.

        :param config: The ChildSyncConfig in use.
        :param queryset: The parents to inspect.
        :param max_children: The most children to inspect per parent.
        :return: None
        """

        expected_field_names = [
            field_name
            for field_names in config.fields_map.values()
            for field_name in field_names
        ]
        comparable_fields = get_comparable_fields(
            config.child_doc_class, expected_field_names
        )
        parents_checked = 0
        parents_drifted = 0
        children_drifted = 0
        drifted_field_counts: dict[str, int] = {}
        for parent_instance in queryset.iterator():
            parents_checked += 1
            drifted = get_drifted_children(
                config, parent_instance, comparable_fields, max_children
            )
            if not drifted:
                continue
            parents_drifted += 1
            children_drifted += len(drifted)
            for field_names in drifted.values():
                for field_name in field_names:
                    drifted_field_counts[field_name] = (
                        drifted_field_counts.get(field_name, 0) + 1
                    )
            logger.info(
                "Parent ID %s has %s out-of-sync children: %s",
                parent_instance.pk,
                len(drifted),
                drifted,
            )

        self.stdout.write(
            f"Checked {parents_checked} parents. {parents_drifted} have "
            f"out-of-sync children ({children_drifted} children total)."
        )
        for field_name, count in sorted(
            drifted_field_counts.items(), key=lambda item: -item[1]
        ):
            self.stdout.write(f"  {field_name}: {count} children")

    def sync_children(
        self,
        config: ChildSyncConfig,
        queryset: QuerySet,
        search_type: str,
        options: dict[str, Any],
    ) -> None:
        """Schedule a parent field update for every parent in the queryset.

        The scheduled task rewrites the child fields unconditionally, so this is
        safe to re-run and safe to interrupt.

        :param config: The ChildSyncConfig in use.
        :param queryset: The parents to process.
        :param search_type: The search type being processed, for the Redis log.
        :param options: The command options.
        :return: None
        """

        queue = options["queue"]
        throttle = CeleryThrottle(
            queue_name=queue, min_items=options["throttle_min_items"]
        )
        processed_count = 0
        parent_pk = None
        for parent_pk in queryset.values_list("pk", flat=True).iterator():
            throttle.maybe_wait()
            update_children_docs_by_query.si(
                config.child_doc_class.__name__,
                parent_pk,
                config.fields_to_update,
                config.fields_map,
            ).set(queue=queue).apply_async()
            processed_count += 1
            if not processed_count % 1000:
                # Log every 1000 parents processed, so --auto-resume can pick
                # up from roughly where an interrupted run stopped.
                log_last_document_indexed(
                    parent_pk, compose_redis_key(search_type)
                )
                self.stdout.write(
                    f"Scheduled {processed_count} parents, last PK: "
                    f"{parent_pk}."
                )

        if parent_pk is not None:
            log_last_document_indexed(
                parent_pk, compose_redis_key(search_type)
            )
        self.stdout.write(
            f"Successfully scheduled {processed_count} parents for child "
            f"document syncing."
        )
