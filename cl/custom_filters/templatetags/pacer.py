from django import template

register = template.Library()


@register.filter
def price(rd):
    if rd.is_free_on_pacer:
        return "0.00"

    if rd.page_count:
        cost = rd.page_count * 0.10
        return "{:.2f}".format(min(3, cost))
    return ""
