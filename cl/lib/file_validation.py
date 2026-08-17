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

# A ceiling to prevent resource exhaustion, not a limit legitimate uploads
# should ever approach. The biggest PACER documents are a few hundred MB.
MAX_UPLOAD_SIZE = 500 * 1024 * 1024  # 500 MB

# Every PDF begins with this header (ISO 32000-1, § 7.5.2).
PDF_MAGIC_NUMBER = b"%PDF-"

# Built without `filesizeformat`, which uses non-breaking spaces that would
# be escaped in API error responses.
FILE_TOO_LARGE_MESSAGE = (
    f"The file is too large. The maximum upload size is "
    f"{MAX_UPLOAD_SIZE // 1024 // 1024} MB."
)
NOT_A_PDF_MESSAGE = (
    "The file is not a PDF. Its contents must begin with the PDF header."
)


def content_is_pdf(f: File) -> bool:
    """Check whether a file's contents are a PDF.

    Only the header is read, so this is cheap enough to call on files of any
    size. The file is rewound afterwards, so callers can read it as usual.

    :param f: The file to check.
    :return: True if the file begins with the PDF magic number.
    """
    f.seek(0)
    header = f.read(len(PDF_MAGIC_NUMBER))
    f.seek(0)
    return header == PDF_MAGIC_NUMBER


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
        raise ValidationError(FILE_TOO_LARGE_MESSAGE)
