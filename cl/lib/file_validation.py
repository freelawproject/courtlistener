"""Validation helpers for files uploaded by users.

Uploads arrive from the RECAP API and from the court partner upload forms,
so both their size and their contents are attacker-controlled: a caller can
name a file `opinion.pdf`, fill it with anything at all, and make it as big
as they like. Check the size before anything reads the file into memory, and
check the magic number rather than trusting the file's name.

Not to be confused with the PDF checks used on downloads --
`juriscraper.pacer.utils.is_pdf` and `cl.corpus_importer.tasks.is_pdf` --
which read the Content-Type header of a `requests.Response`. A header is a
claim by whoever sent it, which is fine for a server we chose to fetch
from, but not for a file a user handed us.
"""

from django.core.exceptions import ValidationError
from django.core.files import File
from django.template.defaultfilters import filesizeformat

# A ceiling to prevent resource exhaustion, not a limit legitimate uploads
# should ever approach. The biggest PACER documents are a few hundred MB.
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB

PDF_MAGIC_NUMBER = b"%PDF-"

# The spec puts the magic number at byte zero, but plenty of PDFs in the
# wild carry junk ahead of it, and readers accept them: Acrobat looks for
# the header within the first 1024 bytes, and so does doctor's Magika
# fallback. Match that, so we don't reject documents the rest of the stack
# is happy to read.
PDF_HEADER_SEARCH_BYTES = 1024

NOT_A_PDF_MESSAGE = (
    "The file is not a PDF. Its contents must start with the PDF header."
)


def file_too_large_message() -> str:
    """Return the error message for an upload over `MAX_UPLOAD_SIZE`.

    A function rather than a constant because `filesizeformat` translates
    its units, which Django cannot do at import time.

    :return: The message, naming the limit in human terms.
    """
    return (
        f"The file is too large. The maximum upload size is "
        f"{filesizeformat(MAX_UPLOAD_SIZE)}."
    )


def content_is_pdf(f: File) -> bool:
    """Check whether a file's contents are a PDF.

    Only the start of the file is read, so this is cheap to call on files of
    any size. The file is left at the position it arrived at, even if the
    read raises, so callers can read it afterwards.

    :param f: The file to check.
    :return: True if the file carries the PDF magic number near its start.
    """
    position = f.tell()
    try:
        f.seek(0)
        return PDF_MAGIC_NUMBER in f.read(PDF_HEADER_SEARCH_BYTES)
    finally:
        f.seek(position)


def is_too_large(f: File) -> bool:
    """Check whether a file exceeds the maximum upload size.

    :param f: The file to check.
    :return: True if the file is larger than `MAX_UPLOAD_SIZE`.
    """
    return f.size is not None and f.size > MAX_UPLOAD_SIZE


def validate_file_size(f: File) -> None:
    """Reject uploads larger than `MAX_UPLOAD_SIZE`.

    Written for use in a Django form field's `validators` list so that it
    runs before the form's `clean_<field>` method, which may read the whole
    file into memory.

    :param f: The file to check.
    :return: None
    :raises ValidationError: If the file is over the size limit.
    """
    if is_too_large(f):
        raise ValidationError(file_too_large_message())
