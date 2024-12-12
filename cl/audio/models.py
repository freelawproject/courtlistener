import pghistory
from django.db import models
from django.urls import reverse
from model_utils import FieldTracker

from cl.lib.model_helpers import make_upload_path
from cl.lib.models import AbstractDateTimeModel, s3_warning_note
from cl.lib.storage import IncrementingAWSMediaStorage
from cl.people_db.models import Person
from cl.search.models import SOURCES, Docket


@pghistory.track()
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


@pghistory.track(
    pghistory.InsertEvent(), pghistory.DeleteEvent(), obj_field=None
)
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
