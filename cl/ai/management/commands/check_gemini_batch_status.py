"""
Check the status of in-progress Google Gemini batch jobs and download results when complete.

This command queries all LLMRequest objects for Google Gemini provider with status
IN_PROGRESS and checks their batch job status with the Google GenAI API. When a
batch job succeeds, it automatically downloads the results, processes them, and
updates all associated LLMTask objects.

Intended to be run periodically via cronjob or daemon (e.g., every 5-10 minutes).

NOTE: This command is specific to Google Gemini provider. If you add other providers
(OpenAI, Anthropic), create separate commands (e.g., check_openai_batch_status.py).

BASIC USAGE:
    python manage.py check_gemini_batch_status

DOCKER USAGE:
    docker exec cl-django python manage.py check_gemini_batch_status

WHAT IT DOES:
    - Finds all LLMRequest objects with status=IN_PROGRESS
    - Checks batch job status with the provider
    - If succeeded: Downloads results, updates tasks, saves response file
    - If failed/cancelled/expired: Marks request and all tasks as FAILED
    - Updates date_completed timestamp when batch finishes

RESPONSE FILE NAMING:
    Files are saved with meaningful names:
    batch_{batch_id_short}_{timestamp}.jsonl

    Example: batch_d06qupto0eg36yg4fy49d3trshhus1it5xox_20260126_143052.jsonl

GOOD TO KNOW:
    - Safe to run multiple times (idempotent for completed batches)
    - Each task's response is saved as properly formatted JSON
    - Completed/failed requests are skipped on subsequent runs
    - Updates completed_tasks and failed_tasks counts on LLMRequest

EXAMPLE OUTPUT:
    Found 2 pending batch requests to check.
    Checking status for request: 42 (batches/abc123xyz...)
      - Job state is 'JOB_STATE_RUNNING'. Skipping for now.
    Checking status for request: 43 (batches/def456uvw...)
      - Job succeeded. Downloading and processing results...
    Finished checking all pending requests.
"""

import json
import logging
from typing import Any

import environ
import sentry_sdk
from django.core.files.base import ContentFile
from django.core.management.base import CommandError
from django.db import transaction
from django.utils.timezone import now

from cl.ai.llm_providers.google import GoogleGenAIBatchWrapper
from cl.ai.models import LLMProvider, LLMRequest, LLMTaskStatusChoices
from cl.lib.command_utils import VerboseCommand

logger = logging.getLogger(__name__)

COMPLETED_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}


def process_succeeded_request(
    wrapper: GoogleGenAIBatchWrapper, request: LLMRequest, job: Any
) -> None:
    """Download results from a succeeded batch job and update all tasks.

    Wrapped in an atomic transaction so a partial failure rolls back cleanly.

    :param wrapper: Google GenAI batch wrapper used to download results.
    :param request: The LLMRequest whose batch job succeeded.
    :param job: The batch job object returned by the provider API.
    """
    jsonl_content = wrapper.download_results(job)
    processed_results = wrapper.process_results(jsonl_content)

    with transaction.atomic():
        batch_id_short = request.batch_id.split("/")[-1]
        timestamp = now().strftime("%Y%m%d_%H%M%S")
        response_filename = f"batch_{batch_id_short}_{timestamp}.jsonl"
        request.batch_response_file.save(
            response_filename,
            ContentFile(jsonl_content.encode("utf-8")),
        )

        tasks_to_update = {task.llm_key: task for task in request.tasks.all()}
        for res in processed_results:
            task = tasks_to_update.get(res["key"])
            if not task:
                continue

            task.status = (
                LLMTaskStatusChoices.SUCCEEDED
                if res["status"] == "SUCCEEDED"
                else LLMTaskStatusChoices.FAILED
            )
            task.error_message = res["error_message"] or ""
            if res.get("raw_result"):
                try:
                    task.response_file.save(
                        f"{task.llm_key}_result.json",
                        ContentFile(
                            json.dumps(
                                res["raw_result"],
                                indent=2,
                                ensure_ascii=False,
                            ).encode("utf-8")
                        ),
                    )
                except (TypeError, ValueError) as e:
                    logger.warning(
                        f"Could not serialize JSON for task {task.llm_key}: {e}"
                    )
                    task.response_file.save(
                        f"{task.llm_key}_result.txt",
                        ContentFile(str(res["raw_result"]).encode("utf-8")),
                    )
            task.save()

        request.status = LLMTaskStatusChoices.FINISHED
        request.completed_tasks = request.tasks.filter(
            status=LLMTaskStatusChoices.SUCCEEDED
        ).count()
        request.failed_tasks = request.tasks.filter(
            status=LLMTaskStatusChoices.FAILED
        ).count()
        request.date_completed = now()
        request.save()


def process_failed_request(request: LLMRequest, job_state_name: str) -> None:
    """Mark a request and all its tasks as FAILED.

    Wrapped in an atomic transaction so all updates succeed or fail together.

    :param request: The LLMRequest to mark as failed.
    :param job_state_name: The terminal job state name (e.g.
        ``JOB_STATE_FAILED``) included in task error messages.
    """
    with transaction.atomic():
        request.status = LLMTaskStatusChoices.FAILED
        request.date_completed = now()
        for task in request.tasks.all():
            task.status = LLMTaskStatusChoices.FAILED
            task.error_message = (
                f"Batch job failed with state: {job_state_name}"
            )
            task.save()
        request.save()


def handle_request(
    wrapper: GoogleGenAIBatchWrapper, request: LLMRequest
) -> None:
    """Check a single request's batch job status and process results.

    Routes to the appropriate handler based on job state. Catches
    ``ValueError`` (from download errors) and generic ``Exception``
    (reported to Sentry) to ensure one failing request doesn't stop
    processing of subsequent requests.

    :param wrapper: Google GenAI batch wrapper used to query job status.
    :param request: The in-progress LLMRequest to check.
    """
    try:
        job = wrapper.get_job(request.batch_id)

        if job.state.name not in COMPLETED_STATES:
            logger.info(
                f"  - Job state is '{job.state.name}'. Skipping for now."
            )
            return

        if job.state.name == "JOB_STATE_SUCCEEDED":
            logger.info(
                "  - Job succeeded. Downloading and processing results..."
            )
            process_succeeded_request(wrapper, request, job)
        else:
            logger.info(
                f"  - Job ended with non-success state: {job.state.name}"
            )
            process_failed_request(request, job.state.name)

    except ValueError as e:
        logger.warning(
            f"ValueError downloading results for request {request.pk}: {e}"
        )
    except Exception as e:
        logger.exception(
            f"Unexpected error in check_gemini_batch_status for request {request.pk}"
        )
        sentry_sdk.capture_exception(e)

        request.status = LLMTaskStatusChoices.FAILED
        request.date_completed = now()
        request.save()


class Command(VerboseCommand):
    help = "Check the status of in-progress Google Gemini batch jobs and download results when complete."

    def handle(self, *args, **options):
        super().handle(*args, **options)
        env = environ.FileAwareEnv()
        batch_api_key = env("GEMINI_BATCH_API_KEY", default=None)
        if not batch_api_key:
            raise CommandError(
                "GEMINI_BATCH_API_KEY environment variable is required. "
                "This should be separate from GEMINI_API_KEY to allow "
                "different API keys for different tasks."
            )

        pending_requests = LLMRequest.objects.filter(
            is_batch=True,
            status=LLMTaskStatusChoices.IN_PROGRESS,
            provider=LLMProvider.GEMINI,
        )
        logger.info(
            f"Found {len(pending_requests)} pending batch requests to check."
        )

        if not pending_requests:
            return

        wrapper = GoogleGenAIBatchWrapper(api_key=batch_api_key)
        for request in pending_requests:
            logger.info(
                f"Checking status for request: {request.pk} ({request.batch_id})"
            )
            handle_request(wrapper, request)

        logger.info("Finished checking all pending requests.")
