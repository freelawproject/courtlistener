"""Model-level enforcement for OAuth Application redirect URIs.

``ALLOWED_REDIRECT_URI_SCHEMES`` includes ``http`` so native-app loopback
redirects (RFC 8252 §7.3) work. That setting is scheme-only and does not
restrict non-loopback hosts, which means an admin could otherwise register
an Application with ``http://attacker.example.com/cb``. The rule is
enforced here at ``pre_save`` so it holds for any save path (admin, shell,
direct ORM).
"""

import ipaddress
from typing import Any
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver
from oauth2_provider.models import get_application_model

Application = get_application_model()

# Hosts that are allowed as ``http://`` redirect targets. Everything
# else must use ``https://``. See RFC 8252 section 7.3 ("Loopback
# Interface Redirection").
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _is_loopback_host(host: str) -> bool:
    """Return True if ``host`` is a loopback interface per RFC 8252."""
    host = host.strip("[]").lower()
    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_redirect_uri(uri: str) -> str | None:
    """Return an error message if ``uri`` is not an acceptable redirect
    target, else ``None``.

    Acceptable: any ``https://`` URI with a host, or an ``http://`` URI
    whose host is a loopback address (RFC 8252 §7.3).
    """
    parsed = urlparse(uri)
    if parsed.scheme == "https":
        if not parsed.netloc:
            return f"redirect_uri missing host: {uri}"
        return None
    if parsed.scheme == "http":
        if not parsed.hostname or not _is_loopback_host(parsed.hostname):
            return (
                "http:// redirect_uris are only permitted for "
                f"loopback addresses (got {uri})"
            )
        return None
    return f"unsupported redirect_uri scheme: {uri}"


@receiver(pre_save, sender=Application)
def enforce_redirect_uri_policy(
    sender: type, instance: Any, **kwargs: Any
) -> None:
    if not instance.redirect_uris:
        return
    for uri in instance.redirect_uris.split():
        error = check_redirect_uri(uri)
        if error:
            raise ValidationError(error)
