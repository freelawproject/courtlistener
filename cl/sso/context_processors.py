from django.http import HttpRequest


def allauth_pages_are_private(request: HttpRequest) -> dict[str, bool]:
    """Mark the pages allauth's own views render as private.

    CourtListener's base templates require every page to say whether search
    engines may index it (the ``private`` variable). allauth's views, such
    as the SSO login confirmation and the cancelled and error pages, don't
    know about that, so this supplies it for them. Sign-in pages shouldn't
    be indexed. Pages from CourtListener's own views are left alone.

    :param request: The request being rendered.
    :return: ``{"private": True}`` for allauth views, else nothing.
    """
    match = getattr(request, "resolver_match", None)
    if match and match.func.__module__.startswith("allauth."):
        return {"private": True}
    return {}
