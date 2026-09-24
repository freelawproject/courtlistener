from pathlib import Path
from typing import Any

from django.core.management.base import CommandError, CommandParser
from juriscraper.pacer import PacerRssFeed

from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.pacer import map_cl_to_pacer_id, map_pacer_to_cl_id
from cl.recap_rss.tasks import merge_rss_feed_contents
from cl.search.models import Court


def feed_epoch_ms(filename: str) -> int:
    """Parse the capture time from a '<court>-<epoch_ms>.rss' filename.

    We sort a court's feed files by this value so older captures are merged
    first and docket entries accrete in the order they were published.

    :param filename: The basename of an archived feed file.
    :return: The epoch timestamp in milliseconds, or 0 if it can't be parsed.
    """
    try:
        return int(filename.rsplit("-", 1)[1].split(".")[0])
    except (IndexError, ValueError):
        return 0


class Command(VerboseCommand):
    help = (
        "Ingest a donated archive of historical PACER RSS feed files. The "
        "archive must be laid out as one subdirectory per court: "
        "<root>/<court_id>/<court_id>-<epoch_ms>.rss, where court_id is the "
        "CourtListener court id (e.g. 'cand' or 'akb'). Each file is parsed "
        "and merged through the same pipeline as the live scrape_rss crawler."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--root",
            required=True,
            help="The directory holding the per-court subdirectories.",
        )
        parser.add_argument(
            "--courts",
            type=str,
            default=["all"],
            nargs="*",
            help="The courts that you wish to parse. Defaults to every court "
            "found in --root.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        super().handle(*args, **options)
        root = Path(options["root"])
        if not root.is_dir():
            raise CommandError(f"--root is not a directory: {root}")
        courts = options["courts"]

        # Only ingest directories that name a court we crawl RSS for, using the
        # same court set as the scrape_rss command.
        pacer_court_ids = set(
            Court.federal_courts.all_pacer_courts().values_list(
                "pk", flat=True
            )
        )
        for court_dir in sorted(root.iterdir()):
            # Archive directories are PACER court codes; map the few that
            # differ from the CourtListener id (e.g. cofc -> uscfc, neb ->
            # nebraskab). It's a no-op for the courts whose ids already match.
            court_id = map_pacer_to_cl_id(court_dir.name)
            if not court_dir.is_dir():
                continue
            if courts != ["all"] and court_id not in courts:
                continue
            if court_id not in pacer_court_ids:
                logger.warning("Skipping unknown PACER court: %s", court_id)
                continue
            self.ingest_court(court_dir, court_id)

    def ingest_court(self, court_dir: Path, court_id: str) -> None:
        """Parse and merge every feed file for one court, oldest first.

        :param court_dir: The directory holding the court's .rss files.
        :param court_id: The CourtListener court id.
        :return: None
        """
        pacer_court_id = map_cl_to_pacer_id(court_id)
        paths = sorted(
            court_dir.glob("*.rss"), key=lambda p: feed_epoch_ms(p.name)
        )
        logger.info("%s: %s feed files to merge.", court_id, len(paths))
        merged = empty = errored = 0
        for path in paths:
            rss_feed = PacerRssFeed(pacer_court_id)
            try:
                rss_feed._parse_text(path.read_bytes().decode())
            except Exception as exc:
                # Tolerate the odd malformed or truncated capture and move on.
                logger.error("Unable to parse %s: %s", path, exc)
                errored += 1
                continue
            if not rss_feed.data:
                # An empty capture (some appellate feeds), not an error.
                empty += 1
                continue
            # Merge synchronously, exactly as RssFeedData.reprocess_item() does.
            merge_rss_feed_contents(rss_feed.data, court_id)
            merged += 1
        logger.info(
            "%s: merged %s feeds, skipped %s empty, %s failed to parse.",
            court_id,
            merged,
            empty,
            errored,
        )
