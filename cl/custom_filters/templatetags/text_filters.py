from django.template import Library
from django.template.defaultfilters import stringfilter
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

import re

register = Library()


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
    return mark_safe(re.sub('\s', '&nbsp;', esc(text.strip())))


@register.filter(needs_autoescape=True)
@stringfilter
def v_wrapper(text, autoescape=None):
    """Wraps every v. in a string with a class of alt"""
    if autoescape:
        esc = conditional_escape
    else:
        esc = lambda x: x
    return mark_safe(
        re.sub(' v\. ', '<span class="alt bold"> v. </span>', esc(text)))


@register.filter(needs_autoescape=True)
@stringfilter
def underscore_to_space(text, autoescape=None):
    """Removed underscores from text."""
    if autoescape:
        esc = conditional_escape
    else:
        esc = lambda x: x
    return mark_safe(re.sub('_', ' ', esc(text)))


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
    return mark_safe(' '.join(text.split()))


@register.filter(needs_autoescape=True)
def naturalduration(seconds, autoescape=None, as_dict=False):
    """Convert a duration in seconds to a duration in hours, minutes, seconds.

    For example:
        61 --> 1:01
        3602 --> 1:00:02
    """
    if seconds is None:
        seconds = 0
    seconds = int(seconds)

    if autoescape:
        esc = conditional_escape
    else:
        esc = lambda x: x

    len_day = 86400
    len_hour = 3600
    len_minute = 60

    trunc_s = seconds % len_day % len_hour % len_minute
    trunc_m = seconds % len_day % len_hour / len_minute
    trunc_h = seconds % len_day / len_hour
    trunc_d = seconds / len_day

    if as_dict:
        return {
            'd': trunc_d,
            'h': trunc_h,
            'm': trunc_m,
            's': trunc_s,
        }
    else:
        duration = '%02d:%02d:%02d:%02d' % (trunc_d, trunc_h, trunc_m, trunc_s)
        trimmed_duration = duration.lstrip('0:')
        if len(trimmed_duration) == 0:
            # It was ALL trimmed away.
            trimmed_duration = '0'

        return mark_safe(trimmed_duration)


@register.filter(is_safe=True)
def OR_join(queryset):
    """Take the input queryset, and return its PKs joined by ' OR '

    This is a one-liner, but you can't do this kind of thing in a template.
    """
    return ' OR '.join([str(item.pk) for item in queryset])


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
