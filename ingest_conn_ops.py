"""Ingest Connecticut Reports opinions into CourtListener.

This script reads the metadata JSON produced by partition_conn_pdfs.py,
and for each opinion either:
  1. Matches it to an existing OpinionCluster (by docket number or citation)
     and attaches the partitioned PDF + citation if missing.
  2. Creates a new Docket, OpinionCluster, Opinion, and Citation if no match.

After creating/updating Opinion objects, it schedules text extraction
via the doctor microservice (extract_opinion_content).

Usage:
    # Inside Docker container with Django configured:
    python ingest_conn_ops.py \
        --metadata /tmp/conn-partitioned-metadata.json \
        --pdf-dir /tmp/conn-partitioned \
        --court-id conn \
        --dry-run

    # Real ingestion:
    python ingest_conn_ops.py \
        --metadata /tmp/conn-partitioned-metadata.json \
        --pdf-dir /tmp/conn-partitioned
"""
import re
import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Django setup — must happen before importing models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cl.settings")

import django

django.setup()

# Suppress verbose SQL debug logging
logging.getLogger("django.db.backends").setLevel(logging.WARNING)

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils.encoding import force_bytes

from cl.lib.crypto import sha1
from cl.lib.string_utils import trunc
from cl.scrapers.management.commands.merge_opinion_versions import (
    delete_version_related_objects,
    merge_metadata,
    update_referencing_objects,
)
from cl.scrapers.tasks import extract_opinion_content
from cl.scrapers.utils import (
    citation_is_duplicated,
    get_extension,
    make_citation,
    update_or_create_docket,
)
from cl.search.cluster_sources import ClusterSources
from cl.search.documents import ES_CHILD_ID, OpinionDocument
from cl.search.models import (
    ClusterRedirection,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
)
from cl.search.tasks import remove_document_from_es_index

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# Max date_filed for Harvard CAP data for conn court
CAP_GAP_START = date(2019, 8, 28)


def find_existing_cluster(
    court_id: str,
    docket_number: str,
    citation_str: str,
    date_filed: date,
    case_name: str,
    database: str = "default",
) -> tuple[OpinionCluster | None, str, list[int]]:
    """Try to match an opinion to an existing OpinionCluster.

    Uses a tiered matching strategy, from most to least specific:
    1. Court + docket number (most reliable for CT)
    2. Court + citation volume/page
    3. Court + date + case name (least reliable, used as fallback)

    :param database: Django database alias to query against.
    :return: Tuple of (matched_cluster, match_type, multi_match_ids).
        match_type is "single", "multi", "consolidation", or "none".
        multi_match_ids contains the cluster IDs for "multi" and
        "consolidation" types.
    """
    # Parse citation parts up front (used in multiple tiers)
    parts = citation_str.split()
    volume = parts[0] if len(parts) >= 3 else None
    page = parts[-1] if len(parts) >= 3 else None
    reporter = " ".join(parts[1:-1]) if len(parts) >= 3 else None
    cite_filter = dict(
        citations__volume=volume,
        citations__reporter=reporter,
        citations__page=page,
    )

    # Track multi-match cluster IDs across tiers (for logging)
    multi_match_ids: set[int] = set()

    def _single_match(
        qs: Q, tier_label: str
    ) -> tuple[OpinionCluster | None, str, list[int]] | None:
        """Return (cluster, "single", []) if qs has exactly 1 result, else None."""
        if qs.count() != 1:
            return None
        cluster = qs.first()
        logger.info(
            "%s: %s %s",
            tier_label,
            cluster.case_name,
            cluster.date_filed,
        )
        if multi_match_ids:
            urls = " ".join(
                f"https://www.courtlistener.com/opinion/{i}/x/"
                for i in multi_match_ids
            )
            logger.info("Clusters matched in other tiers: %s", urls)
        return cluster, "single", []

    # Tier 1: Match by docket_number_raw (exact, with/without spaces)
    docket_number_clean = docket_number.replace(" ", "")
    docket_q = Q(docket__docket_number_raw=docket_number_clean) | Q(
        docket__docket_number_raw=docket_number
    )
    qs = (
        OpinionCluster.objects.using(database)
        .filter(docket__court_id=court_id)
        .filter(docket_q)
    )

    if result := _single_match(qs, "Tier 1 (docket_number_raw)"):
        return result

    # Tier 1b: Multiple docket matches — disambiguate with citation or date
    if qs.count() > 1:
        multi_match_ids.update(qs.values_list("id", flat=True))
        if volume:
            if result := _single_match(
                qs.filter(**cite_filter),
                "Tier 1b (docket_number_raw + citation)",
            ):
                return result
        if result := _single_match(
            qs.filter(date_filed=date_filed),
            "Tier 1b (docket_number_raw + date_filed)",
        ):
            return result

    # Tier 1c: icontains on docket_number (catches formatting variations)
    qs = (
        OpinionCluster.objects.using(database)
        .filter(docket__court_id=court_id)
        .filter(
            Q(docket__docket_number__icontains=docket_number_clean)
            | Q(docket__docket_number__icontains=docket_number)
        )
    )
    if result := _single_match(qs, "Tier 1c (docket_number icontains)"):
        return result

    if qs.count() > 1:
        multi_match_ids.update(qs.values_list("id", flat=True))
        if volume:
            if result := _single_match(
                qs.filter(**cite_filter),
                "Tier 1c (docket icontains + citation)",
            ):
                return result

    # Tier 2: Match by citation alone
    if volume:
        qs = OpinionCluster.objects.using(database).filter(
            docket__court_id=court_id, **cite_filter
        )
        if result := _single_match(qs, "Tier 2 (citation alone)"):
            return result
        if qs.count() > 1:
            multi_match_ids.update(qs.values_list("id", flat=True))

    # Tier 3: Match by date + case name (loose)
    name_prefix = (
        case_name.split(" v. ")[0][:30]
        if " v. " in case_name
        else case_name[:30]
    )
    qs = OpinionCluster.objects.using(database).filter(
        docket__court_id=court_id,
        date_filed=date_filed,
        case_name__icontains=name_prefix,
    )
    if result := _single_match(qs, "Tier 3 (date + case name)"):
        return result
    if qs.count() > 1:
        multi_match_ids.update(qs.values_list("id", flat=True))

    # No single match found
    sorted_ids = sorted(multi_match_ids)
    if not sorted_ids:
        return None, "none", []

    # Check if multi-match looks like sub-opinions needing consolidation
    if len(sorted_ids) == 2 and sorted_ids[1] - sorted_ids[0] == 1:
        logger.info(
            "CONSOLIDATION candidate: %s matched clusters %s",
            citation_str,
            sorted_ids,
        )
        return None, "consolidation", sorted_ids

    logger.warning(
        "MULTI_MATCH: %s matched %d clusters: %s — skipping",
        citation_str,
        len(sorted_ids),
        sorted_ids,
    )
    return None, "multi", sorted_ids


def _load_pdf(pdf_dir: Path, source_file: str | None) -> bytes | None:
    """Load a partitioned opinion PDF from disk.

    :return: PDF bytes, or None if not found.
    """
    if not source_file:
        logger.warning("  No source_file, skipping")
        return None
    pdf_path = pdf_dir / source_file
    if not pdf_path.exists():
        logger.warning("  PDF not found: %s", pdf_path)
        return None
    return pdf_path.read_bytes()


def get_opinion_type_from_name(cluster) -> str:
    """The scraper itself relies on the case name to extract opinion types

    For example "State v. Williams (Concurrence & Dissent)", current cluster 10600944
    """
    clean_text = re.sub(r"[\n\r\t\s]+", " ", cluster.case_name).replace("–", "-").lower()

    is_concurrence = "concur" in clean_text
    is_dissent = "dissent" in clean_text
    is_appendix = "appendix" in clean_text

    if is_concurrence and is_dissent:
        op_type = Opinion.CONCUR_IN_PART
    elif is_concurrence:
        op_type = Opinion.CONCURRENCE
    elif is_dissent:
        op_type = Opinion.DISSENT
    elif is_appendix:
        op_type = Opinion.ADDENDUM
    else:
        op_type = Opinion.LEAD

    logger.info("Cluster %s has been assigned op type %s", cluster.id, op_type)
    return op_type

def get_opinion_type_from_text(opinion:Opinion):
    """

    lead:
    https://www.courtlistener.com/opinion/4675033/X/
    concurrence:
    https://www.courtlistener.com/opinion/4675032/m/
    """

    # focus on the text after the disclaimer
    index = opinion.plain_text[:100].find("****************")
    if index == -1:
        logger.warning("Unexpected versioned file without disclaimer")
        return None
    
    target_text = opinion.plain_text[index:index+1000]

    # Only lead opinions have the sylalbus block
    if "Syllabus" in target_text:
        return Opinion.LEAD
    if "APPENDIX" in target_text:
        return Opinion.ADDENDUM
    
    # account for line breaks
    target_text = re.sub(r"[\n\s-]+", " ", target_text)
    dissent = "DISSENT" in target_text or "dissenting" in target_text
    concurrence = "CONCURRENCE" in target_text or "concurring" in target_text

    if dissent and concurrence:
        return Opinion.CONCUR_IN_PART
    if dissent:
        return Opinion.DISSENT
    if concurrence:
        return Opinion.CONCURRENCE
    
    return None

@transaction.atomic
def consolidate_clusters(
    cluster_ids: list[int],
    database: str = "default",
) -> OpinionCluster:
    """Merge sub-opinion clusters into one, for cases where the court
    website scraped lead/dissent into separate OpinionCluster objects.

    Follows the same pattern as consolidate_opinion_clusters (PR #6814)
    using merge_metadata and update_referencing_objects from
    merge_opinion_versions.

    :param cluster_ids: List of cluster IDs to consolidate (usually 2).
    :param database: Django database alias.
    :return: The surviving cluster.
    """
    clusters = list(
        OpinionCluster.objects.using(database)
        .filter(id__in=cluster_ids)
        .select_related("docket")
        .order_by("id")
    )
    if len(clusters) < 2:
        raise ValueError(
            f"Expected 2+ clusters for consolidation, got {len(clusters)}"
        )

    cluster_to_keep, *clusters_to_delete = clusters

    for cluster in clusters_to_delete:
        op_type = get_opinion_type_from_name(cluster)
        
        if cluster.sub_opinions.all().count() == 1:
            sub_op = cluster.sub_opinions.first()
            sub_op.type = op_type
            sub_op.save()

        if "(" in cluster.case_name:
            cluster.case_name = cluster.case_name.rsplit("(", 1)[0].strip()
            cluster.docket.case_name = cluster.docket.case_name.rsplit("(", 1)[0].strip()
        
        # should only go once into this conditional
        if "(" in cluster_to_keep.case_name:
            cluster_to_keep.case_name = cluster_to_keep.case_name.rsplit("(", 1)[0].strip()
            cluster_to_keep.docket.case_name = cluster_to_keep.docket.case_name.rsplit("(", 1)[0].strip()

        # Merge metadata (case_name, judges, etc.)
        merge_metadata(cluster_to_keep, cluster, error_on_diff=True)

        # Merge docket metadata if they're different docket objects
        if cluster_to_keep.docket_id != cluster.docket_id:
            merge_metadata(
                cluster_to_keep.docket, cluster.docket, error_on_diff=True
            )

    cluster_to_keep.save()
    cluster_to_keep.docket.save()

    # Move sub-opinions from deleted clusters into the surviving cluster
    for cluster in clusters_to_delete:
        for opinion in cluster.sub_opinions.all():
            opinion.cluster = cluster_to_keep
            if opinion.type == Opinion.COMBINED:
                op_type = get_opinion_type_from_text(opinion)
                if op_type:
                    logger.info("Got opinion type %s for op %s", op_type, opinion.id)
                    opinion.type = op_type
            opinion.save()

    # Redirect references and clean up
    for cluster in clusters_to_delete:
        update_referencing_objects(cluster_to_keep, cluster)

        if cluster_to_keep.docket_id != cluster.docket_id:
            update_referencing_objects(
                cluster_to_keep.docket, cluster.docket
            )
            docket_id = cluster.docket_id
            cluster.docket.delete()
            logger.info(
                "  Consolidated: deleted docket %d", docket_id
            )

        ClusterRedirection.create_from_clusters(
            cluster_to_keep=cluster_to_keep,
            cluster_to_delete=cluster,
            reason=ClusterRedirection.CONSOLIDATION,
        )

        cluster_id = cluster.id
        cluster.delete()
        logger.info(
            "  Consolidated: deleted cluster %d into %d",
            cluster_id,
            cluster_to_keep.id,
        )

    return cluster_to_keep


@transaction.atomic
def attach_pdf_to_cluster(
    cluster: OpinionCluster,
    pdf_content: bytes,
    citation_str: str,
    court_id: str,
    dry_run: bool,
) -> bool:
    """Add citation and new opinion version with the PDF to a cluster.

    Creates a new Opinion as the main version and marks existing
    opinions as superseded versions. Cleans up version-related objects
    (citations, parentheticals, ES index) following the same pattern
    as merge_opinion_versions.

    :return: True if any changes were made, False otherwise.
    """
    changed = False

    # Add citation if not already present
    citation_candidate = make_citation(citation_str, cluster, court_id)
    if citation_candidate and not citation_is_duplicated(
        citation_candidate, citation_str
    ):
        if not dry_run:
            citation_candidate.save()
        logger.info(
            "  Added citation %s to cluster %d", citation_str, cluster.id
        )
        changed = True
    else:
        logger.info("  Citation already existed or could not be parsed")

    if dry_run:
        return changed

    # Check if this PDF has already been ingested (by SHA1)
    sha1_hash = sha1(force_bytes(pdf_content))
    if Opinion.objects.filter(sha1=sha1_hash).exists():
        logger.debug("  PDF already ingested (sha1 match)")
        return changed

    # Merge source to reflect this new data origin
    merged_source = ClusterSources.merge_sources(
        cluster.source, ClusterSources.MANUAL_INPUT
    )
    if merged_source != cluster.source:
        cluster.source = merged_source
        cluster.save()
        changed = True
        logger.info(
            "  Updated cluster %d source to %s", cluster.id, merged_source
        )

    # Create a new opinion with the PDF — this becomes the main version
    cf = ContentFile(pdf_content)
    extension = get_extension(pdf_content)
    file_name = trunc(cluster.case_name.lower(), 75) + extension

    new_opinion = Opinion(
        cluster=cluster,
        type=Opinion.COMBINED,
        sha1=sha1_hash,
    )
    new_opinion.file_with_date = cluster.date_filed
    new_opinion.local_path.save(file_name, cf, save=False)
    new_opinion.save()

    # Mark existing opinions as versions and clean up their related objects
    # (adapted from merge_opinion_versions — same cluster, no docket merge)
    for version_opinion in cluster.sub_opinions.exclude(pk=new_opinion.pk):
        version_opinion.main_version = new_opinion
        version_opinion.html_with_citations = ""
        version_opinion.save()
        delete_version_related_objects(version_opinion)

        remove_document_from_es_index.delay(
            OpinionDocument.__name__,
            ES_CHILD_ID(version_opinion.id).OPINION,
            new_opinion.cluster.id,
        )

    # Schedule text extraction via the doctor microservice
    extract_opinion_content.delay(new_opinion.pk, ocr_available=True)
    changed = True
    logger.info(
        "  Created opinion version %d in cluster %d",
        new_opinion.id,
        cluster.id,
    )

    return changed


@transaction.atomic
def create_new_opinion(
    court: Court,
    opinion_data: dict,
    pdf_content: bytes,
) -> OpinionCluster:
    """Create a new Docket, OpinionCluster, Opinion, and Citation.

    :return: The newly created OpinionCluster.
    """
    case_name = opinion_data["case_name"]
    date_filed = datetime.strptime(
        opinion_data["date_filed"][:10], "%Y-%m-%d"
    ).date()

    docket = update_or_create_docket(
        case_name=case_name,
        case_name_short=opinion_data["case_name_short"].strip("."),
        court=court,
        docket_number=opinion_data["docket_number"],
        source=Docket.DIRECT_INPUT,
        from_harvard=False,
    )
    docket.save()

    cluster = OpinionCluster(
        docket=docket,
        date_filed=date_filed,
        case_name=case_name,
        case_name_short=opinion_data["case_name_short"].strip("."),
        source=ClusterSources.MANUAL_INPUT,
        precedential_status="Published",
    )
    cluster.save()

    citation = make_citation(opinion_data["citation"], cluster, court.id)
    if citation:
        citation.save()

    sha1_hash = sha1(force_bytes(pdf_content))
    opinion = Opinion(
        cluster=cluster,
        type=Opinion.COMBINED,
        sha1=sha1_hash,
    )
    cf = ContentFile(pdf_content)
    extension = get_extension(pdf_content)
    file_name = trunc(case_name.lower(), 75) + extension
    opinion.file_with_date = date_filed
    opinion.local_path.save(file_name, cf, save=False)
    opinion.save()

    extract_opinion_content.delay(opinion.pk, ocr_available=True)

    logger.info(
        "  Created cluster %d / opinion %d for %s",
        cluster.id,
        opinion.id,
        opinion_data["citation"],
    )
    return cluster


def ingest_opinions(
    metadata_path: Path,
    pdf_dir: Path,
    court_id: str = "conn",
    dry_run: bool = False,
    database: str = "default",
) -> None:
    """Main ingestion loop.

    :param metadata_path: Path to the JSON file from partition_conn_pdfs.py.
    :param pdf_dir: Directory containing partitioned single-opinion PDFs.
    :param court_id: Court identifier (default: "conn").
    :param dry_run: If True, only report matches and add citations.
    :param database: Django database alias for read queries.
    """
    with open(metadata_path) as f:
        opinions_data = json.load(f)

    court = Court.objects.using(database).get(id=court_id)
    logger.info(
        "Ingesting %d opinions for court %s (dry_run=%s, database=%s)",
        len(opinions_data),
        court_id,
        dry_run,
        database,
    )

    stats = {
        "matched": 0,
        "created": 0,
        "failed": 0,
        "skipped_pre_cap": 0,
        "multi_match": 0,
        "no_match": 0,
        "consolidation": 0,
        "missing_file": 0,
    }

    for opinion_data in opinions_data:
        citation_str = opinion_data["citation"]
        date_filed = datetime.strptime(
            opinion_data["date_filed"][:10], "%Y-%m-%d"
        ).date()

        if date_filed < CAP_GAP_START:
            logger.debug(
                "Skipping %s %s (pre-CAP-gap)", citation_str, date_filed
            )
            stats["skipped_pre_cap"] += 1
            continue

        logger.info(
            "Trying to match %s %s %s",
            opinion_data["case_name"],
            opinion_data["docket_number"],
            opinion_data["date_filed"],
        )

        cluster, match_type, multi_ids = find_existing_cluster(
            court_id=court_id,
            docket_number=opinion_data["docket_number"],
            citation_str=citation_str,
            date_filed=date_filed,
            case_name=opinion_data["case_name"],
            database=database,
        )

        if match_type == "multi":
            stats["multi_match"] += 1
            continue

        if match_type == "consolidation":
            stats["consolidation"] += 1
            if dry_run:
                continue

            try:
                cluster = consolidate_clusters(multi_ids, database)
            except Exception:
                logger.exception(
                    "  Failed to consolidate clusters %s for %s",
                    multi_ids,
                    citation_str,
                )
                stats["failed"] += 1
                continue

        pdf_content = _load_pdf(pdf_dir, opinion_data.get("source_file"))
        if not pdf_content:
            stats["missing_file"] += 1
            continue

        if cluster:
            logger.info(
                "MATCH: %s -> cluster %d '%s' %s",
                citation_str,
                cluster.id,
                cluster.case_name,
                cluster.docket.docket_number,
            )
            stats["matched"] += 1
            attach_pdf_to_cluster(
                cluster, pdf_content, citation_str, court_id, dry_run
            )
        else:
            logger.info(
                "NO MATCH: %s — %s",
                citation_str,
                opinion_data["case_name"],
            )
            stats["no_match"] += 1

            if dry_run:
                continue

            try:
                create_new_opinion(court, opinion_data, pdf_content)
                stats["created"] += 1
            except Exception:
                logger.exception(
                    "  Failed to create opinion for %s", citation_str
                )
                stats["failed"] += 1

    logger.info("Results: %s", stats)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Connecticut Reports opinions into CourtListener."
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        required=True,
        help="Path to the opinion metadata JSON from partition_conn_pdfs.py.",
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        required=True,
        help="Directory containing the partitioned single-opinion PDFs.",
    )
    parser.add_argument(
        "--court-id",
        default="conn",
        help="Court identifier (default: conn).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report matches and add citations, don't upload PDFs.",
    )
    parser.add_argument(
        "--database",
        default="default",
        help="Django database alias for read queries (default: 'default').",
    )
    args = parser.parse_args()

    if args.database != "default" and not args.dry_run:
        logger.error(
            "Cannot use --database=%s without --dry-run. "
            "Writes must go to the default database.",
            args.database,
        )
        sys.exit(1)

    ingest_opinions(
        metadata_path=args.metadata,
        pdf_dir=args.pdf_dir,
        court_id=args.court_id,
        dry_run=args.dry_run,
        database=args.database,
    )


if __name__ == "__main__":
    main()
