from lxml import html
from lxml.html import HtmlElement


def is_missing_file_page(html_string: str | bytes) -> bool:
    """Check if a TAMES page is a 'File not found' error page.

    :param html_string: raw HTML string or bytes
    :return: True if the page contains the TAMES missing file error
    """
    tree = html.fromstring(html_string)
    results = tree.xpath('//*[@id="ctl00_ContentPlaceHolder1_lblError"]')
    if not isinstance(results, list) or not results:
        return False
    element = results[0]
    if not isinstance(element, HtmlElement):
        return False
    return element.text_content().strip() == "File not found."
