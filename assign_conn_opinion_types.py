"""Assign opinion types and unset main_version for merged MULTI_MATCH groups.

For each surviving cluster from the multi-match merging:
1. Query all opinions in the cluster
2. Try to assign opinion types using text heuristics
3. If an opinion gets a type other than COMBINED and points to a
   main_version, set main_version=None (it's a real sub-opinion,
   not a version)

Usage:
    docker exec cl-django python assign_conn_opinion_types.py [--dry-run]
"""

import argparse
import logging
import os
import re
from collections import defaultdict
from itertools import combinations

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cl.settings")

import django

django.setup()

from cl.scrapers.management.commands.merge_opinion_versions import (
    clean_opinion_text,
    get_text_similarity,
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


def main(dry_run: bool = False) -> None:
    for cluster_id in SURVIVING_CLUSTER_IDS:
        if not OpinionCluster.objects.filter(id=cluster_id).exists():
            logger.warning(
                "Cluster %s no longer exists — skipping", cluster_id
            )
            continue

        opinions = Opinion.objects.filter(
            cluster_id=cluster_id
        ).select_related("cluster")

        logger.info("Cluster %s: %d opinions", cluster_id, opinions.count())

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

            if not dry_run:
                opinion.type = op_type
                opinion.save()

        # Second pass: unset main_version for opinions that got a
        # non-COMBINED type (they are real sub-opinions, not versions)
        versioned = opinions.filter(main_version__isnull=False).exclude(
            type=Opinion.COMBINED
        )
        for opinion in versioned:
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

        # Third pass: for opinions of the same type, compare text similarity
        # and assign main_version to create version chains
        # Re-fetch to get updated types
        opinions = list(
            Opinion.objects.filter(cluster_id=cluster_id).select_related(
                "cluster"
            )
        )
        by_type: dict[str, list[Opinion]] = defaultdict(list)
        for opinion in opinions:
            by_type[opinion.type].append(opinion)

        for op_type, ops in by_type.items():
            if len(ops) < 2:
                continue

            # Sort by id desc so newest is first
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
                        "  Opinion %s has no text — skipping",
                        version_op.id,
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
