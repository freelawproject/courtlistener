from collections import Counter
from datetime import date
from typing import Any

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
    compare_structured_extraction,
    merge_structured_opinion_into_cl_opinion,
)
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.microservice_utils import microservice
from cl.search.cluster_sources import ClusterSources
from cl.search.models import Opinion, OpinionCluster


def get_opinions_to_extract(
    courts: list[str],
    cluster_ids: list[int] | None = None,
    date_filed_gte: date | None = None,
    date_filed_lte: date | None = None,
    limit: int | None = None,
    skip_validation: bool = False,
) -> QuerySet[Opinion]:
    """Find scraped opinions that Centralia's structured extraction can read.

    Only clusters whose only source is a court website scraper, that hold
    exactly one opinion with a stored PDF, are returned. Clusters with
    several opinions are not supported yet. Opinions with anon 2020 content
    are left out too: that field outranks `html` for display and citation
    finding, so the extracted HTML would never be shown, while the opinion's
    curated type and author would still be overwritten.

    :param courts: The court ids to read. Should be a subset of
    CENTRALIA_ENABLED_COURTS. Ignored when `skip_validation` is set.
    :param cluster_ids: If given, only these clusters are considered.
    :param date_filed_gte: If given, only clusters filed on or after it.
    :param date_filed_lte: If given, only clusters filed on or before it.
    :param limit: If given, the maximum number of opinions returned.
    :param skip_validation: Whether to drop the court, source, opinion count
    and anon 2020 filters. Meant for previews and one-off fixes together
    with `cluster_ids`.
    :return: The opinions, with their cluster and docket selected, ordered
    by cluster id. Superseded opinion versions and opinions without a
    stored PDF are always left out.
    """
    clusters = OpinionCluster.objects.all()
    if not skip_validation:
        clusters = (
            clusters.filter(
                docket__court_id__in=courts,
                source=ClusterSources.COURT_WEBSITE,
            )
            .annotate(opinion_count=Count("sub_opinions"))
            .filter(opinion_count=1)
        )
    if cluster_ids:
        clusters = clusters.filter(pk__in=cluster_ids)
    if date_filed_gte:
        clusters = clusters.filter(date_filed__gte=date_filed_gte)
    if date_filed_lte:
        clusters = clusters.filter(date_filed__lte=date_filed_lte)

    # These filters stay even when validation is skipped. Without a PDF there
    # is nothing to send to Doctor. Superseded versions keep their PDF, but
    # their citations were dropped when they were merged into the main
    # version, so extracting them would count those citations again.
    opinions = (
        Opinion.objects.filter(
            cluster_id__in=clusters.values("pk"), main_version__isnull=True
        )
        .exclude(local_path="")
        .select_related("cluster__docket")
        .order_by("cluster_id")
    )
    if not skip_validation:
        opinions = opinions.filter(html_anon_2020="")
    if limit:
        opinions = opinions[:limit]
    return opinions


def extract_structured_opinion(
    opinion: Opinion,
    dry_run: bool = False,
    compare: bool = False,
    queue: str = "batch1",
    skip_validation: bool = False,
) -> dict[str, Any]:
    """Extract an opinion's PDF with Centralia and store the result.

    Sends the opinion's PDF to Doctor's structured opinion endpoint, which
    is backed by Centralia, and saves the first writing's HTML in
    `Opinion.html` along with the opinion's ordering key, type, per curiam
    flag and author string. Each further writing, such as a concurrence or
    dissent, becomes a new opinion in the cluster. Citations in the new
    content are then found by a Celery task.

    The opinion must be its cluster's only one when Centralia finds several
    writings, and the read must pass should_ingest: a "valid" status, no
    scanned, textless or CID-encoded pages, and at least half the text of
    the opinion's current `plain_text`. Anything else is logged and skipped
    without changing the database. See cl.corpus_importer.centralia for the
    details. With `skip_validation`, only writings with HTML are required,
    so a partial or garbled read can replace the opinion's existing content,
    but opinions with text in a field that outranks `html` are still
    skipped.

    Error responses from Doctor are logged and reported in the result. Other
    errors, such as connection errors, timeouts or database errors while
    saving, are raised.

    :param opinion: The opinion to extract, from get_opinions_to_extract.
    :param dry_run: Whether to only call Centralia and run the quality
    checks, without saving anything or finding citations.
    :param compare: Whether to add character and citation count metrics
    comparing the opinion's current content with the extraction. Slow, as it
    runs eyecite on both.
    :param queue: The Celery queue for the citation-finding task.
    :param skip_validation: Whether to skip Centralia's quality checks. It
    also lets Centralia read courts it has not released yet.
    :return: A dict with the "cluster_id", the StructuredExtractionStatus as
    "status", the "reason" for it, the number of "writings" Centralia found
    (0 when Doctor failed), and the "metrics" from
    compare_structured_extraction (empty unless `compare` is set and Doctor
    succeeded).
    """
    result: dict[str, Any] = {
        "cluster_id": opinion.cluster_id,
        "status": StructuredExtractionStatus.ERROR,
        "reason": "",
        "writings": 0,
        "metrics": {},
    }
    court_id = opinion.cluster.docket.court_id
    log_extra = {
        "opinion_cluster_id": opinion.cluster_id,
        "court_id": court_id,
        "local_path": opinion.local_path.name,
        "fingerprint": [f"{court_id}-opinion-extract-structured-failure"],
    }
    with opinion.local_path.open("rb") as document_file:
        response = async_to_sync(microservice)(
            service="opinion-extract-structured",
            file=document_file,
            data={
                "court_id": court_id,
                # Every court outside CENTRALIA_ENABLED_COURTS is pending in
                # Centralia, and only skip_validation lets those through.
                "allow_pending": str(skip_validation).lower(),
            },
        )
    if not response.is_success:
        logger.error(
            "Error from opinion-extract-structured microservice: %s",
            response.status_code,
            extra=log_extra,
        )
        result["reason"] = f"HTTP {response.status_code}"
        return result

    data = response.json()
    if not data.get("success"):
        logger.error(
            "Error from opinion-extract-structured microservice: %s",
            data.get("error_code"),
            extra={**log_extra, "msg": data.get("msg")},
        )
        result["reason"] = f"{data.get('error_code')}: {data.get('msg')}"
        return result

    result["writings"] = len(data.get("opinions") or [])
    if compare:
        # Before merging, which replaces the opinion's current content
        result["metrics"] = compare_structured_extraction(opinion, data)

    if dry_run:
        mergeable, result["reason"] = check_structured_extraction(
            opinion, data, skip_validation=skip_validation
        )
        result["status"] = (
            StructuredExtractionStatus.WOULD_INGEST
            if mergeable
            else StructuredExtractionStatus.SKIPPED
        )
        return result

    opinion_pks, result["reason"] = merge_structured_opinion_into_cl_opinion(
        opinion, data, skip_validation=skip_validation
    )
    if not opinion_pks:
        result["status"] = StructuredExtractionStatus.SKIPPED
        return result

    result["status"] = StructuredExtractionStatus.INGESTED
    find_citations_and_parentheticals_for_opinion_by_pks.si(
        opinion_pks
    ).apply_async(queue=queue)
    return result


class Command(VerboseCommand):
    help = """Run Centralia's structured extraction over scraped opinions.

    Sends the PDF of each matching cluster to Doctor's structured opinion
    endpoint, one at a time, and, when the read passes the quality checks,
    stores its HTML on the cluster's only opinion and queues a task to find
    its citations. When the PDF holds several writings, such as a majority
    and a dissent, each writing after the first becomes a new opinion in
    the cluster. See extract_structured_opinion.

    Only courts in CENTRALIA_ENABLED_COURTS, and clusters whose only source
    is a court website scraper, with exactly one opinion and no anon 2020
    content, are processed.

    --skip-validation lifts those restrictions and the quality checks, for
    previewing Centralia on other courts or on clusters a check would
    decline. It requires --cluster-ids, so it can't be used for bulk runs,
    and is best paired with --dry-run and --compare.

    Use --dry-run with --compare on a small sample first: it calls Centralia
    and reports what would be ingested, with character and citation counts
    for the current and extracted content, without changing the database.

    A cluster that fails, whether from a Doctor error or an exception while
    extracting it, is logged and reported as an error, and the run moves on
    to the next one. The command exits with an error once every cluster is
    processed if any failed.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--courts",
            nargs="+",
            default=sorted(CENTRALIA_ENABLED_COURTS),
            help="The court ids to process. Defaults to every enabled court. "
            "Ignored with --skip-validation, which reads each of the "
            "--cluster-ids from its own court.",
        )
        parser.add_argument(
            "--cluster-ids",
            nargs="+",
            type=int,
            help="Only process these OpinionCluster ids. The other filters "
            "still apply.",
        )
        parser.add_argument(
            "--date-filed-gte",
            type=date.fromisoformat,
            help="Only process clusters filed on or after this YYYY-MM-DD "
            "date.",
        )
        parser.add_argument(
            "--date-filed-lte",
            type=date.fromisoformat,
            help="Only process clusters filed on or before this YYYY-MM-DD "
            "date.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="The maximum number of clusters to process.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Call Centralia and run the quality checks, but do not "
            "save anything or find citations.",
        )
        parser.add_argument(
            "--compare",
            action="store_true",
            default=False,
            help="Report character and citation counts for each cluster's "
            "current content and for the extraction. Slow, as it runs "
            "eyecite on both.",
        )
        parser.add_argument(
            "--skip-validation",
            action="store_true",
            default=False,
            help="Accept any court, drop the source, opinion count and anon "
            "2020 filters, and skip Centralia's quality checks. Lets "
            "Centralia read courts it has not released yet. Requires "
            "--cluster-ids, as it's meant for previews and one-off fixes, "
            "not bulk runs. WARNING: without "
            "the checks, a partial or garbled read can replace an "
            "opinion's existing content, so pair it with --dry-run and "
            "--compare first.",
        )
        parser.add_argument(
            "--queue",
            default="batch1",
            help="The celery queue where the citation-finding tasks should "
            "be processed.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=500,
            help="How many opinions to fetch from the database at a time.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        super().handle(*args, **options)
        if options["limit"] is not None and options["limit"] < 1:
            raise CommandError("--limit must be a positive number.")
        if options["chunk_size"] < 1:
            raise CommandError("--chunk-size must be a positive number.")
        skip_validation = options["skip_validation"]
        if skip_validation and not options["cluster_ids"]:
            raise CommandError("--skip-validation requires --cluster-ids.")
        if not skip_validation and (
            unknown := sorted(
                set(options["courts"]) - set(CENTRALIA_ENABLED_COURTS)
            )
        ):
            raise CommandError(
                f"Courts not in CENTRALIA_ENABLED_COURTS: {unknown}. Use "
                "--skip-validation with --cluster-ids to read them anyway."
            )
        if skip_validation:
            logger.warning(
                "Validation is skipped: a partial or garbled read can "
                "replace existing content."
            )

        opinions = get_opinions_to_extract(
            courts=options["courts"],
            cluster_ids=options["cluster_ids"],
            date_filed_gte=options["date_filed_gte"],
            date_filed_lte=options["date_filed_lte"],
            limit=options["limit"],
            skip_validation=skip_validation,
        )
        results: list[dict[str, Any]] = []
        for opinion in opinions.iterator(chunk_size=options["chunk_size"]):
            try:
                result = extract_structured_opinion(
                    opinion,
                    dry_run=options["dry_run"],
                    compare=options["compare"],
                    queue=options["queue"],
                    skip_validation=skip_validation,
                )
            except Exception as e:
                logger.exception(
                    "Structured extraction failed for cluster %s",
                    opinion.cluster_id,
                )
                result = {
                    "cluster_id": opinion.cluster_id,
                    "status": StructuredExtractionStatus.ERROR,
                    "reason": f"{type(e).__name__}: {e}",
                    "writings": 0,
                    "metrics": {},
                }
            results.append(result)
            logger.info(
                "Cluster %s: %s (%s) %s",
                result["cluster_id"],
                result["status"],
                result["reason"],
                result["metrics"],
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
        """Write the outcome counts and the comparison metrics.

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
        split = sum(
            1
            for r in results
            if r["writings"] > 1
            and r["status"]
            in (
                StructuredExtractionStatus.INGESTED,
                StructuredExtractionStatus.WOULD_INGEST,
            )
        )
        self.stdout.write(f"  split into several opinions: {split}")

        compared = [r for r in results if r["metrics"]]
        if not compared:
            return
        totals = Counter()
        for result in compared:
            totals.update(result["metrics"])
        self.stdout.write(f"Comparison over {len(compared)} cluster(s):")
        for kind in ("chars", "citations"):
            old, new = totals[f"old_{kind}"], totals[f"new_{kind}"]
            ratio = f"{new / old:.1%}" if old else "n/a"
            self.stdout.write(
                f"  {kind}: current {old}, extracted {new} ({ratio})"
            )

        # Fewer citations in the extraction is the clearest sign that a read
        # lost or garbled content, so list those clusters for review.
        fewer_citations = [
            r
            for r in compared
            if r["metrics"]["new_citations"] < r["metrics"]["old_citations"]
        ]
        if fewer_citations:
            self.stdout.write(
                f"Extraction found fewer citations in "
                f"{len(fewer_citations)} cluster(s):"
            )
            for result in fewer_citations:
                metrics = result["metrics"]
                self.stdout.write(
                    f"  cluster {result['cluster_id']} ({result['status']}): "
                    f"{metrics['old_citations']} -> "
                    f"{metrics['new_citations']}"
                )
