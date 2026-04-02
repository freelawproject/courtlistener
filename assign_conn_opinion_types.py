"""Assign opinion types and unset main_version for merged MULTI_MATCH groups.

For each surviving cluster from the multi-match merging:
1. Query all opinions in the cluster
2. Try to assign opinion types using text heuristics
3. If an opinion gets a type other than COMBINED and points to a
   main_version, set main_version=None (it's a real sub-opinion,
   not a version)

For "different case names" groups (parenthetical differences only):
1. Strip parentheticals from case names, confirm base names match
2. Assign opinion types from parentheticals before merging
3. Merge clusters via merge_opinion_versions
4. Run type extraction and versioning on the surviving cluster

Usage:
    docker exec cl-django python assign_conn_opinion_types.py [--dry-run]
"""

import argparse
import logging
import os
import re
from collections import defaultdict

from django.db import transaction
from itertools import combinations  # noqa: F401

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cl.settings")

import django

django.setup()

from cl.scrapers.management.commands.merge_opinion_versions import (
    clean_opinion_text,
    get_text_similarity,
    merge_opinion_versions,
)
from cl.search.models import Opinion, OpinionCluster

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def get_opinion_type_from_text(opinion: Opinion) -> str | None:
    """Derive opinion type from the opinion's plain_text content."""
    if not opinion.plain_text:
        return None

    index = opinion.plain_text[500:].find("****************")
    if index == -1:
        return None

    target_text = opinion.plain_text[index : index + 2000]

    if "Syllabus" in target_text or "Procedural History" in target_text:
        return Opinion.LEAD
    if "APPENDIX" in target_text:
        return Opinion.ADDENDUM

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


# Surviving cluster IDs from the multi-match merging (groups with 3+ clusters)
SURVIVING_CLUSTER_IDS: list[int] = [
    4660323,
    4730881,
    4834087,
    4898287,
    4979144,
    5095343,
    5289478,
    5293107,
    5312145,
    6247181,
    10278652,
    10278650,
    10278648,
    10278649,
    6456917,
    10278647,
    9367844,
    9369857,
    9388330,
    9398290,
    9439125,
    9439117,
]

# Groups that were skipped due to different case names (parenthetical only)
# fmt: off
DIFFERENT_CASE_NAME_GROUPS: list[list[int]] = [
    [10278590, 10278592],
    [9406620, 9406621, 9406622, 10278657, 10278658],
    [10131729, 10131730, 10145150, 10145151],
    [10131740, 10131741, 10160174, 10160175],
    [10131719, 10131720, 10132376, 10132377],
    [10131710, 10131711, 10140975, 10140976],
    [10131713, 10131714, 10131715, 10160251, 10160252, 10160253],
    [10131727, 10131728, 10183717, 10183718, 10185240, 10266509],
    [10131725, 10131726, 10266967, 10266968, 10273954],
    [10131732, 10131733, 10274725, 10274726],
    [10131716, 10131717, 10275825, 10275826],
    [10131736, 10131737, 10131738, 10281331, 10281332, 10286360],
    [10131734, 10131735, 10281329, 10281330],
    [10346730, 10346731, 10352121],
]
# fmt: on


def strip_parenthetical(case_name: str) -> str:
    """Remove trailing parenthetical from case name.

    e.g. "State v. Williams (Concurrence & Dissent)" -> "State v. Williams"
    """
    if "(" in case_name:
        return case_name.rsplit("(", 1)[0].strip()
    return case_name


def get_opinion_type_from_name(case_name: str) -> str | None:
    """Derive opinion type from case name parenthetical.

    Returns None if no parenthetical keyword is found, so the caller
    can fall back to text-based detection.

    e.g. "State v. Williams (Concurrence & Dissent)" -> CONCUR_IN_PART
         "Cohen v. Rossi" -> None
    """
    if "(" not in case_name:
        return None

    clean = re.sub(r"[\n\r\t\s]+", " ", case_name).replace("\u2013", "-").lower()

    is_concurrence = "concur" in clean
    is_dissent = "dissent" in clean
    is_appendix = "appendix" in clean

    if is_concurrence and is_dissent:
        return Opinion.CONCUR_IN_PART
    if is_concurrence:
        return Opinion.CONCURRENCE
    if is_dissent:
        return Opinion.DISSENT
    if is_appendix:
        return Opinion.ADDENDUM
    return None


def assign_types_and_version(
    cluster_id: int,
    dry_run: bool,
    opinion_overrides: list[Opinion] | None = None,
) -> None:
    """Assign opinion types from text and set up version chains.

    :param cluster_id: the cluster to process
    :param dry_run: if True, don't save changes
    :param opinion_overrides: if provided, use these opinions instead of
        querying by cluster_id. Useful for dry-run when merges haven't
        happened yet and opinions are still spread across clusters.
    """
    if opinion_overrides is None:
        if not OpinionCluster.objects.filter(id=cluster_id).exists():
            logger.warning(
                "Cluster %s no longer exists — skipping", cluster_id
            )
            return
        opinions = list(
            Opinion.objects.filter(cluster_id=cluster_id).select_related(
                "cluster"
            )
        )
    else:
        opinions = list(opinion_overrides)

    logger.info("Cluster %s: %d opinions", cluster_id, len(opinions))

    for opinion in opinions:
        if opinion.type != Opinion.COMBINED:
            logger.info(
                "  Opinion %s already has type %s",
                opinion.id,
                opinion.type,
            )
            continue

        op_type = get_opinion_type_from_text(opinion)

        if not op_type:
            logger.warning(
                "  Opinion %s: could not determine type from text",
                opinion.id,
            )
            continue

        logger.info(
            "%s  Opinion %s: assigning type %s",
            "[DRY RUN]" if dry_run else "",
            opinion.id,
            op_type,
        )

        # Update in-memory so the versioning pass sees the new type
        opinion.type = op_type
        if not dry_run:
            opinion.save()

    # Unset main_version for opinions that got a non-COMBINED type
    for opinion in opinions:
        if opinion.main_version_id is not None and opinion.type != Opinion.COMBINED:
            logger.info(
                "%s  Opinion %s (type %s): unsetting main_version (was %s)",
                "[DRY RUN]" if dry_run else "",
                opinion.id,
                opinion.type,
                opinion.main_version_id,
            )
            if not dry_run:
                opinion.main_version = None
                opinion.save()

    # For opinions of the same type, compare text similarity
    # and assign main_version to create version chains
    by_type: dict[str, list[Opinion]] = defaultdict(list)
    for opinion in opinions:
        by_type[opinion.type].append(opinion)

    for op_type, ops in by_type.items():
        if len(ops) < 2:
            continue

        ops.sort(key=lambda o: o.id, reverse=True)
        main_op = ops[0]
        main_text = clean_opinion_text(main_op)
        if not main_text:
            logger.warning(
                "  Opinion %s (type %s) has no text — skipping version assignment",
                main_op.id,
                op_type,
            )
            continue

        for version_op in ops[1:]:
            if version_op.main_version_id is not None:
                continue

            version_text = clean_opinion_text(version_op)
            if not version_text:
                logger.warning(
                    "  Opinion %s has no text — skipping", version_op.id
                )
                continue

            strictly, loosely, ratio1, ratio2 = get_text_similarity(
                main_text, version_text
            )

            if strictly or loosely:
                logger.info(
                    "%s  Opinion %s -> main_version %s (type %s) ratio1=%.4f ratio2=%.4f %s",
                    "[DRY RUN]" if dry_run else "",
                    version_op.id,
                    main_op.id,
                    op_type,
                    ratio1,
                    ratio2,
                    "LOOSE" if loosely and not strictly else "",
                )
                if not dry_run:
                    version_op.main_version = main_op
                    version_op.save()
            else:
                logger.warning(
                    "  Opinions %s and %s (type %s) text too different: ratio1=%.4f ratio2=%.4f",
                    main_op.id,
                    version_op.id,
                    op_type,
                    ratio1,
                    ratio2,
                )


def process_different_case_name_groups(dry_run: bool) -> None:
    """Merge clusters that differ only by parenthetical in case name.

    1. Assign opinion types from parentheticals
    2. Clean parentheticals from case names
    3. Merge clusters via merge_opinion_versions
    4. Run type + versioning on the surviving cluster
    """
    for cluster_ids in DIFFERENT_CASE_NAME_GROUPS:
        existing = set(
            OpinionCluster.objects.filter(id__in=cluster_ids).values_list(
                "id", flat=True
            )
        )
        missing = set(cluster_ids) - existing
        if missing:
            logger.warning(
                "Clusters %s no longer exist (from group %s) — skipping",
                missing,
                cluster_ids,
            )
            continue

        clusters = list(
            OpinionCluster.objects.filter(id__in=cluster_ids)
            .select_related("docket")
            .order_by("-id")
        )

        # Verify base names match after stripping parentheticals
        base_names = {strip_parenthetical(c.case_name) for c in clusters}
        if len(base_names) > 1:
            logger.warning(
                "Base case names still differ for clusters %s: %s — skipping",
                cluster_ids,
                base_names,
            )
            continue

        logger.info(
            "Processing different-case-name group %s", cluster_ids
        )

        # Gather all opinions across all clusters for this group
        all_opinions = list(
            Opinion.objects.filter(cluster_id__in=cluster_ids)
            .select_related("cluster", "cluster__docket")
            .order_by("-id")
        )

        # Assign opinion types from parentheticals and clean case names
        for cluster in clusters:
            op_type = get_opinion_type_from_name(cluster.case_name)
            if not op_type:
                # No parenthetical — leave as COMBINED for text-based detection later
                continue
            for opinion in all_opinions:
                if opinion.cluster_id != cluster.id:
                    continue
                if opinion.type == Opinion.COMBINED:
                    logger.info(
                        "%s  Opinion %s: assigning type %s from case name '%s'",
                        "[DRY RUN]" if dry_run else "",
                        opinion.id,
                        op_type,
                        cluster.case_name,
                    )
                    # Update in-memory so dry-run versioning sees the type
                    opinion.type = op_type
                    if not dry_run:
                        opinion.save()

            if "(" in cluster.case_name:
                clean_name = strip_parenthetical(cluster.case_name)
                logger.info(
                    "%s  Cluster %s: cleaning case name '%s' -> '%s'",
                    "[DRY RUN]" if dry_run else "",
                    cluster.id,
                    cluster.case_name,
                    clean_name,
                )
                if not dry_run:
                    cluster.case_name = clean_name
                    cluster.save()
                    cluster.docket.case_name = strip_parenthetical(
                        cluster.docket.case_name
                    )
                    cluster.docket.save()

        main_cluster = clusters[0]

        with transaction.atomic():
            # Merge all clusters into the one with the highest id
            main_opinion = (
                Opinion.objects.filter(cluster_id=main_cluster.id)
                .order_by("-id")
                .first()
            )
            if not main_opinion:
                logger.warning(
                    "No opinions in main cluster %s — skipping",
                    main_cluster.id,
                )
                continue

            for cluster in clusters[1:]:
                version_opinion = (
                    Opinion.objects.filter(cluster_id=cluster.id)
                    .select_related("cluster", "cluster__docket")
                    .order_by("-id")
                    .first()
                )
                if not version_opinion:
                    continue

                # Reload main_opinion to get fresh state
                main_opinion = (
                    Opinion.objects.filter(id=main_opinion.id)
                    .select_related("cluster", "cluster__docket")
                    .first()
                )

                logger.info(
                    "%sMerging opinion %s (cluster %s) into opinion %s (cluster %s)",
                    "[DRY RUN] " if dry_run else "",
                    version_opinion.id,
                    version_opinion.cluster_id,
                    main_opinion.id,
                    main_opinion.cluster_id,
                )
                if not dry_run:
                    merge_opinion_versions(main_opinion, version_opinion)

        # Run type extraction + versioning on the surviving cluster
        # In dry-run: pass in-memory opinions (merges didn't happen)
        # In real run: re-fetch from DB to get fresh state after merges
        if dry_run:
            assign_types_and_version(main_cluster.id, dry_run, all_opinions)
        else:
            assign_types_and_version(main_cluster.id, dry_run)


def main(dry_run: bool = True) -> None:
    # Part 1: Already-merged clusters — assign types and version
    logger.info("=== Processing already-merged clusters ===")
    SURVIVING_CLUSTER_IDS = []
    for cluster_id in SURVIVING_CLUSTER_IDS:
        assign_types_and_version(cluster_id, dry_run)

    # Part 2: Different case name groups — merge, assign types, version
    logger.info("=== Processing different-case-name groups ===")
    process_different_case_name_groups(dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        default=False,
        action="store_true",
        help="Print what would be done without making changes",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
