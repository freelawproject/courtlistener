import subprocess
from tempfile import NamedTemporaryFile
from typing import Any

from django.core.files.base import ContentFile

from cl.lib.models import THUMBNAIL_STATUSES


def make_png_thumbnail_for_instance(
    pk: int,
    klass: Any,
    file_attr: str,
    max_dimension: int,
) -> None:
    """Abstract function for making a thumbnail for a PDF

    This function is a candidate for removal. Do not continue building off this
    function. Instead, use the approach provided by BTE.

    :param pk: The PK of the item to make a thumbnail for
    :param klass: The class of the instance
    :param file_attr: The attr where the PDF is located on the item
    :param max_dimension: The longest you want any edge to be
    """
    item = klass.objects.get(pk=pk)
    with NamedTemporaryFile(
        prefix="thumbnail_",
        suffix=".pdf",
        buffering=0,  # Make sure it's on disk when we try to use it
    ) as tmp:
        tmp.write(getattr(item, file_attr).read())

        command = [
            "pdftoppm",
            "-jpeg",
            tmp.name,
            # Start and end on the first page
            "-f",
            "1",
            "-l",
            "1",
            # Set the max dimension (generally the height). Alas, we can't just
            # set the width, so this is our only hope.
            "-scale-to",
            str(max_dimension),
        ]

        # Note that pdftoppm adds things like -01.jpeg to the end of whatever
        # filename you give it, which makes using a temp file difficult. But,
        # if you don't give it an output file, it'll send the result to stdout,
        # so that's why we are capturing it here.
        p = subprocess.Popen(
            command,
            close_fds=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = p.communicate()

    if p.returncode != 0:
        item.thumbnail_status = THUMBNAIL_STATUSES.FAILED
        item.save()
        return item.pk

    item.thumbnail_status = THUMBNAIL_STATUSES.COMPLETE
    filename = f"{pk}.thumb.{max_dimension}.jpeg"
    item.thumbnail.save(filename, ContentFile(stdout))

    return item.pk
