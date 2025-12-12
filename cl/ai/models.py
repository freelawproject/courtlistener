from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.text import slugify

from cl.lib.models import AbstractDateTimeModel


class Prompt(AbstractDateTimeModel):
    """Represents a single API message object (System, User, etc) for building the conversational context passed to the LLM"""

    SYSTEM = 1
    USER = 2
    ROLES = (
        (SYSTEM, "System"),
        (USER, "User"),
    )
    prompt_name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique identifier name for prompt (e.g. 'ocr-p3d-sys-v1'). It will be slugified if it is not in this format.",
    )
    role = models.SmallIntegerField(
        choices=ROLES,
        default=USER,
        help_text="The identifier used by the LLM API to distinguish the type of message (e.g., system instructions vs. user input)",
    )
    text = models.TextField(help_text="The actual text of the prompt used")
    position = models.PositiveSmallIntegerField(
        help_text="The sequence order for this prompt within a prompt set (e.g., 1 for System, 2 for User, etc)"
    )

    def save(self, *args, **kwargs):
        self.prompt_name = slugify(self.prompt_name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.prompt_name} | {self.get_role_display()}: {self.text[:50]}..."


class LLMConfig(AbstractDateTimeModel):
    """Stores the specific LLM model identifier and generation parameters used for execution"""

    PROVIDER_CHOICES = (
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("google", "Google Gemini"),
    )
    config_name = models.CharField(
        max_length=255,
        unique=True,  # Critical for quick lookup and preventing duplicates
        help_text="Unique identifier for this configuration (e.g., 'gemini2-5-high-temp'). It will be slugified if it is not in this format.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description about when/why to use this specific config",
    )
    provider = models.CharField(
        max_length=20,
        choices=PROVIDER_CHOICES,
        default="openai",
        help_text="The LLM provider to use",
    )
    model_name = models.CharField(
        max_length=255,
        help_text="The specific model ID expected by the API (e.g., 'gpt-4o', 'claude-3-opus')",
    )
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON dictionary for specific model settings like {'temperature': 0.5, 'max_tokens': 1000}",
    )

    def __str__(self):
        return f"{self.config_name} | {self.provider} : {self.model_name}"

    def save(self, *args, **kwargs):
        self.config_name = slugify(self.config_name)
        super().save(*args, **kwargs)


class LLMPromptSet(AbstractDateTimeModel):
    """Groups specific Prompt objects into a versioned instruction set for a specific task (e.g., 'ocr_scan_p3d')."""

    prompt_set_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Identifier for the task (e.g., 'ocr-scan-p3d'). It will be slugified if it is not in this format. This name must be repeated across versions to use the latest active one.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this version of the prompt set attempts to achieve",
    )
    prompts = models.ManyToManyField(
        Prompt,
        help_text="The collection of individual prompts that make up this instruction set",
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Incremental version number for this specific task name",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates if this is the currently active version for the task",
    )
    notes = models.TextField(
        blank=True,
        help_text="Internal comments, known limitations, or reasons for changes (e.g., 'v1 failed on handwritten text; v2 adds examples to fix this')",
    )

    def save(self, *args, **kwargs):
        self.prompt_set_name = slugify(self.prompt_set_name)
        super().save(*args, **kwargs)

    class Meta:
        # Ensure only one set is the active version for a given task name
        unique_together = ("prompt_set_name", "version")

    def __str__(self):
        return f"{self.prompt_set_name} | Version: {self.version}"


class LLMRun(AbstractDateTimeModel):
    """Records a single execution of an LLM call, linking the input data, configuration used,
    and the resulting output for traceability and debugging
    """

    llm_config = models.ForeignKey(
        LLMConfig,
        on_delete=models.CASCADE,
        help_text="The configuration (provider/model/params) used for this run",
    )
    prompt_set = models.ForeignKey(
        LLMPromptSet,
        on_delete=models.CASCADE,
        help_text="The specific version of prompts used",
    )

    # Generic Foreign Key
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")

    output = models.TextField(
        blank=True,
        help_text="The raw text response returned by the LLM, useful for debugging parsing errors",
    )
    success = models.BooleanField(
        default=True, help_text="True if the output was successfully obtained"
    )

    def __str__(self):
        return f"Run {self.id} | {self.llm_config}"
