"""Where Court-PASS files are stored before and after they are published."""

NY_STATE_CODE: str = "ny"

PRIVATE_PREFIX: str = f"responses/dockets/{NY_STATE_CODE}/"
"""Where the scraper leaves the files it downloads, in the private bucket."""


def is_scraped(path: str) -> bool:
    """Whether a stored path names a file the scraper left in the private
    bucket, which is the only kind of path a scrape may report.

    :param path: The path a document's `filepath_local` holds, or a key a
        scrape reported.
    :return: Whether the file is sitting in the scrape bucket.
    """
    return path.startswith(PRIVATE_PREFIX)


def is_published(path: str) -> bool:
    """Whether a stored path names a file in the bucket CourtListener serves.

    A Court-PASS file is either where the scraper left it or where the loader
    published it, so anything stored that is not the former is the latter.
    Deliberately not a check against the published layout itself, which would
    call a file published under a layout since superseded unpublished, and
    leave the loader no reason to move it to the name it now belongs under;
    see `AbstractStateDocument.get_pdf_path`.

    :param path: The path a document's `filepath_local` holds.
    :return: Whether the file is in the bucket CourtListener serves, wherever
        in it. `False` for a document with no file at all.
    """
    return bool(path) and not is_scraped(path)
