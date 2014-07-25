from alert.lib.model_helpers import make_upload_path
from alert.search.models import Docket, SOURCES
from django.db import models


class Audio(models.Model):
    """A class representing oral arguments and their associated metadata

    """
    docket = models.ForeignKey(
        Docket,
        help_text="The docket that the oral argument is a part of",
        related_name="audio_files",
        blank=True,
        null=True
    )
    source = models.CharField(
        help_text="the source of the audio file, one of: %s" % ', '.join(['%s (%s)' % (t[0], t[1]) for t in SOURCES]),
        max_length=3,
        choices=SOURCES,
        blank=True
    )
    case_name = models.TextField(
        help_text="The full name of the case",
        blank=True
    )
    docket_number = models.CharField(
        help_text="The docket numbers of a case, can be consolidated and quite long",
        max_length=5000,  # sometimes these are consolidated, hence they need to be long (was 50, 100, 300, 1000).
        blank=True,
        null=True
    )
    judges = models.TextField(
        help_text="The judges that brought the opinion as a simple text string",
        blank=True,
        null=True,
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
    )
    date_argued = models.DateField(
        help_text="the date the case was argued",
        blank=True,
        null=True,
        db_index=True,
    )
    sha1 = models.CharField(
        help_text="unique ID for the document, as generated via SHA1 of the binary file or text data",
        max_length=40,
        db_index=True
    )
    download_url = models.URLField(
        help_text="The URL on the court website where the document was originally scraped",
        max_length=500,
        db_index=True,
        null=True,
        blank=True,
    )
    local_path_mp3 = models.FileField(
        help_text="The location, relative to MEDIA_ROOT, on the CourtListener server, where encoded file is stored",
        upload_to=make_upload_path,
        blank=True,
        db_index=True,
    )
    local_path_original_file = models.FileField(
        help_text="The location, relative to MEDIA_ROOT, on the CourtListener server, where the original file is stored",
        upload_to=make_upload_path,
        db_index=True,
    )
    length = models.SmallIntegerField(
        help_text="the length of the file, in seconds",
        null=True,
    )
    date_blocked = models.DateField(
        help_text="The date that this opinion was blocked from indexing by search engines",
        blank=True,
        null=True,
        db_index=True,
    )
    blocked = models.BooleanField(
        help_text="Whether a document should be blocked from indexing by search engines",
        db_index=True,
        default=False
    )

    class Meta:
        ordering = ["-time_retrieved"]
        verbose_name_plural = 'Audio Files'
