import json
import logging
from contextlib import nullcontext
from io import BufferedReader
from typing import Any, cast

from asgiref.sync import sync_to_async
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.files.base import File
from httpx import (
    AsyncClient,
    NetworkError,
    Response,
    TimeoutException,
)

from cl.audio.models import Audio
from cl.lib.decorators import retry
from cl.lib.exceptions import NoSuchKey
from cl.lib.models import AbstractPDF
from cl.search.models import Opinion, RECAPDocument

logger = logging.getLogger(__name__)


def log_invalid_embedding_errors(embeddings: Any):
    """Log an error when the embeddings response is not a list.

    :param embeddings: The embeddings object to validate and log.
    """
    if isinstance(embeddings, dict):
        logger.error(
            "Received API error response in embeddings: %s",
            json.dumps(embeddings, default=str),
        )
    else:
        logger.error(
            "Unexpected data type for embeddings: %s (%s)",
            str(embeddings)[:200],
            type(embeddings),
        )


async def clean_up_recap_document_file(item: AbstractPDF) -> None:
    """Clean up the document's file-related fields after detecting the file
    doesn't exist in the storage.

    :param item: The document to work on.
    :return: None
    """

    if isinstance(item, AbstractPDF):
        await sync_to_async(item.filepath_local.delete)()
        item.sha1 = ""
        item.file_size = None
        item.page_count = None
        if isinstance(item, RECAPDocument):
            cast(RECAPDocument, item).date_upload = None
            cast(RECAPDocument, item).is_available = False
        await item.asave()


async def microservice(
    service: str,
    method: str = "POST",
    item: AbstractPDF | Opinion | Audio | None = None,
    file: BufferedReader | File | bytes | None = None,
    file_type: str | None = None,
    filepath: str | None = None,
    data=None,
    params=None,
) -> Response:
    """Call a Microservice endpoint

    This is a helper utility to call our microservices.  To see a list of Endpoints
    check out the settings file cl/settings/public.py.

    Because of the various ways our db is setup we have a few different params we use
    in this function.

    Only the selected file source is opened, preferring file, then item, then
    filepath. A missing PDF on item is cleaned up and falls back to filepath.
    Named Django files keep their filename unless file_type is provided.

    :param service: The service to call
    :param method: The method to use (defaults to POST)
    :param item: The document as a db object
    :param file: A caller-owned file or byte array; this function does not close it
    :param file_type: Override the upload filename with dummy.<file_type>
    :param filepath: The filepath of the file
    :param data: The data to send
    :param params: The params to send
    :return: The response from the microservice
    """

    services = settings.MICROSERVICE_URLS

    file_context = nullcontext()
    field_file = None
    filename = "filename"
    if file:
        file_context = nullcontext(file)
        if file_type:
            filename = f"dummy.{file_type}"
        elif isinstance(file, File) and file.name:
            filename = file.name
    else:
        if isinstance(item, AbstractPDF):
            field_file = item.filepath_local
        elif isinstance(item, Opinion):
            field_file = item.local_path
        elif isinstance(item, Audio):
            field_file = (
                item.local_path_mp3
                if service == "downsize-audio"
                else item.local_path_original_file
            )

        if field_file is not None:
            filename = field_file.name
            file_context = field_file

    # Enter before reopening so failed S3 downloads are also closed.
    with file_context as upload_file:
        if field_file is not None:
            try:
                field_file.open(mode="rb")
            except FileNotFoundError:
                if not isinstance(item, AbstractPDF):
                    raise
                # The file is no longer available, clean it up in DB.
                await clean_up_recap_document_file(item)
                upload_file = None

        upload_context = nullcontext(upload_file)
        if upload_file is None and filepath:
            filename = filepath
            upload_context = open(filepath, "rb")

        with upload_context as upload_file:
            files = (
                {"file": (filename, upload_file)}
                if upload_file is not None
                else None
            )

            async with AsyncClient(
                follow_redirects=True, http2=True
            ) as client:
                req = client.build_request(
                    method=method,
                    url=services[service]["url"],  # type: ignore
                    data=data,
                    files=files,
                    params=params,
                    timeout=services[service]["timeout"],
                )
                return await client.send(req)


@retry(
    ExceptionToCheck=(NetworkError, TimeoutException, NoSuchKey),
    tries=3,
    delay=2,
    backoff=2,
    logger=logger,
)
async def doc_page_count_service(doc: AbstractPDF) -> Response:
    """Call page-count from doctor with retries

    :param doc: the document to count pages
    :return: Response object
    """
    try:
        response = await microservice(
            service="page-count",
            item=doc,
        )
        return response
    except ClientError as error:
        if error.response["Error"]["Code"] == "NoSuchKey":
            raise NoSuchKey("Key not found: The specified key does not exist.")
        raise error


@retry(
    ExceptionToCheck=(NetworkError, TimeoutException, NoSuchKey),
    tries=3,
    delay=2,
    backoff=2,
    logger=logger,
)
async def check_redactions_service(rd: RECAPDocument) -> Response:
    """Call redaction check from doctor with retries

    Uses X-Ray to detect bad redactions (text visible under redaction boxes).

    :param rd: The RECAPDocument to check for bad redactions
    :return: Response object with redaction data
    """
    try:
        return await microservice(service="check-redactions", item=rd)
    except ClientError as error:
        if error.response["Error"]["Code"] == "NoSuchKey":
            raise NoSuchKey("Key not found: The specified key does not exist.")
        raise error
