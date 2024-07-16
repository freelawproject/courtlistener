from typing import Dict, List, Union

import pghistory
from django.db import models
from django.template import loader
from django.urls import NoReverseMatch, reverse
from model_utils import FieldTracker

from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.date_time import midnight_pt
from cl.lib.model_helpers import make_upload_path
from cl.lib.models import AbstractDateTimeModel, s3_warning_note
from cl.lib.pghistory import AfterUpdateOrDeleteSnapshot
from cl.lib.search_index_utils import (
    InvalidDocumentError,
    normalize_search_dicts,
    null_map,
)
from cl.lib.storage import IncrementingAWSMediaStorage
from cl.lib.utils import deepgetattr
from cl.people_db.models import Person
from cl.search.models import SOURCES, Docket


@pghistory.track(AfterUpdateOrDeleteSnapshot())
class Audio(AbstractDateTimeModel):
    """A class representing oral arguments and their associated metadata"""

    STT_NEEDED = 0
    STT_COMPLETE = 1
    STT_FAILED = 2
    STT_HALLUCINATION = 3
    STT_FILE_TOO_BIG = 4
    STT_NO_FILE = 5
    STT_STATUSES = (
        (STT_NEEDED, "Speech to Text Needed"),
        (STT_COMPLETE, "Speech to Text Complete"),
        (STT_FAILED, "Speech to Text Failed"),
        (STT_HALLUCINATION, "Transcription does not match audio"),
        (STT_FILE_TOO_BIG, "File size is bigger than 25 MB"),
        (STT_NO_FILE, "File does not exist"),
    )
    STT_OPENAI_WHISPER = 1
    STT_SELF_HOSTED_WHISPER = 2
    STT_SOURCES = [
        (STT_OPENAI_WHISPER, "OpenAI API's whisper-1 model"),
        (STT_SELF_HOSTED_WHISPER, "Self hosted Whisper model"),
    ]

    # Annotation required b/c this FK is nullable, which breaks absolute_url
    docket: Docket = models.ForeignKey(
        Docket,
        help_text="The docket that the oral argument is a part of",
        related_name="audio_files",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    source = models.CharField(
        help_text="the source of the audio file, one of: %s"
        % ", ".join(f"{t[0]} ({t[1]})" for t in SOURCES.NAMES),
        max_length=10,
        choices=SOURCES.NAMES,
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
        help_text="The full name of the case", blank=True
    )
    panel = models.ManyToManyField(  # type: ignore[var-annotated]
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
        help_text="The location in AWS S3 where our enhanced copy of the "
        f"original audio file is stored. {s3_warning_note}",
        upload_to=make_upload_path,
        storage=IncrementingAWSMediaStorage(),
        blank=True,
        db_index=True,
    )
    local_path_original_file = models.FileField(
        help_text="The location in AWS S3 where the original audio file "
        f"downloaded from the court is stored. {s3_warning_note}",
        upload_to=make_upload_path,
        storage=IncrementingAWSMediaStorage(),
        db_index=True,
    )
    filepath_ia = models.CharField(
        help_text="The URL of the file in IA",
        max_length=1000,
        blank=True,
    )
    ia_upload_failure_count = models.SmallIntegerField(
        help_text="Number of times the upload to the Internet Archive failed.",
        null=True,
        blank=True,
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
        "Speech to text status",
        help_text="The status of the Speech to Text for this item?",
        choices=STT_STATUSES,
        default=STT_NEEDED,
    )
    stt_source = models.SmallIntegerField(
        "Speech to text source",
        help_text="Source used to get the transcription",
        choices=STT_SOURCES,
        blank=True,
        null=True,
    )
    stt_transcript = models.TextField(
        "Speech to text transcription",
        help_text="Speech to text transcription",
        blank=True,
    )

    es_oa_field_tracker = FieldTracker(
        fields=[
            "case_name",
            "case_name_short",
            "case_name_full",
            "duration",
            "download_url",
            "local_path_mp3",
            "judges",
            "sha1",
            "source",
            "stt_transcript",
            "docket_id",
        ]
    )

    @property
    def transcript(self) -> str:
        return self.stt_transcript

    class Meta:
        ordering = ["-date_created"]
        verbose_name_plural = "Audio Files"

    def __str__(self) -> str:
        return f"{self.pk}: {self.case_name}"

    def get_absolute_url(self) -> str:
        return reverse("view_audio_file", args=[self.pk, self.docket.slug])

    def save(  # type: ignore[override]
        self,
        index: bool = True,
        force_commit: bool = False,
        *args: List,
        **kwargs: Dict,
    ) -> None:
        """
        Overrides the normal save method, but provides integration with the
        bulk files and with Solr indexing.

        :param index: Should the item be added to the Solr index?
        :param force_commit: Should a commit be performed in solr after
        indexing it?
        """
        super().save(*args, **kwargs)  # type: ignore
        if index:
            from cl.search.tasks import add_items_to_solr

            add_items_to_solr([self.pk], "audio.Audio", force_commit)

    def delete(  # type: ignore[override]
        self,
        *args: List,
        **kwargs: Dict,
    ) -> None:
        """
        Update the index as items are deleted.
        """
        id_cache = self.pk
        super().delete(*args, **kwargs)  # type: ignore
        from cl.search.tasks import delete_items

        delete_items.delay([id_cache], "audio.Audio")

    def as_search_dict(self) -> Dict[str, Union[int, List[int], str]]:
        """Create a dict that can be ingested by Solr"""
        # IDs
        out = {
            "id": self.pk,
            "docket_id": self.docket_id,
            "court_id": self.docket.court_id,
        }

        # Docket
        docket = {"docketNumber": self.docket.docket_number}
        if self.docket.date_argued is not None:
            docket["dateArgued"] = midnight_pt(self.docket.date_argued)
        if self.docket.date_reargued is not None:
            docket["dateReargued"] = midnight_pt(self.docket.date_reargued)
        if self.docket.date_reargument_denied is not None:
            docket["dateReargumentDenied"] = midnight_pt(
                self.docket.date_reargument_denied
            )
        out.update(docket)

        # Court
        out.update(
            {
                "court": self.docket.court.full_name,
                "court_citation_string": self.docket.court.citation_string,
                "court_exact": self.docket.court_id,  # For faceting
            }
        )

        # Audio File
        out.update(
            {
                "caseName": best_case_name(self),
                "panel_ids": [judge.pk for judge in self.panel.all()],
                "judge": self.judges,
                "file_size_mp3": deepgetattr(
                    self, "local_path_mp3.size", None
                ),
                "duration": self.duration,
                "source": self.source,
                "download_url": self.download_url,
                "local_path": deepgetattr(self, "local_path_mp3.name", None),
            }
        )
        try:
            out["absolute_url"] = self.get_absolute_url()
        except NoReverseMatch:
            raise InvalidDocumentError(
                f"Unable to save to index due to missing absolute_url: {self.pk}"
            )

        text_template = loader.get_template("indexes/audio_text.txt")
        out["text"] = text_template.render({"item": self}).translate(null_map)

        return normalize_search_dicts(out)


@pghistory.track(AfterUpdateOrDeleteSnapshot(), obj_field=None)
class AudioPanel(Audio.panel.through):  # type: ignore
    """A model class to track audio panel m2m relation"""

    class Meta:
        proxy = True


class AudioTranscriptionMetadata(models.Model):
    audio = models.ForeignKey(Audio, on_delete=models.DO_NOTHING)
    metadata = models.JSONField(
        help_text="Word and/or segment level metadata returned by a STT model."
        " May be used for diarization. Contains start and end timestamps for "
        "segments and words, probabilities and other model outputs"
    )
