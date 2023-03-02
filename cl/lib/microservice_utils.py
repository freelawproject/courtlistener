from django.conf import settings
from django.db import models
from requests import Request, Response, Session

from cl.audio.models import Audio
from cl.lib.search_utils import clean_up_recap_document_file
from cl.search.models import Opinion, RECAPDocument


def microservice(
    service: str,
    method: str = "POST",
    item: models.Model | None = None,
    file: bytes | None = None,
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

    req = Request(
        method=method,
        url=services[service]["url"],  # type: ignore
    )
    # Add file from filepath
    if filepath:
        with open(filepath, "rb") as f:
            req.files = {"file": (filepath, f.read())}

    # Handle our documents based on the type of model object
    # Sadly these are not uniform
    if item:
        if type(item) == RECAPDocument:
            try:
                with item.filepath_local.open(mode="rb") as local_path:
                    req.files = {
                        "file": (item.filepath_local.name, local_path.read())
                    }
            except FileNotFoundError:
                # The file is no longer available, clean it up in DB
                clean_up_recap_document_file(item)
        elif type(item) == Opinion:
            with item.local_path.open(mode="rb") as local_path:
                req.files = {"file": (item.local_path.name, local_path.read())}
        elif type(item) == Audio:
            with item.local_path_original_file.open(mode="rb") as local_path:
                req.files = {
                    "file": (
                        item.local_path_original_file.name,
                        local_path.read(),
                    )
                }
    # Sometimes we will want to pass in a filename and the file bytes
    # to avoid writing them to disk. Filename can often be generic
    # and is used to identify the file extension for our microservices
    if file and file_type:
        req.files = {"file": (f"dummy.{file_type}", file)}
    elif file:
        req.files = {"file": (f"filename", file)}

    if data:
        req.data = data

    if params:
        req.params = params

    return Session().send(req.prepare(), timeout=services[service]["timeout"])  # type: ignore
