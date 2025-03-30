import pghistory
from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator
from django.db import models
from django.utils import timezone

from cl.audio.models import Audio
from cl.lib.models import AbstractDateTimeModel
from cl.search.models import Docket, OpinionCluster, RECAPDocument


@pghistory.track()
class Note(models.Model):
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        auto_now=True, db_index=True, null=True
    )
    user = models.ForeignKey(
        User,
        help_text="The user that owns the note",
        related_name="notes",
        on_delete=models.CASCADE,
    )
    cluster_id = models.ForeignKey(
        OpinionCluster,
        verbose_name="the opinion cluster that is saved",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    audio_id = models.ForeignKey(
        Audio,
        verbose_name="the audio file that is saved",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    docket_id = models.ForeignKey(
        Docket,
        verbose_name="the docket that is saved",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    recap_doc_id = models.ForeignKey(
        RECAPDocument,
        verbose_name="the RECAP document that is saved",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    name = models.CharField("a name for the alert", max_length=100)
    notes = models.TextField(
        "notes about the item saved",
        validators=[MaxLengthValidator(500)],
        max_length=500,
        blank=True,
    )

    class Meta:
        unique_together = (
            ("cluster_id", "user"),
            ("audio_id", "user"),
            ("docket_id", "user"),
            ("recap_doc_id", "user"),
        )


@pghistory.track()
class DocketTag(models.Model):
    """Through table linking dockets to tags"""

    docket = models.ForeignKey(
        Docket, related_name="docket_tags", on_delete=models.CASCADE
    )
    tag = models.ForeignKey(
        "favorites.UserTag",
        related_name="docket_tags",
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = (("docket", "tag"),)


@pghistory.track(
    pghistory.UpdateEvent(
        condition=pghistory.AnyChange(exclude_auto=True), row=pghistory.Old
    ),
    pghistory.DeleteEvent(),
    exclude=["view_count"],
)
class UserTag(AbstractDateTimeModel):
    """Tags that can be added by users to various objects"""

    user = models.ForeignKey(
        User,
        help_text="The user that created the tag",
        related_name="user_tags",
        on_delete=models.CASCADE,
    )
    dockets = models.ManyToManyField(
        Docket,
        help_text="Dockets that are tagged with by this item",
        related_name="user_tags",
        through=DocketTag,
        blank=True,
    )
    name = models.SlugField(
        help_text="The name of the tag", max_length=50, db_index=True
    )
    title = models.TextField(help_text="A title for the tag", blank=True)
    description = models.TextField(
        help_text="The description of the tag in Markdown format", blank=True
    )
    view_count = models.IntegerField(
        help_text="The number of times the URL for the tag has been seen.",
        db_index=True,
        default=0,
    )
    published = models.BooleanField(
        help_text="Whether the tag has been shared publicly.",
        db_index=True,
        default=False,
    )

    def __str__(self) -> str:
        return f"{self.pk}: {self.name} by user {self.user_id}"

    class Meta:
        unique_together = (("user", "name"),)
        indexes = [
            models.Index(
                fields=["user", "name"],
                name="favorites_usertag_user_id_name_54aef6fe_idx",
            )
        ]


@pghistory.track()
class Prayer(models.Model):
    WAITING = 1
    GRANTED = 2
    STATUSES = (
        (WAITING, "Still waiting for the document."),
        (GRANTED, "Prayer has been granted."),
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    user = models.ForeignKey(
        User,
        help_text="The user that made the prayer",
        related_name="prayers",
        on_delete=models.CASCADE,
    )
    recap_document = models.ForeignKey(
        RECAPDocument,
        help_text="The document you're praying for.",
        related_name="prayers",
        on_delete=models.CASCADE,
    )
    status = models.SmallIntegerField(
        help_text="Whether the prayer has been granted or is still waiting.",
        choices=STATUSES,
        default=WAITING,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "recap_document"],
                name="unique_prayer_for_user_document",
            ),
        ]
        indexes = [
            # When adding a new document to RECAP, we'll ask: What outstanding
            # prayers do we have for this document?
            # When loading the prayer leader board, we'll ask: Which documents
            # have the most outstanding prayers?
            models.Index(
                fields=["recap_document", "status"],
                name="favorites_prayer_recap_document_id_status_82e2dbbb_idx",
            ),
            # When loading docket pages, we'll ask (hundreds of times): Did
            # user ABC pray for document XYZ?
            models.Index(
                fields=["recap_document", "user"],
                name="favorites_prayer_recap_document_id_user_id_c5d30108_idx",
            ),
            # When a user votes, we'll ask: How many outstanding prayers did
            # user ABC make today?
            models.Index(
                fields=["date_created", "user", "status"],
                name="favorites_prayer_date_created_user_id_status_880d7280_idx",
            ),
        ]


# model to keep track of when we last checked whether a given PACER document was still unavailable for purchase
class PrayerAvailability(models.Model):
    recap_document = models.ForeignKey(
        RECAPDocument,
        help_text="The document people prayed for.",
        related_name="prayeravailability",
        on_delete=models.CASCADE,
    )
    last_checked = models.DateTimeField(
        help_text="The time when the availability of this document was last checked.",
        default=timezone.now,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recap_document"],
                name="unique_recap_document",
                include=["last_checked"],
            ),
        ]
