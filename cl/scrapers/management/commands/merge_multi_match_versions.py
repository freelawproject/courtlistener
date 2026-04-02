"""Merge opinion versions for MULTI_MATCH cluster groups from ingestion logs.

Usage:
    docker exec cl-django python manage.py merge_multi_match_versions [--dry-run]
"""

import re
from collections import defaultdict

from django.db.models import QuerySet

from cl.lib.command_utils import VerboseCommand, logger
from cl.scrapers.management.commands.merge_opinion_versions import (
    clean_opinion_text,
    get_text_similarity,
    merge_opinion_versions,
)
from cl.search.models import Opinion, OpinionCluster

# Hardcoded MULTI_MATCH groups from conn-march-31-ingestion-logs.txt
# fmt: off
MULTI_MATCH_GROUPS: list[list[int]] = [
    [4667446, 4668196],
    [4659245, 4659246, 4659247, 4659248, 4660323],
    [4730452, 4730453, 4730881],
    [4769130, 4769794],
    [4803764, 4805171],
    [4805170, 4807978],
    [4765135, 4766638],
    [4765137, 4766639],
    [4807976, 4807977, 4834087],
    [4865800, 4867087],
    [4869436, 4876617],
    [4896219, 4896220, 4898287],
    [4958134, 5043963],
    [4845000, 4845001, 4979141, 4979144],
    [5093422, 5094349],
    [5094350, 5094351, 5095343],
    [5174607, 5287823],
    [5174605, 5287822],
    [5289421, 5289422, 5289478],
    [5293093, 5293106, 5293107],
    [5295008, 5296312],
    [5303447, 5304002],
    [5311080, 5311081, 5312144, 5312145],
    [6247171, 10278653],
    [6246849, 6247182],
    [6246847, 6246848, 6247180, 6247181],
    [6246846, 6247179],
    [6246843, 6247176],
    [6246844, 6247177],
    [6246845, 6247178],
    [6347294, 6347295, 10278652],
    [6347288, 10278651],
    [6353276, 6353277, 10278650],
    [6445225, 6445885, 10278648],
    [6445891, 6445892, 10278649],
    [6447494, 6448588],
    [6455123, 6455124, 6455125, 6456917],
    [6455126, 6455127, 10278647],
    [6456916, 10278646],
    [6470898, 10278645],
    [10278590, 10278592],
    [9357385, 9357386, 9367843, 9367844],
    [9367840, 9367841, 9369857],
    [9368896, 9369856],
    [9369855, 9370808],
    [9376821, 9377251],
    [9370807, 10278661],
    [9373796, 9374108],
    [9373795, 9374107],
    [9374109, 9374638],
    [9385246, 9385247, 9388330],
    [9388329, 9390563],
    [9389713, 9390562],
    [9396311, 9396312, 9398289, 9398290],
    [9398284, 9402600],
    [9406620, 9406621, 9406622, 10278657, 10278658],
    [9439123, 9439124, 9439125],
    [9439115, 9439116, 9439117],
    [9495363, 9497177],
    [10131724, 10143421],
    [10131742, 10144635],
    [10131729, 10131730, 10145150, 10145151],
    [10131740, 10131741, 10160174, 10160175],
    [10131739, 10131937],
    [10131721, 10131936],
    [10131723, 10132289],
    [10131719, 10131720, 10132376, 10132377],
    [10131710, 10131711, 10140975, 10140976],
    [10131713, 10131714, 10131715, 10160251, 10160252, 10160253],
    [10131718, 10162002],
    [10131727, 10131728, 10183717, 10183718, 10185240, 10266509],
    [10131712, 10266508],
    [10131722, 10266507],
    [10131725, 10131726, 10266967, 10266968, 10273954],
    [10131732, 10131733, 10274725, 10274726],
    [10131716, 10131717, 10275825, 10275826],
    [10131731, 10276061],
    [10131736, 10131737, 10131738, 10281331, 10281332, 10286360],
    [10131734, 10131735, 10281329, 10281330],
    [10283159, 10286359],
    [10286358, 10287978],
    [10292984, 10303985],
    [10346730, 10346731, 10352121],
    [10362516, 10362517, 10362518, 10362519, 10364395, 10375070, 10375071, 10375072, 10375073],
    [10380431, 10417565],
    [10626611, 10626612, 10633233],
    [10747443, 10750520],
]
# fmt: on


def parse_multi_match_groups(log_path: str) -> list[list[int]]:
    """Extract cluster ID groups from WARNING MULTI_MATCH log lines.

    :param log_path: path to the log file
    :return: list of cluster ID lists
    """
    pattern = re.compile(
        r"WARNING MULTI_MATCH:.*?matched \d+ clusters: \[([^\]]+)\]"
    )
    groups: list[list[int]] = []
    with open(log_path) as f:
        for line in f:
            if m := pattern.search(line):
                ids = [int(x.strip()) for x in m.group(1).split(",")]
                groups.append(ids)
    return groups


def get_valid_opinions(
    cluster_ids: list[int],
) -> QuerySet[Opinion] | None:
    """Check all clusters exist and return their opinions ordered by -id.

    :param cluster_ids: list of cluster IDs to check
    :return: queryset of opinions or None if any cluster is missing
    """
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
        return None

    return (
        Opinion.objects.filter(cluster_id__in=cluster_ids)
        .select_related("cluster", "cluster__docket")
        .order_by("-id")
    )


class Command(VerboseCommand):
    help = "Merge opinion versions for MULTI_MATCH groups from conn ingestion"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--dry-run",
            default=False,
            action="store_true",
            help="Print what would be done without making changes",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        dry_run = options["dry_run"]

        groups = MULTI_MATCH_GROUPS
        logger.info("Processing %d MULTI_MATCH groups", len(groups))

        stats: dict[str, int] = defaultdict(int)

        for cluster_ids in groups:
            opinions = get_valid_opinions(cluster_ids)
            if opinions is None:
                stats["skipped_missing_clusters"] += 1
                continue

            if not opinions.exists():
                logger.warning(
                    "No opinions found for clusters %s", cluster_ids
                )
                stats["skipped_no_opinions"] += 1
                continue

            case_names = {op.cluster.case_name for op in opinions}
            if len(case_names) > 1:
                logger.warning(
                    "Different case names for clusters %s: %s — skipping",
                    cluster_ids,
                    case_names,
                )
                stats["skipped_different_case_names"] += 1
                continue

            # Most recent opinion ID is the main; merge rest into it
            main_opinion, *versions = list(opinions)
            main_text = clean_opinion_text(main_opinion)
            if not main_text:
                logger.warning(
                    "Main opinion %s has no text — skipping group %s",
                    main_opinion.id,
                    cluster_ids,
                )
                stats["skipped_no_text"] += 1
                continue

            for version in versions:
                if main_opinion.cluster_id == version.cluster_id:
                    stats["skipped_same_cluster"] += 1
                    continue

                version_text = clean_opinion_text(version)
                text_is_strictly_similar, text_is_loosely_similar, ratio1, ratio2 = (
                    get_text_similarity(main_text, version_text)
                )

                if not text_is_strictly_similar and not text_is_loosely_similar:
                    logger.warning(
                        "Text too different for opinions %s (cluster %s) and %s (cluster %s): ratio1=%.4f ratio2=%.4f — skipping",
                        main_opinion.id,
                        main_opinion.cluster_id,
                        version.id,
                        version.cluster_id,
                        ratio1,
                        ratio2,
                    )
                    stats["skipped_text_too_different"] += 1
                    continue

                if text_is_loosely_similar and not text_is_strictly_similar:
                    stats["loose_text_similarity"] += 1

                logger.info(
                    "%sMerging opinion %s (cluster %s) into opinion %s (cluster %s) [ratio1=%.4f ratio2=%.4f]",
                    "[DRY RUN] " if dry_run else "",
                    version.id,
                    version.cluster_id,
                    main_opinion.id,
                    main_opinion.cluster_id,
                    ratio1,
                    ratio2,
                )
                if not dry_run:
                    merge_opinion_versions(main_opinion, version)
                stats["merged"] += 1

        logger.info("Stats: %s", dict(stats))
