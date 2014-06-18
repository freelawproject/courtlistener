from alert.lib.model_helpers import make_upload_path
from alert.search.models import Case, Court
from django.db import models


# Flash is a jerk about only accepting these three rates.
# If an mp3 has a different sample rate, we downgrade it as necessary.

MP3_SAMPLE_RATES = (
    ('low', '11025'),
    ('medium', '22050'),
    ('high', '44100'),
)


class OralArgument(models.Model):
    """A class representing oral arguments and their associated metadata

    """
    case = models.ForeignKey(
        Case,
        help_text="The case that the oral argument is a part of",
        related_name="oral_arguments",
        blank=True,
        null=True
    )
    time_retrieved = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        editable=False,
        db_index=True
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value  in year 1750 indicates the value is unknown",
        auto_now=True,
        editable=False,
        db_index=True,
        null=True,
    )
    date_argued = models.DateField(
        help_text="the date the case was argued",
        blank=True,
        null=True,
    )
    sha1 = models.CharField(
        help_text="unique ID for the document, as generated via SHA1 of the binary file or text data",
        max_length=40,
        db_index=True
    )
    court = models.ForeignKey(
        Court,
        help_text="The court where the document was filed",
        db_index=True,
        null=True,
    )
    download_url = models.URLField(
        help_text="The URL on the court website where the document was originally scraped",
        max_length=500,
        db_index=True,
        null=True,
        blank=True,
    )
    local_path_mp3 = models.FileField(
        help_text="The location, relative to MEDIA_ROOT on the CourtListener server, where files are stored",
        upload_to=make_upload_path,
        blank=True,
        db_index=True,
    )
    length = models.SmallIntegerField(
        help_text="the length of the file, in seconds",
    )

    class Meta:
        ordering = ["-time_retrieved"]
