"""Ingest Connecticut Reports opinions into CourtListener.

This script reads the metadata JSON produced by extract_conn_metadata.py,
and for each opinion either:
  1. Matches it to an existing OpinionCluster (by docket number or citation)
     and attaches the PDF + citation if missing.
  2. Creates a new Docket, OpinionCluster, Opinion, and Citation if no match.

After creating/updating Opinion objects, it schedules text extraction
via the doctor microservice (extract_opinion_content).

Usage:
    # Dry run (no writes, just report matches):
    python manage.py shell < ingest_conn_opinions.py -- --dry-run

    # Or more practically, run inside Django shell or with django setup:
    # Set DJANGO_SETTINGS_MODULE=cl.settings, then:
    python ingest_conn_opinions.py \
        --metadata /tmp/conn-opinion-metadata.json \
        --pdf-dir /tmp/conn-reports/conn \
        --dry-run

This script requires Django to be configured. Run it inside the Docker
container or set up Django settings first.
"""

import argparse
import io
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils.encoding import force_bytes

from cl.lib.crypto import sha1
from cl.lib.string_utils import trunc
from cl.scrapers.tasks import extract_opinion_content
from cl.scrapers.utils import (
    get_extension,
    make_citation,
    update_or_create_docket,
)
from cl.search.cluster_sources import ClusterSources
from cl.search.models import (
    Citation,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
)
from cl.scrapers.management.commands.merge_opinion_versions import delete_version_related_objects, remove_document_from_es_index


logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def find_existing_cluster(
    court_id: str,
    docket_number: str,
    citation_str: str,
    date_filed: date,
    case_name: str,
    database: str = "default",
) -> tuple[OpinionCluster | None, str]:
    """Try to match an opinion to an existing OpinionCluster.

    Uses a tiered matching strategy, from most to least specific:
    1. Court + docket number (most reliable for CT)
    2. Court + citation volume/page
    3. Court + date + case name (least reliable, used as fallback)

    :param database: Django database alias to query against.
    :return: Tuple of (matched_cluster, match_type) where match_type is
        "single", "multi", or "none".
    """
    # Parse citation parts up front (used in multiple tiers)
    parts = citation_str.split()
    volume = parts[0] if len(parts) >= 3 else None
    page = parts[-1] if len(parts) >= 3 else None
    reporter = " ".join(parts[1:-1]) if len(parts) >= 3 else None
    cite_dict = dict(
        citations__volume=volume,
        citations__reporter=reporter,
        citations__page=page,
    )

    # Track the best multi-match we've seen (for logging)
    best_multi_match_ids = set()

    # Tier 1: Match by docket number (removing spaces for compatibility)
    docket_number_clean = docket_number.replace(" ", "")
    docket_q = Q(docket__docket_number_raw=docket_number_clean) | Q(
        docket__docket_number_raw=docket_number
    )
    qs = (
        OpinionCluster.objects.using(database)
        .filter(docket__court_id=court_id)
        .filter(docket_q)
    )
    if qs.count() == 1:
        logger.info("Perfect docket number match")
        return qs.first(), "single"

    # Tier 1b: If docket matched multiple, disambiguate with citation
    if qs.count() > 1:
        best_multi_match_ids.union(set(qs.values_list("id", flat=True)))
        if volume:
            qs_narrowed = qs.filter(**cite_dict)
            if qs_narrowed.count() == 1:
                logger.info("Matched docket + citation")
                if best_multi_match_ids:
                    logger.info("Clusters matched in other stages %s", best_multi_match_ids)
                return qs_narrowed.first(), "single"
            
            # Also try narrowing by date
            qs_narrowed = qs.filter(date_filed=date_filed)
            if qs_narrowed.count() == 1:
                logger.info("Matched docket + citation + date_filed")
                if best_multi_match_ids:
                    logger.info("Clusters matched in other stages %s", best_multi_match_ids)
                return qs_narrowed.first(), "single"

    # Tier 1c: Search docket_number field with icontains (catches
    # formatting variations like "SC 16628" vs "SC16628, SC16629")
    if qs.count() != 1:
        qs = (
            OpinionCluster.objects.using(database)
            .filter(docket__court_id=court_id)
            .filter(
                Q(docket__docket_number__icontains=docket_number_clean)
                | Q(docket__docket_number__icontains=docket_number)
            )
        )
        if qs.count() == 1:
            logger.info("Matched by icontains docket number")
            if best_multi_match_ids:
                logger.info("Clusters matched in other stages %s", best_multi_match_ids)
            return qs.first(), "single"
        
        # Disambiguate with citation if multiple
        if qs.count() > 1:
            best_multi_match_ids.union(set(qs.values_list("id", flat=True)))
            if volume:
                qs_narrowed = qs.filter(**cite_dict)
                if qs_narrowed.count() == 1:
                    logger.info("Matched icontains docket + citation. Other matches %s", best_multi_match_ids)
                    if best_multi_match_ids:
                        logger.info("Clusters matched in other stages %s", best_multi_match_ids)

                    return qs_narrowed.first(), "single"

    # Tier 2: Match by citation alone (e.g., "345 Conn. 123")
    if volume:
        qs = OpinionCluster.objects.using(database).filter(docket__court_id=court_id, **cite_dict)
        if qs.count() == 1:
            logger.info("Matched by citation alone")
            if best_multi_match_ids:
                logger.info("Clusters matched in other stages %s", best_multi_match_ids)

            return qs.first(), "single"
        
        if qs.count() > 1:
            best_multi_match_ids.union(set(qs.values_list("id", flat=True)))

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
    if qs.count() == 1:
        logger.info("Matched by loose name + date_filed")
        if best_multi_match_ids:
            logger.info("Clusters matched in other stages %s", best_multi_match_ids)
        return qs.first(), "single"
    
    if qs.count() > 1:
        best_multi_match_ids.union(set(qs.values_list("id", flat=True)))

    # If we found multiple matches but couldn't narrow to one, report it
    if best_multi_match_ids:
        logger.warning(
            "MULTI_MATCH: %s matched %d clusters: %s — skipping to avoid duplicates",
            citation_str,
            len(best_multi_match_ids),
            best_multi_match_ids,
        )
        return None, "multi"

    return None, "none"


@transaction.atomic
def attach_pdf_to_cluster(
    cluster: OpinionCluster,
    pdf_content: bytes,
    citation_str: str,
) -> bool:
    """Add a new opinion version with the PDF to an existing cluster.

    If the cluster already has opinions, creates a new Opinion that
    becomes the main version, and marks the existing opinion as a
    superseded version (via main_version FK). This preserves the
    original opinion rather than overwriting it.

    Also adds the citation if it's not already present.

    :return: True if any changes were made, False otherwise.
    """
    changed = False

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

    # Add citation if not already present
    from cl.scrapers.utils import citation_is_duplicated, make_citation
    citation_candidate = make_citation(citation_str, cluster, "conn")
    if not citation_is_duplicated(citation_candidate, citation_str):
        citation_candidate.save()
        logger.info("Add citation to cluster %s %s", cluster.id, str(candidate_citation))

    # Check if this PDF has already been ingested (by SHA1)
    sha1_hash = sha1(force_bytes(pdf_content))
    if Opinion.objects.filter(sha1=sha1_hash).exists():
        logger.debug("  PDF already ingested (sha1 match)")
        return changed

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

    # Mark existing opinions as versions of the new one
    # (main_version points to the current/main opinion;
    # ordered_opinions filters these out automatically)
    for version_opinion in cluster.sub_opinions.exclude(pk=new_opinion.pk):
        version_opinion.main_version = new_opinion
        version_opinion.html_with_citations = ""
        version_opinion.save()
        delete_version_related_objects(version_opinion)
        
        from cl.search.documents import OpinionDocument, ES_CHILD_ID

        remove_document_from_es_index.delay(
            OpinionDocument.__name__,
            ES_CHILD_ID(version_opinion.id).OPINION,

            # kind of repetitive. The new opinion will be indexed on `extract_opinion_content`
            new_opinion.cluster.id,
        )


    # Schedule text extraction via the doctor microservice
    extract_opinion_content.delay(new_opinion.pk, ocr_available=True)
    changed = True
    logger.info(
        "Created new opinion version %d in cluster %d",
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

    Follows the same pattern as cl_scrape_opinions.make_objects +
    save_everything.

    :return: The newly created OpinionCluster.
    """
    case_name = opinion_data["case_name"]
    date_filed = datetime.strptime(opinion_data["date_filed"][:10], "%Y-%m-%d").date()

    # Create docket
    docket = update_or_create_docket(
        case_name=case_name,
        case_name_short=opinion_data["case_name_short"].strip("."),
        court=court,
        docket_number=opinion_data["docket_number"],
        source=Docket.DIRECT_INPUT,
        from_harvard=False,
    )
    docket.save()

    # Create cluster
    cluster = OpinionCluster(
        docket=docket,
        date_filed=date_filed,
        case_name=case_name,
        case_name_short=opinion_data["case_name_short"].strip("."),
        source=ClusterSources.MANUAL_INPUT,
        precedential_status="Published",
    )
    cluster.save()

    # Create citation
    citation = make_citation(opinion_data["citation"], cluster, court.id)
    if citation:
        citation.cluster_id = cluster.pk
        citation.save()

    # Create opinion with PDF
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

    # Schedule text extraction via the doctor microservice
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

    :param metadata_path: Path to the JSON file from extract_conn_metadata.py.
    :param pdf_dir: Directory containing the downloaded PDFs.
    :param court_id: Court identifier (default: "conn").
    :param dry_run: If True, only report matches without writing anything.
    :param database: Django database alias for read queries (default: "default").
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
        "skipped": 0,
        "multi_match": 0,
    }

    for opinion_data in opinions_data:
        citation_str = opinion_data["citation"]
        date_filed = datetime.strptime(
            opinion_data["date_filed"][:10], "%Y-%m-%d"
        ).date()
        logger.info("Trying to match opinion %s %s", opinion_data["case_name"], opinion_data["docket_number"])
        # Try to find an existing cluster
        cluster, match_type = find_existing_cluster(
            court_id=court_id,
            docket_number=opinion_data["docket_number"],
            citation_str=citation_str,
            date_filed=date_filed,
            case_name=opinion_data["case_name"],
            database=database,
        )

        if match_type == "multi":
            # Multiple matches found but couldn't disambiguate — skip
            # to avoid creating duplicates. Already logged by
            # find_existing_cluster.
            stats["multi_match"] += 1
            continue


        # Load the PDF for this opinion
        source_file = opinion_data.get("source_file")
        if not source_file:
            logger.warning("  No source_file for %s, skipping PDF attachment", citation_str)
            continue

        pdf_path = pdf_dir / source_file
        if not pdf_path.exists():
            logger.warning("  PDF not found: %s", pdf_path)
            continue
        pdf_content = pdf_path.read_bytes()

        if cluster:
            logger.info(
                "MATCH: %s -> cluster %d '%s' %s",
                citation_str,
                cluster.id,
                cluster.case_name,
                cluster.docket.docket_number
            )
            stats["matched"] += 1

            if dry_run:
                continue

            attach_pdf_to_cluster(cluster, pdf_content, citation_str)
        else:
            logger.info("NO MATCH: %s — %s", citation_str, opinion_data["case_name"])

            if dry_run:
                stats["skipped"] += 1
                continue

            try:
                create_new_opinion(court, opinion_data, pdf_content)
                stats["created"] += 1
            except Exception:
                logger.exception(
                    "  Failed to create opinion for %s", citation_str
                )
                stats["failed"] += 1

    logger.info(
        "Done. Matched: %d, Created: %d, Failed: %d, Skipped: %d, Multi-match: %d",
        stats["matched"],
        stats["created"],
        stats["failed"],
        stats["skipped"],
        stats["multi_match"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Connecticut Reports opinions into CourtListener."
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        required=True,
        help="Path to the opinion metadata JSON from extract_conn_metadata.py.",
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        required=True,
        help="Directory containing the downloaded CT Reports PDFs.",
    )
    parser.add_argument(
        "--court-id",
        default="conn",
        help="Court identifier (default: conn).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report matches, don't write anything to the database.",
    )
    parser.add_argument(
        "--database",
        default="default",
        help="Django database alias for read queries (default: 'default'). "
        "Use 'replica' to query against the read replica.",
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