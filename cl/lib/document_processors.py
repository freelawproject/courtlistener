from PyPDF2 import PdfFileReader
from PyPDF2.utils import PdfReadError


def get_page_count(path, extension):
    """Get the number of pages, if appropriate mimetype.

    :param path: A path to a binary (pdf, wpd, doc, txt, html, etc.)
    :param extension: The extension of the binary.
    :return: The number of pages if possible, else return None
    """
    if extension == 'pdf':
        try:
            reader = PdfFileReader(path)
            return int(reader.getNumPages())
        except (IOError, ValueError, TypeError, KeyError, AssertionError,
                PdfReadError):
            # IOError: File doesn't exist. My bad.
            # ValueError: Didn't get an int for the page count. Their bad.
            # TypeError: NumberObject has no attribute '__getitem__'. Ugh.
            # KeyError, AssertionError: assert xrefstream["/Type"] == "/XRef". WTF?
            # PdfReadError: Something else. I have no words.
            pass
    elif extension == 'wpd':
        # Best solution appears to be to dig into the binary format
        pass
    elif extension == 'doc':
        # Best solution appears to be to dig into the XML of the file
        # itself: http://stackoverflow.com/a/12972502/64911
        pass
    return None
