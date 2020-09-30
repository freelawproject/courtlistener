from django.core.files.base import ContentFile
from requests import Timeout

from cl.celery_init import app
from cl.lib.bot_detector import is_og_bot
from cl.lib.command_utils import logger
from cl.lib.models import THUMBNAIL_STATUSES
from cl.people_db.models import FinancialDisclosure
from cl.scrapers.transformer_extractor_utils import generate_thumbnail
from cl.search.models import RECAPDocument


def make_png_thumbnail_for_instance(
    pk, InstanceClass, file_attr, max_dimension
):
    """Abstract function for making a thumbnail for a PDF

    See helper functions below for how to use this in a simple way.

    :param pk: The PK of the item to make a thumbnail for
    :param InstanceClass: The class of the instance
    :param file_attr: The attr where the PDF is located on the item
    :param max_dimension: The longest you want any edge to be
    """
    item = InstanceClass.objects.get(pk=pk)
    filepath = getattr(item, file_attr).path

    try:
        thumbnail_resp = generate_thumbnail(filepath)
    except Timeout:
        logger.error("Thumbnail generation failed via timeout.")
    except Exception as e:
        logger.error(
            "Catch all exception occurred during thumbnail generation.  See %s"
            % str(e)
        )
    finally:
        if "thumbnail_resp" not in locals():
            item.thumbnail_status = THUMBNAIL_STATUSES.FAILED
            item.save()
            return item.pk

    item.thumbnail_status = THUMBNAIL_STATUSES.COMPLETE
    filename = "%s.thumb.%s.jpeg" % (pk, max_dimension)
    item.thumbnail.save(filename, ContentFile(thumbnail_resp.content))

    return item.pk


@app.task
def make_financial_disclosure_thumbnail_from_pdf(pk):
    make_png_thumbnail_for_instance(
        pk=pk,
        InstanceClass=FinancialDisclosure,
        file_attr="filepath",
        max_dimension=350,
    )


@app.task
def make_recap_document_thumbnail_from_pdf(pk):
    make_png_thumbnail_for_instance(
        pk=pk,
        InstanceClass=RECAPDocument,
        file_attr="filepath_local",
        max_dimension=1068,
    )


def make_thumb_if_needed(request, rd):
    """Make a thumbnail for a RECAP Document, if needed

    If a thumbnail is needed, can be made and should be made, make one.

    :param request: The request sent to the server
    :param rd: A RECAPDocument object
    """
    needs_thumb = rd.thumbnail_status != THUMBNAIL_STATUSES.COMPLETE
    if all([needs_thumb, rd.has_valid_pdf, is_og_bot(request)]):
        make_recap_document_thumbnail_from_pdf(rd.pk)
        rd.refresh_from_db()
    return rd
