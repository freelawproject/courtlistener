from django import template

from cl.search.models import RECAPDocument

register = template.Library()


@register.filter
def price(rd: RECAPDocument) -> str:
    if rd.is_free_on_pacer:
        return "0.00"

    if rd.page_count:
        cost = rd.page_count * 0.10
        return f"{min(3, cost):.2f}"
    return ""
