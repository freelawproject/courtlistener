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

    :param url: The URL to parse.
    :raises: ValidationError: If the input URL is invalid.
    :return: The parsed URL.
    """
    ada_url = URL(url, base=BASE_URL)
    return ada_url.href.replace(BASE_URL, "")


def get_redirect_or_login_url(request: HttpRequest, field_name: str) -> str:
    """Get the redirect if it's safe, or send the user to the login page

    :param request: The HTTP request
    :param field_name: The field where the redirect is located
    :return: Either the value requested or the default LOGIN_REDIRECT_URL, if
    a sanity or security check failed.
    """
    url = request.GET.get(field_name, "")
    if not url:
        return settings.LOGIN_REDIRECT_URL

    try:
        cleaned_url = parse_url_with_ada(url)
    except ValueError:
        return settings.LOGIN_REDIRECT_URL

    is_safe = is_safe_url(cleaned_url, request)
    if not is_safe:
        return settings.LOGIN_REDIRECT_URL
    return cleaned_url


def get_redirect_or_404(request: HttpRequest, field_name: str) -> str:
    """Get the redirect if safe, or throw a 404

    :param request: The HTTP request
    :param field_name: The field where the redirect is located
    :return: The URL if it was safe
    """
    url = request.GET.get(field_name, "")
    if not url:
        raise Http404("No URL to redirect to.")

    try:
        cleaned_url = parse_url_with_ada(url)
    except ValueError:
        raise Http404(f"Unsafe redirect URL: {url}")

    is_safe = is_safe_url(cleaned_url, request)
    if not is_safe:
        raise Http404(f"Unsafe redirect URL: {url}")
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
