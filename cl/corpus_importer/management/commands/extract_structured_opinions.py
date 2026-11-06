from collections import Counter
from typing import Any

import httpx
from asgiref.sync import async_to_sync
from django.core.management import CommandError
from django.db.models import Count, QuerySet

from cl.citations.tasks import (
    find_citations_and_parentheticals_for_opinion_by_pks,
)
from cl.corpus_importer.centralia import (
    CENTRALIA_ENABLED_COURTS,
    StructuredExtractionStatus,
    check_structured_extraction,
    merge_structured_opinion_into_cl_opinion,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.microservice_utils import microservice
from cl.search.cluster_sources import ClusterSources
from cl.search.models import Opinion, OpinionCluster


def get_opinions_to_extract(
    courts: list[str],
    cluster_ids: list[int] | None = None,
) -> QuerySet[Opinion]:
    """Find scraped opinions that Centralia's structured extraction can read.

    Only clusters scraped from a court website, that hold exactly one
    opinion with a stored PDF, are returned. Clusters with several opinions
    are not supported yet.

    :param courts: The court ids to read. Should be a subset of
    CENTRALIA_ENABLED_COURTS.
    :param cluster_ids: If given, only these clusters are considered.
    :return: The opinions, with their cluster and docket selected, ordered
    by cluster id.
    """
    clusters = (
        OpinionCluster.objects.filter(
            docket__court_id__in=courts,
            source__contains=ClusterSources.COURT_WEBSITE,
        )
        .annotate(opinion_count=Count("sub_opinions"))
        .filter(opinion_count=1)
    )
    if cluster_ids:
        clusters = clusters.filter(pk__in=cluster_ids)

    return (
        Opinion.objects.filter(cluster_id__in=clusters.values("pk"))
        .exclude(local_path="")
        .select_related("cluster__docket")
        .order_by("cluster_id")
    )


def extract_structured_opinion(
    opinion: Opinion,
    allow_pending: bool = False,
    dry_run: bool = False,
    queue: str = "batch1",
) -> dict[str, Any]:
    """Extract an opinion's PDF with Centralia and store the result.

    Sends the opinion's PDF to Doctor's structured opinion endpoint, which
    is backed by Centralia, and saves the returned HTML in `Opinion.html`
    along with the opinion's ordering key, type, per curiam flag and author
    string. Citations in the new content are then found by a Celery task.

    The opinion must be its cluster's only one. Centralia must also find
    exactly one opinion, and its read must pass should_ingest: a "valid"
    status, no scanned, textless or CID-encoded pages, and at least half the
    text of the opinion's current `plain_text`. Anything else is logged and
    skipped without changing the database. See cl.corpus_importer.centralia
    for the details.

    Doctor errors, including connection errors and timeouts, are logged and
    reported in the result; other errors, including database errors while
    saving, are raised.

    :param opinion: The opinion to extract, from get_opinions_to_extract.
    :param allow_pending: Whether Centralia should read a court it has not
    released yet.
    :param dry_run: Whether to only call Centralia and run the quality
    checks, without saving anything or finding citations.
    :param queue: The Celery queue for the citation-finding task.
    :return: A dict with the "cluster_id", the StructuredExtractionStatus as
    "status" and the "reason" for it.
    """
    result: dict[str, Any] = {
        "cluster_id": opinion.cluster_id,
        "status": StructuredExtractionStatus.ERROR,
        "reason": "",
    }
    court_id = opinion.cluster.docket.court_id
    log_extra = {
        "opinion_cluster_id": opinion.cluster_id,
        "court_id": court_id,
        "local_path": opinion.local_path.name,
        "fingerprint": [f"{court_id}-opinion-extract-structured-failure"],
    }
    try:
        with opinion.local_path.open("rb") as document_file:
            response = async_to_sync(microservice)(
                service="opinion-extract-structured",
                file=document_file,
                data={
                    "court_id": court_id,
                    "allow_pending": str(allow_pending).lower(),
                },
            )
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.error(
            "Could not reach the opinion-extract-structured microservice: %s",
            e,
            extra=log_extra,
        )
        result["reason"] = f"{type(e).__name__}: {e}"
        return result

    data = response.json()
    if not response.is_success or not data.get("success"):
        logger.error(
            "Error from opinion-extract-structured microservice: %s %s",
            response.status_code,
            data.get("error_code"),
            extra={**log_extra, "msg": data.get("msg")},
        )
        result["reason"] = (
            f"HTTP {response.status_code} {data.get('error_code')}: "
            f"{data.get('msg')}"
        )
        return result

    if dry_run:
        mergeable, result["reason"] = check_structured_extraction(
            opinion, data
        )
        result["status"] = (
            StructuredExtractionStatus.WOULD_INGEST
            if mergeable
            else StructuredExtractionStatus.SKIPPED
        )
        return result

    merged, result["reason"] = merge_structured_opinion_into_cl_opinion(
        opinion, data
    )
    if not merged:
        result["status"] = StructuredExtractionStatus.SKIPPED
        return result

    result["status"] = StructuredExtractionStatus.INGESTED
    find_citations_and_parentheticals_for_opinion_by_pks.si(
        [opinion.pk]
    ).apply_async(queue=queue)
    return result


class Command(VerboseCommand):
    help = """Run Centralia's structured extraction over scraped opinions.

    Sends the PDF of each matching cluster to Doctor's structured opinion
    endpoint, one at a time, and, when the read passes the quality checks,
    stores its HTML on the cluster's only opinion and queues a task to find
    its citations. See extract_structured_opinion.

    Only courts in CENTRALIA_ENABLED_COURTS, and clusters scraped from a
    court website with exactly one opinion, are processed.

    Use --dry-run on a small sample first: it calls Centralia and reports
    what would be ingested, without changing the database.

    Doctor errors are reported and make the command exit with an error once
    every cluster is processed. Other errors stop it immediately.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--courts",
            nargs="+",
            choices=sorted(CENTRALIA_ENABLED_COURTS),
            default=sorted(CENTRALIA_ENABLED_COURTS),
            help="The court ids to process. Defaults to every enabled court.",
        )
        parser.add_argument(
            "--cluster-ids",
            nargs="+",
            type=int,
            help="Only process these OpinionCluster ids. The other filters "
            "still apply.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Call Centralia and run the quality checks, but do not "
            "save anything or find citations.",
        )
        parser.add_argument(
            "--allow-pending",
            action="store_true",
            default=False,
            help="Let Centralia read courts it has not released yet.",
        )
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the citation-finding tasks should "
            "be processed.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        super().handle(*args, **options)
        opinions = get_opinions_to_extract(
            courts=options["courts"],
            cluster_ids=options["cluster_ids"],
        )
        results: list[dict[str, Any]] = []
        for opinion in opinions.iterator():
            result = extract_structured_opinion(
                opinion,
                allow_pending=options["allow_pending"],
                dry_run=options["dry_run"],
                queue=options["queue"],
            )
            results.append(result)
            logger.info(
                "Cluster %s: %s (%s)",
                result["cluster_id"],
                result["status"],
                result["reason"],
            )

        self.report(results, options["dry_run"])
        errors = [
            r["cluster_id"]
            for r in results
            if r["status"] == StructuredExtractionStatus.ERROR
        ]
        if errors:
            raise CommandError(
                f"Centralia failed on {len(errors)} cluster(s): {errors}"
            )

    def report(self, results: list[dict[str, Any]], dry_run: bool) -> None:
        """Write the outcome counts.

        :param results: The extract_structured_opinion return values.
        :param dry_run: Whether nothing was saved.
        :return: None
        """
        statuses = Counter(r["status"] for r in results)
        self.stdout.write(
            f"Processed {len(results)} cluster(s)"
            f"{' (dry run, nothing saved)' if dry_run else ''}:"
        )
        for status in StructuredExtractionStatus:
            self.stdout.write(f"  {status}: {statuses[status]}")
