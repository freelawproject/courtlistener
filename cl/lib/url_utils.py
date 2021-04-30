from urllib.parse import quote

from django.conf import settings
from django.http import HttpRequest
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def sanitize_redirection(request: HttpRequest) -> str:
    """Security and sanity checks on redirections.

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

    :return: Either the value requested or the default LOGIN_REDIRECT_URL, if
    a sanity or security check failed.
    """
    redirect_to = request.GET.get("next", "")

    # Fixes security vulnerability reported upstream to Django, where
    # whitespace can be provided in the scheme like "java\nscript:alert(bad)"
    redirect_to = quote(redirect_to)
    sign_in_url = reverse("sign-in") in redirect_to
    register_in_url = reverse("register") in redirect_to
    garbage_url = " " in redirect_to
    no_url = not redirect_to
    not_safe_url = not url_has_allowed_host_and_scheme(
        redirect_to,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )
    if any([sign_in_url, register_in_url, garbage_url, no_url, not_safe_url]):
        return settings.LOGIN_REDIRECT_URL
    return redirect_to
