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


@register.filter
def pacerdash_price(rd: RECAPDocument) -> str:
    if rd.is_free_on_pacer:
        return "0.00"

    if rd.page_count:
        cost = rd.page_count * 0.10
        pacerdash_cost = (min(3, cost) * 1.029) + 0.90
        return f"{pacerdash_cost:.2f}"
    return ""
