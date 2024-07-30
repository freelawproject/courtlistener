from ada_url import URL
from django.conf import settings
from django.http import Http404, HttpRequest
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

BASE_URL = (
    "https://www.courtlistener.com"
    if not settings.DEVELOPMENT
    else "http://localhost:8000"
)


def parse_url_with_ada(url: str) -> str:
    """Parses a URL using the `URL` class from the `Ada`.

    Handles relative paths by adding the `BASE_URL` to the class constructor.
    If the URL is already absolute, this step has no effect. Extracts the
    parsed URL from the `href` attribute and attempts to remove the `BASE_URL`
    if it was added previously.

    Returns an empty string If the input URL is invalid or cannot be parsed.

    :param url: The URL to parse.
    :return: The parsed URL or an empty string if the input URL is invalid or
    cannot be parsed.
    """
    if not url:
        return ""

    try:
        ada_url = URL(url, base=BASE_URL)
        return ada_url.href.replace(BASE_URL, "")
    except ValueError:
        return ""


def get_redirect_or_abort(
    request: HttpRequest, redirect_field_name: str, throw_404: bool = False
) -> str:
    """
    Retrieves a safe redirect URL from the request or returns the login URL.

    This function checks for a redirect URL in both the POST and GET data of
    the provided request object. It then parses the retrieved URL using the
    `parse_url_with_ada` helper and performs safety checks using the
    `is_safe_url` function.

    :param request: The HTTP request object containing potential redirect data.
    :param redirect_field_name: The name of the field containing the redirect
    URL.
    :param throw_404: Whether to raise an Http404 exception for unsafe URLs.
    Defaults to False, in which case it returns the login redirect URL.
    :raises Http404: If `throw_404` is True and the redirect URL is unsafe.
    :return: The safe, parsed redirect URL if found, otherwise the configured
    login URL.
    """
    redirect_url = request.POST.get(
        redirect_field_name,
        request.GET.get(redirect_field_name, ""),
    )
    cleaned_url = parse_url_with_ada(redirect_url)
    safe = is_safe_url(cleaned_url, request)
    if not safe:
        if throw_404:
            raise Http404("Missing or unsafe redirect URL.")
        return settings.LOGIN_REDIRECT_URL
    return cleaned_url


def is_safe_url(url: str, request: HttpRequest) -> bool:
    """Check whether a redirect URL is safe

    Much of this code was grabbed from Django:

    1. Prevent open redirect attacks. Imagine getting an email:

      Subject: Your CourtListener account is conformed
      Body: Click here to continue: https://www.courtlistener.com/?next=https://cortlistener.com/evil/thing

    Without proper redirect sanitation, a user might click that link, and get
    redirected to courtlistener.com, which could be a spoof of the real thing.

    1. Prevent illogical redirects. Like, don't let people redirect back to
    the sign-in or register page.

    1. Prevent garbage URLs (like empty ones or ones with spaces)

    1. Prevent dangerous URLs (like JavaScript)

    :param url: The URL to check
    :param request: The user request
    :return True if safe, else False
    """
    sign_in_url = reverse("sign-in") in url
    register_in_url = reverse("register") in url
    no_url = not url
    not_safe_url = not url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )
    return not any([sign_in_url, register_in_url, no_url, not_safe_url])
