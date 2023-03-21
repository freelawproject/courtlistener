import bz2

from django.db import models
from juriscraper.pacer import PacerRssFeed

from cl.lib.model_helpers import make_path
from cl.lib.models import AbstractDateTimeModel
from cl.lib.pacer import map_cl_to_pacer_id
from cl.lib.storage import S3PrivateUUIDStorage
from cl.search.models import Court


class RssFeedStatus(AbstractDateTimeModel):
    """Keep track of PACER RSS feed parsing.

    We use this class to determine whether we should crawl RSS at a given court
    or if we have done it recently enough not to bother.
    """

    PROCESSING_SUCCESSFUL = 1
    UNCHANGED = 2
    PROCESSING_FAILED = 3
    PROCESSING_IN_PROGRESS = 4
    QUEUED_FOR_RETRY = 5
    PROCESSING_STATUSES = (
        (PROCESSING_SUCCESSFUL, "Feed processed successfully."),
        (UNCHANGED, "Feed unchanged since last visit"),
        (PROCESSING_FAILED, "Feed encountered an error while processing."),
        (PROCESSING_IN_PROGRESS, "Feed is currently being processed."),
        (QUEUED_FOR_RETRY, "Feed failed processing, but will be retried."),
    )
    court = models.ForeignKey(
        Court,
        help_text="The court where the upload was from",
        related_name="rss_feed_statuses",
        on_delete=models.CASCADE,
    )
    date_last_build = models.DateTimeField(
        help_text="The dateLastBuilt field from the feed when it was visited.",
        null=True,
        blank=True,
    )
    status = models.SmallIntegerField(
        help_text="The current status of this feed. Possible values are: %s"
        % ", ".join(["(%s): %s" % (t[0], t[1]) for t in PROCESSING_STATUSES]),
        choices=PROCESSING_STATUSES,
    )
    is_sweep = models.BooleanField(
        help_text="Whether this object is tracking the progress of a sweep or "
        "a partial crawl.",
        default=False,
    )

    class Meta:
        verbose_name_plural = "RSS Feed Statuses"

    def __str__(self) -> str:
        return f"RssFeedStatus: {self.pk}, {self.court_id}"


class RssItemCache(models.Model):
    """A cache for hashes of the RSS models to make it faster to look them up
    and merge them in.
    """

    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    hash = models.CharField(max_length=64, unique=True, db_index=True)


def make_rss_feed_path(instance, filename: str) -> str:
    return make_path("pacer-rss-feeds", filename)


class RssFeedData(AbstractDateTimeModel):
    """Store all old RSS data to disk for future analysis."""

    court = models.ForeignKey(
        Court,
        help_text="The court where the RSS feed was found",
        on_delete=models.RESTRICT,
        related_name="rss_feed_data",
    )
    filepath = models.FileField(
        help_text="The path of the file in the local storage area.",
        upload_to=make_rss_feed_path,
        storage=S3PrivateUUIDStorage(),
        max_length=150,
    )

    @property
    def file_contents(self) -> str:
        return bz2.decompress(self.filepath.read()).decode()

    def print_file_contents(self) -> None:
        print(self.file_contents)

    def reprocess_item(
        self,
        metadata_only: bool = False,
        index: bool = True,
    ) -> None:
        """Reprocess the RSS feed

        :param metadata_only: If True, only do the metadata, not the docket
        entries.
        :param index: Whether to save to Solr (note that none will be sent
        when doing medata only since no entries are modified).
        """
        from cl.recap_rss.tasks import merge_rss_feed_contents
        from cl.search.tasks import add_items_to_solr

        rss_feed = PacerRssFeed(map_cl_to_pacer_id(self.court_id))
        rss_feed._parse_text(self.file_contents)
        response = merge_rss_feed_contents(
            rss_feed.data, self.court_id, metadata_only
        )
        if index:
            add_items_to_solr(
                response.get("rds_for_solr", []), "search.RECAPDocument"
            )
