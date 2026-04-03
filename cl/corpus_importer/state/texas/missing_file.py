from lxml import html


def is_missing_file_page(html_string: str | bytes) -> bool:
    """Check if a TAMES page is a 'File not found' error page.

    :param html_string: raw HTML string or bytes
    :return: True if the page contains the TAMES missing file error
    """
    tree = html.fromstring(html_string)
    error_span = tree.xpath('//*[@id="ctl00_ContentPlaceHolder1_lblError"]')
    if not error_span:
        return False
    text = error_span[0].text_content().strip()
    return text == "File not found."
