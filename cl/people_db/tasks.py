import subprocess

from django.core.files.base import ContentFile

from cl.celery import app
from cl.people_db.models import FinancialDisclosure
from cl.search.models import THUMBNAIL_STATUSES, RECAPDocument


def make_png_thumbnail_for_instance(pk, InstanceClass, file_attr,
                                    max_dimension):
    """Abstract function for making a thumbnail for a PDF

    See helper functions below for how to use this in a simple way.

    :param pk: The PK of the item to make a thumbnail for
    :param InstanceClass: The class of the instance
    :param file_attr: The attr where the PDF is located on the item
    :param max_dimension: The longest you want any edge to be
    """
    item = InstanceClass.objects.get(pk=pk)
    command = [
        'pdftoppm',
        '-jpeg',
        getattr(item, file_attr).path,
        # Start and end on the first page
        '-f', '1',
        '-l', '1',
        # Set the max dimension (generally the height). Alas, we can't just
        # set the width, so this is our only hope.
        '-scale-to', str(max_dimension),
    ]

    # Note that pdftoppm adds things like -01.png to the end of whatever
    # filename you give it, which makes using a temp file difficult. But,
    # if you don't give it an output file, it'll send the result to stdout,
    # so that's why we are capturing it here.
    p = subprocess.Popen(command, close_fds=True, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if p.returncode != 0:
        item.thumbnail_status = THUMBNAIL_STATUSES.FAILED
        item.save()
        return item.pk

    item.thumbnail_status = THUMBNAIL_STATUSES.COMPLETE
    filename = '%s.thumb.%s.jpeg' % (pk, max_dimension)
    item.thumbnail.save(filename, ContentFile(stdout))

    return item.pk


@app.task
def make_financial_disclosure_thumbnail_from_pdf(pk):
    make_png_thumbnail_for_instance(
        pk=pk,
        InstanceClass=FinancialDisclosure,
        file_attr='filepath',
        max_dimension=350,
    )


@app.task
def make_recap_document_thumbnail_from_pdf(pk):
    make_png_thumbnail_for_instance(
        pk=pk,
        InstanceClass=RECAPDocument,
        file_attr='filepath_local',
        max_dimension=1068,
    )


def make_thumb_if_needed(rd):
    """Check if a thumbnail exists. If it does, do not make another. If it
    does not, make it.
    """
    if rd.thumbnail_status == THUMBNAIL_STATUSES.COMPLETE:
        return
    else:
        make_recap_document_thumbnail_from_pdf(rd.pk)
