import json
from datetime import datetime
from datetime import time

from django.conf import settings
from django.core.urlresolvers import reverse, NoReverseMatch
from django.db import models
from django.template import loader

from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.model_helpers import make_upload_path
from cl.lib.search_index_utils import InvalidDocumentError, null_map, nuke_nones
from cl.lib.storage import IncrementingFileSystemStorage
from cl.lib.utils import deepgetattr
from cl.people_db.models import Person
from cl.search.models import Docket, SOURCES


class Audio(models.Model):
    """A class representing oral arguments and their associated metadata

    """
    STT_NEEDED = 0
    STT_COMPLETE = 1
    STT_FAILED = 2
    STT_STATUSES = (
        (STT_NEEDED, 'Speech to Text Needed'),
        (STT_COMPLETE, 'Speech to Text Complete'),
        (STT_FAILED, 'Speech to Text Failed'),
    )
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
        max_length=10,
        choices=SOURCES,
        blank=True,
    )
    case_name_short = models.TextField(
        help_text="The abridged name of the case, often a single word, e.g. "
                  "'Marsh'",
        blank=True,
    )
    case_name = models.TextField(
        help_text="The full name of the case",
        blank=True,
    )
    case_name_full = models.TextField(
        help_text="The full name of the case",
        blank=True
    )
    panel = models.ManyToManyField(
        Person,
        help_text="The judges that heard the oral arguments",
        related_name="oral_argument_panel_members",
        blank=True,
    )
    judges = models.TextField(
        help_text="The judges that heard the oral arguments as a simple text "
                  "string. This field is used when normalized judges cannot "
                  "be placed into the panel field.",
        blank=True,
        null=True,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified. A value in year"
                  " 1750 indicates the value is unknown",
        auto_now=True,
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
        storage=IncrementingFileSystemStorage(),
        blank=True,
        db_index=True,
    )
    local_path_original_file = models.FileField(
        help_text="The location, relative to MEDIA_ROOT, on the CourtListener "
                  "server, where the original file is stored",
        upload_to=make_upload_path,
        storage=IncrementingFileSystemStorage(),
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
    stt_status = models.SmallIntegerField(
        u"Speech to text status",
        help_text="The status of the Speech to Text for this item?",
        choices=STT_STATUSES,
        default=STT_NEEDED,
    )
    stt_google_response = models.TextField(
        u"Speech to text Google response",
        help_text="The JSON response object returned by Google Speech.",
        blank=True,
    )

    @property
    def transcript(self):
        j = json.loads(self.stt_google_response)
        # Find the alternative with the highest confidence for every utterance
        # in the results.
        best_utterances = []
        for utterance in j['response']['results']:
            best_confidence = 0
            for alt in utterance['alternatives']:
                current_confidence = alt.get('confidence', 0)
                if current_confidence > best_confidence:
                    best_transcript = alt['transcript']
                    best_confidence = current_confidence
            best_utterances.append(best_transcript)
        return ' '.join(best_utterances)

    class Meta:
        ordering = ["-date_created"]
        verbose_name_plural = 'Audio Files'

    def __unicode__(self):
        return u'%s: %s' % (self.pk, self.case_name)

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
            from cl.search.tasks import add_or_update_audio_files
            add_or_update_audio_files.delay([self.pk], force_commit)

    def delete(self, *args, **kwargs):
        """
        Update the index as items are deleted.
        """
        id_cache = self.pk
        super(Audio, self).delete(*args, **kwargs)
        from cl.search.tasks import delete_items
        delete_items.delay([id_cache], settings.SOLR_AUDIO_URL)

    def as_search_dict(self):
        """Create a dict that can be ingested by Solr"""
        # IDs
        out = {
            'id': self.pk,
            'docket_id': self.docket_id,
            'court_id': self.docket.court_id,
        }

        # Docket
        docket = {'docketNumber': self.docket.docket_number}
        if self.docket.date_argued is not None:
            docket['dateArgued'] = datetime.combine(
                self.docket.date_argued,
                time()
            )
        if self.docket.date_reargued is not None:
            docket['dateReargued'] = datetime.combine(
                self.docket.date_reargued,
                time()
            )
        if self.docket.date_reargument_denied is not None:
            docket['dateReargumentDenied'] = datetime.combine(
                self.docket.date_reargument_denied,
                time()
            )
        out.update(docket)

        # Court
        out.update({
            'court': self.docket.court.full_name,
            'court_citation_string': self.docket.court.citation_string,
            'court_exact': self.docket.court_id,  # For faceting
        })

        # Audio File
        out.update({
            'caseName': best_case_name(self),
            'panel_ids': [judge.pk for judge in self.panel.all()],
            'judge': self.judges,
            'file_size_mp3': deepgetattr(self, 'local_path_mp3.size', None),
            'duration': self.duration,
            'source': self.source,
            'download_url': self.download_url,
            'local_path': unicode(getattr(self, 'local_path_mp3', None))
        })
        try:
            out['absolute_url'] = self.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                "Unable to save to index due to missing absolute_url: %s"
                % self.pk
            )

        text_template = loader.get_template('indexes/audio_text.txt')
        out['text'] = text_template.render({'item': self}).translate(null_map)

        return nuke_nones(out)

