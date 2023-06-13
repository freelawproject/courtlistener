import html
import re

from django.template import Library
from django.template.defaultfilters import stringfilter
from django.utils.encoding import force_str
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = Library()


@register.filter(is_safe=True, needs_autoescape=True)
def oxford_join(items, conjunction="and", separator=",", autoescape=True):
    """Join together items in a human-readable list

    Also works for django querysets due to not using negative indexing.

    :param items: The list to be joined together.
    :param conjunction: The word to join the items together with (typically
    'and', but can be swapped for another word like 'but', or 'or'.
    :param separator: The separator between the items. Typically a comma.
    :returns s: A string with the items in the list joined together.
    """
    items = list(map(force_str, items))
    if autoescape:
        items = list(map(conditional_escape, items))

    num_items = len(items)
    if num_items == 0:
        s = ""
    elif num_items == 1:
        s = items[0]
    elif num_items == 2:
        s = f"{items[0]} {conjunction} {items[1]}"
    elif num_items > 2:
        # Don't use negative indexing here, even though they'd make this
        # easier. Instead use enumeration to figure out when we're close to the
        # end of the list.
        for i, item in enumerate(items):
            if i == 0:
                # First item
                s = item
            elif i == (num_items - 1):
                # Last item.
                s += f"{separator} {conjunction} {item}"
            else:
                # Items in the middle
                s += f"{separator} {item}"

    return mark_safe(s)


@register.filter(needs_autoescape=True)
@stringfilter
def nbsp(text, autoescape=None):
    """Converts white space to non-breaking spaces

    This creates a template filter that converts white space to html non-breaking
    spaces. It uses conditional_escape to escape any strings that are incoming
    and are not already marked as safe.
    """
    if autoescape:
        esc = conditional_escape
    else:
        # This is an anonymous python identity function. Simply returns the
        # value of x when x is given.
        esc = lambda x: x
    return mark_safe(re.sub(r"\s", "&nbsp;", esc(text.strip())))


@register.filter(needs_autoescape=True)
@stringfilter
def v_wrapper(text, autoescape=None):
    """Wraps every v. in a string with a class of alt"""
    if autoescape:
        esc = conditional_escape
    else:
        esc = lambda x: x
    return mark_safe(
        re.sub(r" v\. ", '<span class="alt"> v. </span>', esc(text))
    )


@register.filter(needs_autoescape=True)
@stringfilter
def underscore_to_space(text, autoescape=None):
    """Removed underscores from text."""
    if autoescape:
        esc = conditional_escape
    else:
        esc = lambda x: x
    return mark_safe(re.sub("_", " ", esc(text)))


@register.filter(needs_autoescape=True)
@stringfilter
def compress_whitespace(text, autoescape=None):
    """Compress whitespace in a string as a browser does with HTML

    For example, this:

        text   foo

        bar    baz

    Becomes: 'text foo bar baz'
    """
    if autoescape:
        esc = conditional_escape
    else:
        esc = lambda x: x
    text = esc(text)
    return mark_safe(" ".join(text.split()))


@register.filter(needs_autoescape=True)
def naturalduration(seconds, autoescape=None, as_dict=False):
    """Convert a duration in seconds to a duration in hours, minutes, seconds.

    For example:
        61 --> 1:01
        3602 --> 1:00:02
    """
    seconds = 0 if not seconds else seconds
    seconds = int(seconds)

    len_day = 86400
    len_hour = 3600
    len_minute = 60

    trunc_s = seconds % len_day % len_hour % len_minute
    trunc_m = seconds % len_day % len_hour // len_minute
    trunc_h = seconds % len_day // len_hour
    trunc_d = seconds // len_day

    if as_dict:
        return {
            "d": trunc_d,
            "h": trunc_h,
            "m": trunc_m,
            "s": trunc_s,
        }
    else:
        duration = "%02d:%02d:%02d:%02d" % (trunc_d, trunc_h, trunc_m, trunc_s)
        trimmed_duration = duration.lstrip("0:")
        if len(trimmed_duration) == 0:
            # It was ALL trimmed away.
            trimmed_duration = "0"

        return mark_safe(trimmed_duration)


@register.filter(is_safe=True)
def OR_join(queryset):
    """Take the input queryset, and return its PKs joined by ' OR '

    This is a one-liner, but you can't do this kind of thing in a template.
    """
    return " OR ".join([str(item.pk) for item in queryset])


@register.filter(is_safe=True)
def best_case_name(obj):
    """Take an object and return the highest quality case name possible.

    In general, this means returning the fields in an order like:

        - case_name
        - case_name_full
        - case_name_short

    Assumes that the object passed in has all of those attributes.
    """
    if obj.case_name:
        return obj.case_name
    elif obj.case_name_full:
        return obj.case_name_full
    else:
        return obj.case_name_short


@register.filter(is_safe=True)
def uniq(iterable):
    """Take an iterable and make it unique. Sorting is not maintained."""
    return list(set(iterable))


@register.filter(needs_autoescape=True)
@stringfilter
def read_more(s, show_words, autoescape=True):
    """Split text after so many words, inserting a "more" link at the end.

    Relies on JavaScript to react to the link being clicked and on classes
    found in Bootstrap to hide elements.
    """
    show_words = int(show_words)
    if autoescape:
        esc = conditional_escape
    else:
        esc = lambda x: x
    words = esc(s).split()

    if len(words) <= show_words:
        return s

    insertion = (
        # The see more link...
        '<span class="read-more">&hellip;'
        '    <a href="#">'
        '        <i class="fa fa-plus-square gray" title="Show All"></i>'
        "    </a>"
        "</span>"
        # The call to hide the rest...
        '<span class="more hidden">'
    )

    # wrap the more part
    words.insert(show_words, insertion)
    words.append("</span>")
    return mark_safe(" ".join(words))


@register.filter(is_safe=True)
def html_decode(value):
    """Decode unicode HTML entities."""
    return html.unescape(value)
