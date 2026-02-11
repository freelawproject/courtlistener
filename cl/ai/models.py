from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from cl.lib.model_helpers import (
    make_llm_request_response_file_path,
    make_llm_task_input_file_path,
    make_llm_task_response_file_path,
)
from cl.lib.models import AbstractDateTimeModel
from cl.lib.storage import S3PrivateLLMStorage


class LLMProvider(models.IntegerChoices):
    """LLM Provider choices"""

    GEMINI = 1, "Google Gemini"
    OPENAI = 2, "OpenAI"
    ANTHROPIC = 3, "Anthropic"


class LLMTaskChoices(models.IntegerChoices):
    """LLM Task choices"""

    SCAN_EXTRACTION = 1, "Extract text from scan"
    SCRAPER_EXTRACTION = 2, "Extract text from scraped documents"
    CASENAME = 3, "Case Name Extraction"
    CLEAN_DOCKET_NUMBERS = 4, "Clean Docket Numbers"


class LLMTaskStatusChoices(models.IntegerChoices):
    """LLM Task status choices"""

    UNPROCESSED = 0, "Unprocessed"
    IN_PROGRESS = 1, "In Progress"
    SUCCEEDED = 2, "LLM response received"
    FAILED = 3, "Failed"
    FINISHED = 4, "LLM response processed"


class PromptTypes(models.IntegerChoices):
    """Prompt type choices"""

    SYSTEM = 1, "System"
    USER = 2, "User"


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
        choices=PromptTypes,
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
        help_text="Human-readable request name. e.g., 'Batch run for Jan 20 scans'",
        max_length=255,
        blank=True,
    )
    is_batch = models.BooleanField(
        help_text="True if this request groups multiple tasks for a batch API call",
        default=False,
    )
    batch_id = models.CharField(
        help_text="External batch ID from the LLM provider (for batch requests)",
        max_length=255,
        blank=True,
    )
    provider = models.SmallIntegerField(
        help_text="The LLM provider used for this request",
        choices=LLMProvider,
        default=LLMProvider.GEMINI,
    )
    api_model_name = models.CharField(
        help_text="Specific model version (e.g., gemini-3-pro-preview, claude-sonnet-4.5)",
        max_length=100,
        blank=True,
    )
    status = models.SmallIntegerField(
        help_text="The current status of the request",
        choices=LLMTaskStatusChoices,
        default=LLMTaskStatusChoices.UNPROCESSED,
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
        help_text="JSON object with additional provider-specific parameters (e.g., temperature, max_tokens).",
        default=dict,
        blank=True,
    )
    batch_response_file = models.FileField(
        help_text="The batch response file from the LLM provider (e.g., a JSONL file)",
        upload_to=make_llm_request_response_file_path,
        storage=S3PrivateLLMStorage(),
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
        choices=LLMTaskStatusChoices,
        default=LLMTaskStatusChoices.UNPROCESSED,
    )

    llm_key = models.CharField(
        max_length=255,
        help_text="A unique identifier from the LLM provider for this task, used to map results back from a batch job.",
    )

    task = models.SmallIntegerField(
        help_text="The specific type of operation this task represents.",
        choices=LLMTaskChoices,
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
        upload_to=make_llm_task_input_file_path,
        storage=S3PrivateLLMStorage(),
        max_length=1000,
        blank=True,
    )
    input_text = models.TextField(
        help_text="Text input for the task, if not using a file.", blank=True
    )

    response_file = models.FileField(
        help_text="Full response from the LLM provider stored as a file",
        upload_to=make_llm_task_response_file_path,
        storage=S3PrivateLLMStorage(),
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
        db_index=False,
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
