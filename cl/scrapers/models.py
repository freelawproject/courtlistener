from datetime import date

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
        return f"<{self.pk}: Docket {self.docket_id} crawled at {self.date_last_mobile_crawl} with {self.count_last_mobile_crawl} results>"


class Scraper(models.IntegerChoices):
    TEXAS = 1, "Texas"


class AccountSubscription(models.Model):
    scraper = models.IntegerField(
        help_text="The scraper/site the account is for.",
        choices=Scraper.choices,
    )
    email = models.EmailField(
        help_text="The email address for the account.",
    )
    user_name = models.CharField(
        help_text="The username of the account.",
        max_length=30,
    )
    first_subscription = models.DateField(
        help_text="The date of the first subscription.",
        default=date.today,
    )
    last_subscription = models.DateField(
        help_text="The date of the last subscription.",
        default=date.today,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scraper", "user_name"],
                name="unique_scraper_user_name",
            )
        ]

    def include_subscriptions(self, dates: set[date]) -> None:
        """Update first/last subscription to encompass the given dates."""
        all_dates = dates | {self.first_subscription, self.last_subscription}
        self.first_subscription = min(all_dates)
        self.last_subscription = max(all_dates)
        self.save(update_fields=["first_subscription", "last_subscription"])

    def __str__(self) -> str:
        return f"{self.get_scraper_display()}: {self.user_name} ({self.email}): {self.first_subscription or 'Unknown'} - {self.last_subscription or 'current'}"
