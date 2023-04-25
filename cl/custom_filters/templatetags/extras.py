import random

from django import template
from django.core.exceptions import ValidationError
from django.template import Context
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.safestring import SafeString, mark_safe

from cl.search.models import Docket, DocketEntry

register = template.Library()


@register.simple_tag(takes_context=True)
def get_full_host(context, username=None, password=None):
    """Return the current URL with the correct protocol and port.

    No trailing slash.

    :param context: The template context that is passed in.
    :type context: RequestContext
    :param username: A HTTP Basic Auth username to show in the URL
    :type username: str
    :param password: A HTTP Basic Auth password to show in the URL
    :type password: str
    """
    if any([username, password]):
        assert all([username, password]), (
            "If a username is provided, a "
            "password must also be provided and "
            "vice versa."
        )
    r = context.get("request")
    if r is None:
        protocol = "http"
        domain_and_port = "courtlistener.com"
    else:
        protocol = "https" if r.is_secure() else "http"
        domain_and_port = r.get_host()

    return mark_safe(
        "{protocol}://{username}{password}{domain_and_port}".format(
            protocol=protocol,
            username="" if username is None else username,
            password="" if password is None else f":{password}@",
            domain_and_port=domain_and_port,
        )
    )


@register.simple_tag(takes_context=True)
def get_canonical_element(context: Context) -> SafeString:
    href = f"{get_full_host(context)}{context['request'].path}"
    return format_html(
        '<link rel="canonical" href="{}" />',
        href,
    )


@register.simple_tag(takes_context=False)
def granular_date(
    obj, field_name, granularity=None, iso=False, default="Unknown"
):
    """Return the date truncated according to its granularity.

    :param obj: The object to get the value from
    :param field_name: The attribute to be converted to a string.
    :param granularity: The granularity to perform. If None, we assume that
        getattr(obj, 'date_%s_field_name') will work.
    :param iso: Whether to return an iso8601 date or a human readable one.
    :return: A string representation of the date.
    """
    from cl.people_db.models import (
        GRANULARITY_DAY,
        GRANULARITY_MONTH,
        GRANULARITY_YEAR,
    )

    if not isinstance(obj, dict):
        # Convert it to a dict. It's easier to convert this way than from a dict
        # to an object.
        obj = obj.__dict__

    d = obj.get(field_name, None)
    if granularity is None:
        date_parts = field_name.split("_")
        granularity = obj[f"{date_parts[0]}_granularity_{date_parts[1]}"]

    if not d:
        return default
    if iso is False:
        if granularity == GRANULARITY_DAY:
            return date_format(d, format="F j, Y")
        elif granularity == GRANULARITY_MONTH:
            return date_format(d, format="F, Y")
        elif granularity == GRANULARITY_YEAR:
            return date_format(d, format="Y")
    else:
        if granularity == GRANULARITY_DAY:
            return date_format(d, format="Y-m-d")
        elif granularity == GRANULARITY_MONTH:
            return date_format(d, format="Y-m")
        elif granularity == GRANULARITY_YEAR:
            return date_format(d, format="Y")

    raise ValidationError(
        "Fell through date granularity template tag. This could mean that you "
        "have a date without an associated granularity. Did you apply the "
        "validation rules? Is full_clean() getting called in your save() "
        "method?"
    )


@register.filter
def get(mapping, key):
    """Emulates the dictionary get. Useful when keys have spaces or other
    punctuation."""
    return mapping.get(key, "")


@register.simple_tag
def random_int(a: int, b: int) -> int:
    return random.randint(a, b)


# sourced from: https://stackoverflow.com/questions/2272370/sortable-table-columns-in-django
@register.simple_tag
def url_replace(request, value):
    field = "order_by"
    dict_ = request.GET.copy()
    if field in dict_.keys():
        if dict_[field].startswith("-") and dict_[field].lstrip("-") == value:
            dict_[field] = value  # desc to asc
        elif dict_[field] == value:
            dict_[field] = f"-{value}"
        else:  # order_by for different column
            dict_[field] = value
    else:  # No order_by
        dict_[field] = value
    return urlencode(sorted(dict_.items()))


@register.simple_tag
def sort_caret(request, value) -> SafeString:
    current = request.GET.get("order_by", "*UP*")
    caret = '&nbsp;<i class="gray fa fa-angle-up"></i>'
    if current == value or current == f"-{value}":
        if current.startswith("-"):
            caret = '&nbsp;<i class="gray fa fa-angle-down"></i>'
    return mark_safe(caret)


@register.simple_tag
def citation(obj) -> SafeString:
    if isinstance(obj, Docket):
        # Dockets do not have dates associated with them.  This is more
        # of a "weak citation".  It is there to allow people to find the
        # docket
        docket = obj
        date_of_interest = None
        ecf = ""
    elif isinstance(obj, DocketEntry):
        docket = obj.docket
        date_of_interest = obj.date_filed
        ecf = obj.entry_number
    else:
        raise NotImplementedError(f"Object not recongized in {__name__}")

    # We want to build a citation that follows the Bluebook format as much
    # as possible.  For documents from a case that looks like:
    #   name_bb, case_bb, (court_bb date_bb) ECF No. {ecf}"
    # If this is a citation to just a docket then we leave off the ECF number
    # For opinions there is no need as the title of the block IS the citation
    if date_of_interest:
        date_of_interest = date_of_interest.strftime("%b %d, %Y")
    result = f"{docket.case_name}, {docket.docket_number}, ("
    result = result + docket.court.citation_string
    if date_of_interest:
        result = f"{result} {date_of_interest}"
    result = f"{result})"
    if ecf:
        result = f"{result} ECF No. {ecf}"
    return result
