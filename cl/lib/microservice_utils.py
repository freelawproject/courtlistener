from io import BufferedReader

from django.conf import settings
from httpx import AsyncClient, Response

from cl.audio.models import Audio
from cl.lib.search_utils import clean_up_recap_document_file
from cl.search.models import Opinion, RECAPDocument


async def microservice(
    service: str,
    method: str = "POST",
    item: RECAPDocument | Opinion | Audio | None = None,
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
        if type(item) == RECAPDocument:
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
        elif type(item) == Opinion:
            files = {
                "file": (
                    item.local_path.name,
                    item.local_path.open(mode="rb"),
                )
            }
        elif type(item) == Audio:
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
