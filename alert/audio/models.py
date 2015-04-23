from django.conf import settings
from django.core.urlresolvers import reverse
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
        null=True,
    )
    source = models.CharField(
        help_text="the source of the audio file, one of: %s" %
                  ', '.join(['%s (%s)' % (t[0], t[1]) for t in SOURCES]),
        max_length=3,
        choices=SOURCES,
        blank=True,
    )
    case_name = models.TextField(
        help_text="The full name of the case",
        blank=True,
    )
    judges = models.TextField(
        help_text="The judges that brought the opinion as a simple text "
                  "string",
        blank=True,
        null=True,
    )
    time_retrieved = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        editable=False,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in year"
                  " 1750 indicates the value is unknown",
        auto_now=True,
        editable=False,
        db_index=True,
    )
    sha1 = models.CharField(
        help_text="unique ID for the document, as generated via SHA1 of the "
                  "binary file or text data",
        max_length=40,
        db_index=True,
    )
    download_url = models.URLField(
        help_text="The URL on the court website where the document was "
                  "originally scraped",
        max_length=500,
        db_index=True,
        null=True,
        blank=True,
    )
    local_path_mp3 = models.FileField(
        help_text="The location, relative to MEDIA_ROOT, on the CourtListener "
                  "server, where encoded file is stored",
        upload_to=make_upload_path,
        blank=True,
        db_index=True,
    )
    local_path_original_file = models.FileField(
        help_text="The location, relative to MEDIA_ROOT, on the CourtListener "
                  "server, where the original file is stored",
        upload_to=make_upload_path,
        db_index=True,
    )
    duration = models.SmallIntegerField(
        help_text="the length of the item, in seconds",
        null=True,
    )
    processing_complete = models.BooleanField(
        help_text="Is audio for this item done processing?",
        default=False,
    )
    date_blocked = models.DateField(
        help_text="The date that this opinion was blocked from indexing by "
                  "search engines",
        blank=True,
        null=True,
        db_index=True,
    )
    blocked = models.BooleanField(
        help_text="Should this item be blocked from indexing by "
                  "search engines?",
        db_index=True,
        default=False,
    )

    class Meta:
        ordering = ["-time_retrieved"]
        verbose_name_plural = 'Audio Files'

    def __unicode__(self):
        return '%s: %s' % (self.pk, self.case_name)

    def get_absolute_url(self):
        return reverse('view_audio_file', args=[self.pk, self.docket.slug])

    def save(self, index=True, force_commit=False, *args, **kwargs):
        """
        Overrides the normal save method, but provides integration with the
        bulk files and with Solr indexing.

        :param index: Should the item be added to the Solr index?
        :param commit: Should a commit be performed after adding it?
        """
        super(Audio, self).save(*args, **kwargs)
        if index:
            from search.tasks import add_or_update_audio_file
            add_or_update_audio_file.delay(self.pk, force_commit)

    def delete(self, *args, **kwargs):
        """
        Update the index as items are deleted.
        """
        id_cache = self.pk
        super(Audio, self).delete(*args, **kwargs)
        from search.tasks import delete_item
        delete_item.delay(id_cache, settings.SOLR_AUDIO_URL)
