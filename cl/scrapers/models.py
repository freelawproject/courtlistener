from django.db import models

from cl.lib.models import AbstractDateTimeModel
from cl.search.models import Court, Docket


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
        "a SHA1 corresponding to the item", max_length=40, editable=False
    )

    def __str__(self) -> str:
        return f"{self.pk}"

    class Meta:
        verbose_name_plural = "URL Hashes"


class ErrorLog(models.Model):
    """A class to hold scraper errors. Items are added by the scraper and
    removed by the scraper's status monitor.
    """

    court = models.ForeignKey(
        Court,
        verbose_name="the court where the error occurred",
        on_delete=models.CASCADE,
    )
    log_time = models.DateTimeField(
        "the exact date and time of the error", auto_now_add=True
    )
    log_level = models.CharField(
        "the loglevel of the error encountered", max_length=15, editable=False
    )
    message = models.TextField(
        "the message produced in the log", blank=True, editable=False
    )

    def __str__(self) -> str:
        return f"{self.log_time} - {self.log_level}@{self.court.pk} {self.message}"


class PACERFreeDocumentLog(models.Model):
    SCRAPE_SUCCESSFUL = 1
    SCRAPE_IN_PROGRESS = 2
    SCRAPE_FAILED = 3
    SCRAPE_STATUSES = (
        (SCRAPE_SUCCESSFUL, "Scrape completed successfully"),
        (SCRAPE_IN_PROGRESS, "Scrape currently in progress"),
        (SCRAPE_FAILED, "Scrape failed"),
    )
    court = models.ForeignKey(
        Court,
        help_text="The court where items were being downloaded from.",
        on_delete=models.CASCADE,
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
    date_queried = models.DateField(
        help_text="The date that was queried.", db_index=True
    )
    status = models.SmallIntegerField(
        help_text="The status of the scrape.", choices=SCRAPE_STATUSES
    )


class PACERFreeDocumentRow(models.Model):
    """Rows from the Free Opinion report table converted to rows in the DB."""

    court_id = models.CharField(max_length=15)
    pacer_case_id = models.CharField(max_length=100)
    docket_number = models.CharField(max_length=5000)
    case_name = models.TextField()
    date_filed = models.DateField()
    pacer_doc_id = models.CharField(max_length=32)
    pacer_seq_no = models.IntegerField(null=True, blank=True)
    document_number = models.CharField(max_length=32)
    description = models.TextField()
    nature_of_suit = models.TextField()
    cause = models.CharField(max_length=2000)
    error_msg = models.TextField()


class PACERMobilePageData(AbstractDateTimeModel):
    """Status information about crawling the PACER Mobile UI for a docket"""

    docket = models.OneToOneField(
        Docket,
        help_text="The docket we are tracking.",
        on_delete=models.CASCADE,
        related_name="mobile_crawl_statuses",
    )
    date_last_mobile_crawl = models.DateTimeField(
        help_text="When the Mobile UI was last crawled",
        db_index=True,
        null=True,
    )
    count_last_mobile_crawl = models.IntegerField(
        help_text="The number of items found during the last crawl",
        null=True,
    )
    count_last_rss_crawl = models.IntegerField(
        help_text="The number of items added from RSS that had a date after "
        "date_last_mobile_crawl",
        default=0,
    )

    def __str__(self) -> str:
        return "<%s: Docket %s crawled at %s with %s results>" % (
            self.pk,
            self.docket_id,
            self.date_last_mobile_crawl,
            self.count_last_mobile_crawl,
        )
