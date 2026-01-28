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
import os

import sentry_sdk
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import now

from cl.ai.llm_providers.google import GoogleGenAIBatchWrapper
from cl.ai.models import LLMProvider, LLMRequest, TaskStatus

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Check the status of in-progress Google Gemini batch jobs and download results when complete."

    def handle(self, *args, **options):
        # Get GEMINI_BATCH_API_KEY from environment
        batch_api_key = os.environ.get("GEMINI_BATCH_API_KEY")
        if not batch_api_key:
            raise CommandError(
                "GEMINI_BATCH_API_KEY environment variable is required. "
                "This should be separate from GEMINI_API_KEY to allow "
                "different API keys for different tasks."
            )

        pending_requests = LLMRequest.objects.filter(
            is_batch=True,
            status=TaskStatus.IN_PROGRESS,
            provider=LLMProvider.GEMINI,
        )
        self.stdout.write(
            f"Found {len(pending_requests)} pending batch requests to check."
        )

        if not pending_requests:
            return

        wrapper = GoogleGenAIBatchWrapper(api_key=batch_api_key)
        for request in pending_requests:
            self.stdout.write(
                f"Checking status for request: {request.pk} ({request.batch_id})"
            )
            try:
                job = wrapper.get_job(request.batch_id)

                completed_states = {
                    "JOB_STATE_SUCCEEDED",
                    "JOB_STATE_FAILED",
                    "JOB_STATE_CANCELLED",
                    "JOB_STATE_EXPIRED",
                }
                if job.state.name not in completed_states:
                    self.stdout.write(
                        f"  - Job state is '{job.state.name}'. Skipping for now."
                    )
                    continue

                if job.state.name == "JOB_STATE_SUCCEEDED":
                    self.stdout.write(
                        "  - Job succeeded. Downloading and processing results..."
                    )
                    jsonl_content = wrapper.download_results(job)
                    processed_results = wrapper.process_results(jsonl_content)

                    # Create meaningful filename with batch_id and timestamp
                    batch_id_short = request.batch_id.split("/")[-1]
                    timestamp = now().strftime("%Y%m%d_%H%M%S")
                    response_filename = (
                        f"batch_{batch_id_short}_{timestamp}.jsonl"
                    )
                    request.batch_response_file.save(
                        response_filename,
                        ContentFile(jsonl_content.encode("utf-8")),
                    )

                    tasks_to_update = {
                        task.llm_key: task for task in request.tasks.all()
                    }
                    for res in processed_results:
                        task = tasks_to_update.get(res["key"])
                        if not task:
                            continue

                        task.status = (
                            TaskStatus.SUCCEEDED
                            if res["status"] == "SUCCEEDED"
                            else TaskStatus.FAILED
                        )
                        task.error_message = res["error_message"] or ""
                        if res.get("raw_result"):
                            try:
                                # Use proper JSON serialization instead of str()
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
                                # JSON serialization failed - fall back to string
                                self.stderr.write(
                                    f"Warning: Could not serialize JSON for task {task.llm_key}: {e}"
                                )
                                task.response_file.save(
                                    f"{task.llm_key}_result.txt",
                                    ContentFile(
                                        str(res["raw_result"]).encode("utf-8")
                                    ),
                                )
                        task.save()

                    request.status = TaskStatus.FINISHED
                    request.completed_tasks = request.tasks.filter(
                        status=TaskStatus.SUCCEEDED
                    ).count()
                    request.failed_tasks = request.tasks.filter(
                        status=TaskStatus.FAILED
                    ).count()
                    request.date_completed = now()

                else:  # Failed, Cancelled, or Expired
                    self.stdout.write(
                        f"  - Job ended with non-success state: {job.state.name}"
                    )
                    request.status = TaskStatus.FAILED
                    request.date_completed = now()
                    # Mark all tasks as failed with descriptive error
                    for task in request.tasks.all():
                        task.status = TaskStatus.FAILED
                        task.error_message = (
                            f"Batch job failed with state: {job.state.name}"
                        )
                        task.save()

                request.save()

            except ValueError as e:
                # Specific handling for download_results errors
                self.stderr.write(
                    f"Error downloading results for request {request.pk}: {e}"
                )
                logger.warning(
                    f"ValueError downloading results for request {request.pk}: {e}"
                )
            except Exception as e:
                # Unexpected error - log, report to Sentry, mark as failed
                self.stderr.write(
                    f"Unexpected error checking request {request.pk}: {e}"
                )
                logger.exception(
                    f"Unexpected error in check_gemini_batch_status for request {request.pk}"
                )
                sentry_sdk.capture_exception(e)

                # Mark request as failed to prevent infinite retries
                request.status = TaskStatus.FAILED
                request.date_completed = now()
                request.save()

                self.stderr.write(
                    f"  - Marked request {request.pk} as FAILED to prevent retries"
                )

        self.stdout.write(
            self.style.SUCCESS("Finished checking all pending requests.")
        )
