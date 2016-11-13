from django.db import models

from cl.search.models import Court


class UrlHash(models.Model):
    """A class to hold URLs and the hash of their contents. This could be added
    to the Court table, except that courts often have more than one URL they
    parse.
    """
    id = models.CharField(
        "the ID of the item that is hashed",
        max_length=5000,
        editable=False,
        primary_key=True,
    )
    sha1 = models.CharField(
        "a SHA1 corresponding to the item",
        max_length=40,
        editable=False,
    )

    def __unicode__(self):
        return u"{pk}".format(pk=self.pk)

    class Meta:
        verbose_name_plural = "URL Hashes"


class ErrorLog(models.Model):
    """A class to hold scraper errors. Items are added by the scraper and
    removed by the scraper's status monitor.
    """
    court = models.ForeignKey(
        Court,
        verbose_name='the court where the error occurred'
    )
    log_time = models.DateTimeField(
        'the exact date and time of the error',
        auto_now_add=True,
    )
    log_level = models.CharField(
        'the loglevel of the error encountered',
        max_length=15,
        editable=False
    )
    message = models.TextField(
        'the message produced in the log',
        blank=True,
        editable=False
    )

    def __unicode__(self):
        return u"%s - %s@%s %s" % (self.log_time,
                                   self.log_level,
                                   self.court.pk,
                                   self.message)


class RECAPLog(models.Model):
    """A class to keep track of data coming in from RECAP."""
    SCRAPE_SUCCESSFUL = 1
    SCRAPE_IN_PROGRESS = 2
    SCRAPE_FAILED = 3
    GETTING_CHANGELIST = 4
    CHANGELIST_RECEIVED = 5
    GETTING_AND_MERGING_ITEMS = 6
    ITEMS_MERGED = 7
    EXTRACTING_CONTENTS = 8
    RECAP_STATUSES = (
        (SCRAPE_SUCCESSFUL, "Scrape Completed Successfully"),
        (SCRAPE_IN_PROGRESS, "Scrape currently in progress"),
        (GETTING_CHANGELIST, "Getting list of new content from archive server"),
        (CHANGELIST_RECEIVED, "Successfully got the change list."),
        (GETTING_AND_MERGING_ITEMS, "Getting and merging items from server"),
        (ITEMS_MERGED, "All changes downloaded and merged from server."),
        (EXTRACTING_CONTENTS, "Extracting contents."),
        (SCRAPE_FAILED, "Scrape Failed"),
    )
    date_started = models.DateTimeField(
        help_text="The moment when the scrape of the RECAP content began.",
        auto_now_add=True,
    )
    date_completed = models.DateTimeField(
        help_text="The moment when the scrape of the RECAP content ended.",
        null=True,
        blank=True,
        db_index=True,
    )
    status = models.SmallIntegerField(
        help_text="The current status of the RECAP scrape.",
        choices=RECAP_STATUSES,
    )
