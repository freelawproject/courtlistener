from django import template
from django.utils.safestring import mark_safe

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
        assert all([username, password]), ("If a username is provided, a "
                                           "password must also be provided and "
                                           "vice versa.")
    r = context.get('request')
    if r is None:
        protocol = 'http'
        domain_and_port = 'courtlistener.com'
    else:
        protocol = 'https' if r.is_secure() else 'http'
        domain_and_port = r.get_host()

    return mark_safe("{protocol}://{username}{password}{domain_and_port}".format(
        protocol=protocol,
        username='' if username is None else username,
        password='' if password is None else ':' + password + '@',
        domain_and_port=domain_and_port,
    ))
