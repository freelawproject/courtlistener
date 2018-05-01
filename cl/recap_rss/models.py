from django.db import models

from cl.search.models import Court


class RssFeedStatus(models.Model):
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
        (PROCESSING_SUCCESSFUL, 'Feed processed successfully.'),
        (UNCHANGED, "Feed unchanged since last visit"),
        (PROCESSING_FAILED, 'Feed encountered an error while processing.'),
        (PROCESSING_IN_PROGRESS, 'Feed is currently being processed.'),
        (QUEUED_FOR_RETRY, 'Feed failed processing, but will be retried.'),
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    court = models.ForeignKey(
        Court,
        help_text="The court where the upload was from",
        related_name='rss_feed_statuses',
    )
    date_last_build = models.DateTimeField(
        help_text="The dateLastBuilt field from the feed when it was visited.",
        null=True,
        blank=True,
    )
    status = models.SmallIntegerField(
        help_text="The current status of this feed. Possible values are: %s" %
                  ', '.join(['(%s): %s' % (t[0], t[1]) for t in
                             PROCESSING_STATUSES]),
        choices=PROCESSING_STATUSES,
        db_index=True,
    )
    is_sweep = models.BooleanField(
        help_text="Whether this object is tracking the progress of a sweep or "
                  "a partial crawl.",
        default=False,
    )

    class Meta:
        verbose_name_plural = 'RSS Feed Statuses'

    def __unicode__(self):
        return u'RssFeedStatus: %s, %s' % (self.pk, self.court_id)
