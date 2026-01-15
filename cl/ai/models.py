from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from cl.lib.model_helpers import make_path
from cl.lib.models import AbstractDateTimeModel
from cl.lib.storage import IncrementingAWSMediaStorage


def make_input_file_path(instance: "LLMTask", filename: str) -> str:
    """
    Creates a date-based path for the input file, ensuring the filename is
    unique by prepending the task's primary key.

    Example:
    llm-tasks/2026/01/15/101-scan_file.pdf
    """
    unique_filename = f"{instance.pk}-{filename}"
    return make_path("llm-tasks", unique_filename)


def make_response_file_path(instance: "LLMRequest", filename: str) -> str:
    """
    Creates a date-based path for the response file, ensuring the filename is
    unique by prepending the request's primary key.

    Example:
    llm-requests/2026/01/15/1-batch_response.jsonl
    """
    unique_filename = f"{instance.pk}-{filename}"
    return make_path("llm-requests", unique_filename)


class LLMProvider:
    """LLM Provider choices"""

    GEMINI = 1
    OPENAI = 2
    ANTHROPIC = 3
    NAMES = (
        (GEMINI, "Google Gemini"),
        (OPENAI, "OpenAI"),
        (ANTHROPIC, "Anthropic"),
    )


class Task:
    """LLM Task choices"""

    SCAN_EXTRACTION = 1
    SCRAPER_EXTRACTION = 2
    CASENAME = 3
    CLEAN_DOCKET_NUMBERS = 4
    NAMES = (
        (SCAN_EXTRACTION, "Extract text from scan"),
        (SCRAPER_EXTRACTION, "Extract text from scraped documents"),
        (CASENAME, "Case Name Extraction"),
        (CLEAN_DOCKET_NUMBERS, "Clean Docket Numbers"),
    )


class TaskStatus:
    """LLM Task status choices"""

    UNPROCESSED = 0
    IN_PROGRESS = 1
    SUCCEEDED = 2
    FAILED = 3
    FINISHED = 4
    NAMES = (
        (UNPROCESSED, "Unprocessed"),
        (IN_PROGRESS, "In Progress"),
        (SUCCEEDED, "Succeeded"),
        (FAILED, "Failed"),
        (FINISHED, "Finished"),
    )


class PromptTypes:
    """Prompt type choices"""

    SYSTEM = 1
    USER = 2
    NAMES = (
        (SYSTEM, "System"),
        (USER, "User"),
    )


class Prompt(AbstractDateTimeModel):
    """Stores reusable prompts for LLM operations.

    Prompts can be system prompts (instructions for the LLM) or user prompts
    (specific extraction parameters). They can be reused across batches and
    tasks.
    """

    name = models.CharField(
        help_text="Descriptive name for this prompt",
        max_length=255,
    )
    prompt_type = models.SmallIntegerField(
        help_text="Whether this is a system or user prompt",
        choices=PromptTypes.NAMES,
        default=PromptTypes.SYSTEM,
    )
    text = models.TextField(
        help_text="The actual prompt text sent to the LLM",
    )
    notes = models.TextField(
        help_text="Documentation about purpose, changes, or usage notes",
        blank=True,
    )
    is_active = models.BooleanField(
        help_text="Whether this prompt is currently active and available for use",
        default=True,
    )

    class Meta:
        verbose_name = "Prompt"
        verbose_name_plural = "Prompts"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_prompt_type_display()})"


class LLMRequest(AbstractDateTimeModel):
    """Represents an LLM API request, either batch or single.

    Tracks request status, API costs, and groups related tasks together.
    Can be used for batch processing (multiple tasks) or single requests.
    """

    name = models.CharField(
        help_text="Human-readable request name",
        max_length=255,
        blank=True,
    )
    is_batch = models.BooleanField(
        help_text="Whether this is a batch request or single request",
        default=False,
    )
    batch_id = models.CharField(
        help_text="External batch ID from the LLM provider (for batch requests)",
        max_length=255,
        blank=True,
    )
    provider = models.SmallIntegerField(
        help_text="The LLM provider used for this request",
        choices=LLMProvider.NAMES,
        default=LLMProvider.GEMINI,
    )
    api_model_name = models.CharField(
        help_text="Specific model version (e.g., gemini-2.0-flash, claude-opus-4.1)",
        max_length=100,
        blank=True,
    )
    status = models.SmallIntegerField(
        help_text="The current status of the request",
        choices=TaskStatus.NAMES,
        default=TaskStatus.UNPROCESSED,
        db_index=True,
    )
    prompts = models.ManyToManyField(
        Prompt,
        help_text="Prompts used for this request",
        related_name="requests",
        blank=True,
    )
    total_tasks = models.IntegerField(
        help_text="Total number of tasks in this request",
        default=0,
    )
    completed_tasks = models.IntegerField(
        help_text="Number of tasks that have completed successfully",
        default=0,
    )
    failed_tasks = models.IntegerField(
        help_text="Number of tasks that have failed",
        default=0,
    )
    max_retries = models.SmallIntegerField(
        help_text="Maximum number of retries for failed tasks",
        default=3,
    )
    total_cost_estimate = models.DecimalField(
        help_text="Estimated API cost before running",
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
    )
    total_cost_actual = models.DecimalField(
        help_text="Actual API cost after completion",
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
    )
    date_started = models.DateTimeField(
        help_text="When request processing began",
        null=True,
        blank=True,
    )
    date_completed = models.DateTimeField(
        help_text="When request processing finished",
        null=True,
        blank=True,
    )
    extra_config_params = models.JSONField(
        help_text="Additional input data or parameters for the LLM",
        default=dict,
        blank=True,
    )
    batch_response_file = models.FileField(
        help_text="The batch response file from the LLM provider (e.g., a JSONL file)",
        upload_to=make_response_file_path,
        storage=IncrementingAWSMediaStorage(),
        max_length=1000,
        blank=True,
    )

    class Meta:
        verbose_name = "LLM Request"
        verbose_name_plural = "LLM Requests"

    def __str__(self) -> str:
        name = self.name or self.batch_id or f"Request {self.pk}"
        return f"{name} ({self.get_status_display()})"


class LLMTask(AbstractDateTimeModel):
    """Represents a task queued for LLM processing.

    Tasks can be things like PDF extraction from scans/scrapes, text
    summarization, case name extraction, etc. Tasks can be processed
    individually or as part of a batch.
    """

    status = models.SmallIntegerField(
        help_text="The current status of the task",
        choices=TaskStatus.NAMES,
        default=TaskStatus.UNPROCESSED,
        db_index=True,
    )

    llm_key = models.CharField(
        max_length=255,
        help_text="The LLM key for this task",
    )

    task = models.SmallIntegerField(
        help_text="The task to run.",
        choices=Task.NAMES,
        db_index=True,
    )

    retry_count = models.SmallIntegerField(
        help_text="Number of times this task has been retried",
        default=0,
    )
    error_message = models.TextField(
        help_text="Error message if the task failed",
        blank=True,
    )

    # Input file (generic - could be PDF, text, etc.)
    input_file = models.FileField(
        help_text="The input file to be processed (PDF, text, etc.)",
        upload_to=make_input_file_path,
        storage=IncrementingAWSMediaStorage(),
        max_length=1000,
        blank=True,
    )

    response_file = models.FileField(
        help_text="Full response from the LLM provider stored as a file",
        upload_to=make_response_file_path,
        storage=IncrementingAWSMediaStorage(),
        max_length=1000,
        blank=True,
    )

    # Processing metrics
    processing_time_ms = models.IntegerField(
        help_text="How long the LLM took to process (milliseconds)",
        null=True,
        blank=True,
    )
    date_started = models.DateTimeField(
        help_text="When processing began",
        null=True,
        blank=True,
    )
    date_completed = models.DateTimeField(
        help_text="When processing finished",
        null=True,
        blank=True,
    )

    # Link to target object via GenericForeignKey
    content_type = models.ForeignKey(
        ContentType,
        help_text="Content type of the related object",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the related object",
        null=True,
        blank=True,
    )
    content_object = GenericForeignKey("content_type", "object_id")

    request = models.ForeignKey(
        LLMRequest,
        help_text="The LLM request this task belongs to, if any",
        related_name="tasks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "LLM Task"
        verbose_name_plural = "LLM Tasks"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"Task {self.pk}: {self.get_status_display()}"
