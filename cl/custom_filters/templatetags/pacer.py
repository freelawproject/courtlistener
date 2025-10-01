from django import template

from cl.search.models import RECAPDocument

register = template.Library()


@register.filter
def price(rd: RECAPDocument) -> str:
    """Calculate the PACER price for the document.

    :param rd: The RECAPDocument object.
    :return: The document PACER price.
    """
    PACER_COST_CAP = 3
    PACER_COST_PER_PAGE = 0.10

    if rd.is_free_on_pacer:
        return "0.00"

    if rd.page_count:
        page_count = rd.page_count  # Create a variable for Sentry debugging
        cost = rd.page_count * PACER_COST_PER_PAGE
        # cost is uncapped for transcripts
        if (
            cost <= PACER_COST_CAP
            or (rd.description or "").lower() == "transcript"
        ):
            return f"{cost:.2f}"
        else:
            return f"{PACER_COST_CAP:.2f}"
    return ""
