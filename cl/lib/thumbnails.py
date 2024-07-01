from typing import Any

from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile

from cl.lib.microservice_utils import microservice
from cl.lib.models import THUMBNAIL_STATUSES


async def make_png_thumbnail_for_instance(
    pk: int,
    klass: Any,
    max_dimension: int,
) -> None:
    """Abstract function for making a thumbnail for a PDF

    This function is a candidate for removal. Do not continue building off this
    function. Instead, use the approach provided by BTE.

    :param pk: The PK of the item to make a thumbnail for
    :param klass: The class of the instance
    :param max_dimension: The longest you want any edge to be
    """
    item = await klass.objects.aget(pk=pk)
    response = await microservice(
        service="generate-thumbnail",
        item=item,
        params={"max_dimension": max_dimension},
    )
    if not response.is_success:
        item.thumbnail_status = THUMBNAIL_STATUSES.FAILED
        await item.asave()
    else:
        item.thumbnail_status = THUMBNAIL_STATUSES.COMPLETE
        filename = f"{pk}.thumb.{max_dimension}.png"
        await sync_to_async(item.thumbnail.save)(
            filename, ContentFile(response.content)
        )
    return item.pk
