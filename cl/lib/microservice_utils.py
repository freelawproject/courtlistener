import json
import logging
from io import BufferedReader
from typing import Any

from asgiref.sync import sync_to_async
from botocore.exceptions import ClientError
from django.conf import settings
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
            item.date_upload = None
            item.is_available = False
        await item.asave()


async def microservice(
    service: str,
    method: str = "POST",
    item: AbstractPDF | Opinion | Audio | None = None,
    file: BufferedReader | None = None,
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

    :param service: The service to call
    :param method: The method to use (defaults to POST)
    :param item: The document as a db object
    :param file: The file as a byte array
    :param file_type: The sometimes you just need the extension of the file
    :param filepath: The filepath of the file
    :param data: The data to send
    :param params: The params to send
    :return: The response from the microservice
    """

    services = settings.MICROSERVICE_URLS

    files = None
    # Add file from filepath
    if filepath:
        files = {"file": (filepath, open(filepath, "rb"))}

    # Handle our documents based on the type of model object
    # Sadly these are not uniform
    if item:
        if isinstance(item, AbstractPDF):
            try:
                files = {
                    "file": (
                        item.filepath_local.name,
                        item.filepath_local.open(mode="rb"),
                    )
                }
            except FileNotFoundError:
                # The file is no longer available, clean it up in DB
                await clean_up_recap_document_file(item)
        elif isinstance(item, Opinion):
            files = {
                "file": (
                    item.local_path.name,
                    item.local_path.open(mode="rb"),
                )
            }
        elif isinstance(item, Audio):
            match service:
                case "downsize-audio":
                    files = {
                        "file": (
                            item.local_path_mp3.name,
                            item.local_path_mp3.open(mode="rb"),
                        )
                    }
                case _:
                    files = {
                        "file": (
                            item.local_path_original_file.name,
                            item.local_path_original_file.open(mode="rb"),
                        )
                    }
    # Sometimes we will want to pass in a filename and the file bytes
    # to avoid writing them to disk. Filename can often be generic
    # and is used to identify the file extension for our microservices
    if file and file_type:
        files = {"file": (f"dummy.{file_type}", file)}
    elif file:
        files = {"file": ("filename", file)}

    async with AsyncClient(follow_redirects=True, http2=True) as client:
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
