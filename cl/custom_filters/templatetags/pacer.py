from django import template

from cl.search.models import RECAPDocument

register = template.Library()


@register.filter
def price(rd: RECAPDocument) -> str:
    """Calculate the PACER price for the document.

    :param rd: The RECAPDocument object.
    :return: The document PACER price.
    """
    if rd.is_free_on_pacer:
        return "0.00"

    if rd.page_count:
        page_count = rd.page_count  # Create a variable for Sentry debugging
        cost = rd.page_count * 0.10
        # cost is uncapped for transcripts
        if (rd.description or "").lower() == "transcript":
            return f"{cost:.2f}"
        return f"{min(3, cost):.2f}"
    return ""
