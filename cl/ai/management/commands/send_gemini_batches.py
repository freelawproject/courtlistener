"""
Create and submit Google Gemini batch requests for files stored in S3.

This command fetches files from an S3 path, creates LLMTask objects for each file,
and submits a batch job to Google Gemini. It supports system prompt caching and
optional file duplication.

NOTE: This command is specific to Google Gemini provider. For other providers,
create separate commands (e.g., send_openai_batches.py).

REQUIRED ARGUMENTS:
    --path              S3 path/prefix containing files to process
                        Example: "llm-inputs/batch-2026-01/"

    --system-prompt     ID of the Prompt object with prompt_type=SYSTEM
                        Example: 1

    --user-prompt       ID of the Prompt object with prompt_type=USER
                        Example: 2

OPTIONAL ARGUMENTS:
    --model             Gemini model name (default: gemini-2.5-pro)
                        Supported: gemini-3-flash-preview, gemini-3-pro-preview,
                                  gemini-2.5-pro, gemini-2.5-flash,
                                  gemini-2.5-flash-lite

    --request-name      Custom name for the LLMRequest
                        Default: "Batch for {s3_path}"

    --cache-name        Stable name for system prompt cache (for cost savings)
                        Example: "scan-extraction-cache-v1"

    --bucket            S3 bucket name (default: AWS_STORAGE_BUCKET_NAME)
                        Must be in allowed list for security

    --store-input-files Store files in CourtListener storage (creates duplicates)
                        Default: Only S3 references are stored (no duplication)

BASIC USAGE:
    python manage.py send_gemini_batches \\
        --path "llm-inputs/batch-2026-01/" \\
        --system-prompt 1 \\
        --user-prompt 2

DOCKER USAGE:
    docker exec cl-django python manage.py send_gemini_batches \\
        --path "llm-inputs/january-scans/" \\
        --system-prompt 1 \\
        --user-prompt 2 \\
        --request-name "January 2026 Scan Batch"

EXAMPLE WITH CACHING:
    docker exec cl-django python manage.py send_gemini_batches \\
        --path "llm-inputs/batch-2026-01/" \\
        --system-prompt 1 \\
        --user-prompt 2 \\
        --cache-name "scan-extraction-v1" \\
        --model "gemini-2.0-flash-001"

EXAMPLE WITH CUSTOM BUCKET:
    docker exec cl-django python manage.py send_gemini_batches \\
        --path "external-scans/batch-jan/" \\
        --bucket "dev-com-courtlistener-storage" \\
        --system-prompt 1 \\
        --user-prompt 2 \\
        --store-input-files

WHAT IT DOES:
    1. Validates system and user prompt IDs
    2. Creates an LLMRequest object with status IN_PROGRESS
    3. Lists all files in the specified S3 path
    4. Creates an LLMTask for each file
    5. Optionally stores files or just references S3 paths
    6. Uploads files to Google GenAI Files API
    7. Creates and submits a batch job
    8. Returns batch_id for status tracking

SECURITY FEATURES:
    - Bucket whitelist validation (only allows configured buckets)
    - Gemini model name validation
    - Input validation for all parameters
    - Automatic cleanup on failure
    - Errors reported to Sentry for monitoring

GOOD TO KNOW:
    - Requires GEMINI_BATCH_API_KEY environment variable (separate from GEMINI_API_KEY)
    - Only processes PDF files (.pdf extension)
    - Sets date_started timestamp on LLMRequest
    - Creates unique llm_key for each task: "scan-batch-{llm_request.pk}"
    - Temporary files are automatically cleaned up
    - On S3 failure, LLMRequest is deleted (no partial state)
    - Use check_gemini_batch_status command to monitor progress

FILE STORAGE MODES:
    Default (--store-input-files NOT set):
        - Only stores S3 reference in LLMTask.input_file.name
        - No duplication, saves storage costs
        - File must remain in S3

    With --store-input-files flag:
        - Downloads and stores files in CourtListener storage
        - Creates duplicates, uses more storage
        - Files available even if removed from S3

EXPECTED OUTPUT:
    Starting new Gemini batch request process...
    Created LLMRequest with ID: 42
    Fetching PDF files from S3 path: llm-inputs/batch-2026-01/
      - Referenced S3 file: scan001.pdf (llm-inputs/batch-2026-01/scan001.pdf)
      - Referenced S3 file: scan002.pdf (llm-inputs/batch-2026-01/scan002.pdf)
    Created 2 LLMTask objects.
    Initializing Google GenAI wrapper...
    Preparing batch requests...
    Executing batch job...
    Cleaning up temporary files...
    Batch job sent to provider. Batch ID: batches/abc123xyz...

NEXT STEPS AFTER RUNNING:
    1. Note the LLMRequest ID and batch ID from output
    2. Run check_gemini_batch_status periodically to monitor progress
    3. When complete, results are in LLMTask.response_file for each task
"""

import logging
import os
import tempfile
import uuid
from collections.abc import Generator

import boto3
import environ
import sentry_sdk
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import CommandError
from django.utils.timezone import now

from cl.ai.llm_providers.google import GoogleGenAIBatchWrapper
from cl.lib.command_utils import VerboseCommand
from cl.ai.models import (
    LLMProvider,
    LLMRequest,
    LLMTask,
    Prompt,
    PromptTypes,
    Task,
    TaskStatus,
)

logger = logging.getLogger(__name__)

# Supported Gemini models for batch operations
SUPPORTED_GEMINI_MODELS = {
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
}


def get_s3_file_list(
    s3_path: str,
    bucket_name: str | None = None,
    file_extension: str = ".pdf",
) -> Generator[tuple[str, bytes, str]]:
    """List files from S3 path and yield file information.

    :param s3_path: S3 prefix/path (e.g., "llm-inputs/batch-2026-01/")
    :param bucket_name: Optional bucket name (defaults to AWS_STORAGE_BUCKET_NAME)
    :param file_extension: File extension to filter (e.g., ".pdf", ".txt")
    :yields: (filename, file_content_bytes, s3_key)
    :raises CommandError: If S3 access fails or bucket is not allowed
    """
    # Use settings for credentials and bucket
    bucket = bucket_name or settings.AWS_STORAGE_BUCKET_NAME
    key_id = settings.AWS_ACCESS_KEY_ID
    secret = settings.AWS_SECRET_ACCESS_KEY

    # Security: Validate bucket is in allowed list
    allowed_buckets = {
        settings.AWS_STORAGE_BUCKET_NAME,
        settings.AWS_PRIVATE_STORAGE_BUCKET_NAME,
    }
    if bucket not in allowed_buckets:
        raise CommandError(
            f"Bucket '{bucket}' not in allowed list: {allowed_buckets}"
        )

    # Create S3 client with session token support for dev mode
    try:
        client_kwargs = {
            "service_name": "s3",
            "aws_access_key_id": key_id,
            "aws_secret_access_key": secret,
        }

        # In dev mode, add session token if available
        if settings.DEVELOPMENT:
            env = environ.FileAwareEnv()
            session_token = env(
                "AWS_SESSION_TOKEN", default=None
            ) or env("AWS_DEV_SESSION_TOKEN", default=None)
            if session_token:
                client_kwargs["aws_session_token"] = session_token

        s3_client = boto3.client(**client_kwargs)
    except (BotoCoreError, ClientError) as e:
        raise CommandError(f"Failed to create S3 client: {e}")

    # Ensure path doesn't start with /
    prefix = s3_path.lstrip("/")

    try:
        # List objects in the prefix
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

        file_count = 0
        for page in pages:
            if "Contents" not in page:
                continue

            for obj in page["Contents"]:
                key = obj["Key"]
                # Skip directories
                if key.endswith("/"):
                    continue

                # Extract filename from key
                filename = key.split("/")[-1]

                # Filter by file extension
                if not filename.lower().endswith(file_extension.lower()):
                    continue

                # Download file content
                response = s3_client.get_object(Bucket=bucket, Key=key)
                file_content = response["Body"].read()

                file_count += 1
                yield (filename, file_content, key)

        if file_count == 0:
            raise CommandError(
                f"No {file_extension} files found in s3://{bucket}/{prefix}. "
                "Please check the path and ensure files with the specified extension exist."
            )

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "NoSuchBucket":
            raise CommandError(f"Bucket '{bucket}' does not exist")
        elif error_code == "AccessDenied":
            raise CommandError(
                f"Access denied to bucket '{bucket}'. Check credentials."
            )
        else:
            raise CommandError(f"Failed to access S3: {e}")
    except BotoCoreError as e:
        raise CommandError(f"AWS SDK error: {e}")


class Command(VerboseCommand):
    help = "Create and submit Google Gemini batch requests for files stored in S3."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            required=True,
            help="The S3 path/prefix containing PDF files to process (e.g., 'llm-inputs/batch-2026-01/').",
        )
        parser.add_argument(
            "--model",
            type=str,
            default="gemini-2.5-pro",
            help=f"Gemini model name (default: gemini-2.5-pro). Supported: {', '.join(sorted(SUPPORTED_GEMINI_MODELS))}",
        )
        parser.add_argument(
            "--system-prompt",
            type=int,
            required=True,
            help="The ID of the system Prompt object.",
        )
        parser.add_argument(
            "--user-prompt",
            type=int,
            required=True,
            help="The ID of the user Prompt object.",
        )
        parser.add_argument(
            "--request-name",
            type=str,
            default="",
            help="An optional name for the LLMRequest.",
        )
        parser.add_argument(
            "--cache-name",
            type=str,
            default="scanning-project-sys-prompt",
            help="An optional, stable name for the system prompt cache.",
        )
        parser.add_argument(
            "--bucket",
            type=str,
            default=None,
            help="S3 bucket name (defaults to AWS_STORAGE_BUCKET_NAME from settings).",
        )
        parser.add_argument(
            "--store-input-files",
            action="store_true",
            help="Store input files in CourtListener storage (creates duplicates). By default, only S3 references are stored.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        logger.info("Starting new Gemini batch request process...")

        # 1. Get and validate arguments
        s3_path = options["path"]
        model = options["model"]
        request_name = options["request_name"] or f"Batch for {s3_path}"
        cache_name = options["cache_name"]

        # Validate Gemini model
        if model not in SUPPORTED_GEMINI_MODELS:
            raise CommandError(
                f"Invalid Gemini model '{model}'. "
                f"Supported models: {', '.join(sorted(SUPPORTED_GEMINI_MODELS))}"
            )

        # Get GEMINI_BATCH_API_KEY from environment
        env = environ.FileAwareEnv()
        batch_api_key = env("GEMINI_BATCH_API_KEY", default=None)
        if not batch_api_key:
            raise CommandError(
                "GEMINI_BATCH_API_KEY environment variable is required. "
                "This should be separate from GEMINI_API_KEY to allow "
                "different API keys for different tasks."
            )

        # 2. Fetch Prompts
        try:
            system_prompt = Prompt.objects.get(
                pk=options["system_prompt"], prompt_type=PromptTypes.SYSTEM
            )
            user_prompt = Prompt.objects.get(
                pk=options["user_prompt"], prompt_type=PromptTypes.USER
            )
        except Prompt.DoesNotExist:
            raise CommandError("Invalid system or user prompt ID provided.")

        # 3. Create Django Model objects
        llm_request = LLMRequest.objects.create(
            name=request_name,
            is_batch=True,
            provider=LLMProvider.GEMINI,
            api_model_name=model,
            status=TaskStatus.IN_PROGRESS,
            date_started=now(),
        )
        llm_request.prompts.set([system_prompt, user_prompt])
        logger.info(f"Created LLMRequest with ID: {llm_request.pk}")

        # 4. Fetch PDF files from S3 and create tasks
        bucket = options.get("bucket") or settings.AWS_STORAGE_BUCKET_NAME
        logger.info(
            f"Fetching PDF files from S3: s3://{bucket}/{s3_path}"
        )
        tasks_data = []
        temp_files = []
        store_files = options["store_input_files"]

        try:
            for filename, file_content, s3_key in get_s3_file_list(
                s3_path=s3_path,
                bucket_name=options.get("bucket"),
                file_extension=".pdf",  # Hardcoded to PDF only
            ):
                # e.g. scan-batch-1-197a40aadcbe
                llm_key = f"scan-batch-{llm_request.pk}-{uuid.uuid4().hex[:12]}"
                task = LLMTask.objects.create(
                    request=llm_request,
                    task=Task.SCAN_EXTRACTION,
                    llm_key=llm_key,
                )

                # Store file in CourtListener storage or just reference S3 path
                if store_files:
                    # Option 1: Duplicate to CourtListener storage
                    task.input_file.save(filename, ContentFile(file_content))
                    logger.info(f"  - Stored file: {filename}")
                else:
                    # Option 2: Just set the S3 key reference (no duplication)
                    task.input_file.name = s3_key
                    task.save()
                    logger.info(f"  - Referenced S3 file: {s3_key}")

                # Create temporary file for upload to Google GenAI
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False, suffix=os.path.splitext(filename)[1]
                )
                temp_file.write(file_content)
                temp_file.close()
                temp_files.append(temp_file.name)

                tasks_data.append(
                    {"llm_key": llm_key, "input_file_path": temp_file.name}
                )

        except CommandError:
            # Clean up created request if S3 fails
            llm_request.delete()
            raise

        llm_request.total_tasks = len(tasks_data)
        llm_request.save()
        logger.info(
            f"Created {llm_request.total_tasks} LLMTask objects."
        )

        # 5. Use the decoupled wrapper to prepare and execute the batch
        try:
            logger.info("Initializing Google GenAI wrapper...")
            wrapper = GoogleGenAIBatchWrapper(api_key=batch_api_key)

            logger.info("Preparing batch requests...")
            prepared_requests = wrapper.prepare_batch_requests(
                tasks_data, user_prompt.text
            )

            logger.info("Executing batch job...")
            batch_id = wrapper.execute_batch(
                model_name=llm_request.api_model_name,
                requests=prepared_requests,
                system_prompt=system_prompt.text,
                cache_display_name=cache_name,
                batch_display_name=llm_request.name
                or f"Request-{llm_request.pk}",
            )

            llm_request.batch_id = batch_id
            llm_request.save()

            logger.info(
                f"Batch job sent to provider. Batch ID: {batch_id}"
            )

        except ValueError as e:
            # Google API initialization or configuration errors
            llm_request.status = TaskStatus.FAILED
            llm_request.save()
            logger.warning(
                f"Configuration error for request {llm_request.pk}: {e}"
            )
            raise CommandError(f"Configuration error: {e}")
        except Exception as e:
            # Unexpected errors during batch creation - report to Sentry
            llm_request.status = TaskStatus.FAILED
            llm_request.save()
            logger.exception(
                f"Unexpected error creating batch for request {llm_request.pk}"
            )
            sentry_sdk.capture_exception(e)
            raise CommandError(f"Failed to create batch job: {e}")
        finally:
            # Clean up temporary files
            logger.info("Cleaning up temporary files...")
            for temp_file_path in temp_files:
                try:
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
                except OSError as e:
                    # Only warn if it's not a "file doesn't exist" error
                    if e.errno != 2:  # errno.ENOENT
                        logger.warning(
                            f"Failed to remove temp file {temp_file_path}: {e}"
                        )
