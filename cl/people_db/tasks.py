import subprocess
from tempfile import NamedTemporaryFile

from django.core.files import File

from cl.celery import app
from cl.people_db.models import FinancialDisclosure
from cl.search.models import THUMBNAIL_STATUSES, RECAPDocument


def make_png_thumbnail_for_instance(pk, InstanceClass, file_attr, width,
                                    tmp_prefix):
    """Abstract function for making a thumbnail for a PDF

    See helper functions below for how to use this in a simple way.

    :param pk: The PK of the item to make a thumbnail for
    :param InstanceClass: The class of the instance
    :param file_attr: The attr where the PDF is located on the item
    :param width: The width in pixels of the desired thumb
    :param tmp_prefix: The prefix to use for the temporary file used during
    thumbnail creation.
    """
    item = InstanceClass.objects.get(pk=pk)
    with NamedTemporaryFile(prefix=tmp_prefix, suffix=".png") as tmp:
        convert = [
            'convert',
            # Only do the first page.
            '%s[0]' % getattr(item, file_attr).path,
            '-resize', '%s' % width,
            # This and the next line handle transparency problems
            '-background', 'white',
            '-alpha', 'remove',
            tmp.name,
        ]
        p = subprocess.Popen(convert, close_fds=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True)
        stdout, stderr = p.communicate()
        if p.returncode != 0:
            item.thumbnail_status = THUMBNAIL_STATUSES.FAILED
            item.save()
            return item.pk

        item.thumbnail_status = THUMBNAIL_STATUSES.COMPLETE
        filename = '%s.thumb.%sw.png' % (pk, width)
        item.thumbnail.save(filename, File(tmp))

        return item.pk


@app.task
def make_financial_disclosure_thumbnail_from_pdf(pk):
    make_png_thumbnail_for_instance(
        pk=pk,
        InstanceClass=FinancialDisclosure,
        file_attr='filepath',
        width=350,
        tmp_prefix='financial_disclosure_',
    )


@app.task
def make_recap_document_thumbnail_from_pdf(pk):
    make_png_thumbnail_for_instance(
        pk=pk,
        InstanceClass=RECAPDocument,
        file_attr='filepath_local',
        width=700,
        tmp_prefix='recap_thumb_',
    )


def make_thumb_if_needed(rd):
    """Check if a thumbnail exists. If it does, do not make another. If it
    does not, make it.
    """
    if rd.thumbnail_status == THUMBNAIL_STATUSES.COMPLETE:
        return
    else:
        make_recap_document_thumbnail_from_pdf(rd.pk)
