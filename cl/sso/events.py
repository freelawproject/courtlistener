import hashlib
import hmac

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpRequest

from cl.lib.ratelimiter import get_viewer_ip
from cl.sso.models import AuthEvent, SSOConnection


def hash_identifier(identifier: str) -> str:
    """Hash a submitted username or address for the audit log.

    Keyed with SECRET_KEY, so the log can show repeated attempts against
    the same identifier without anybody being able to reverse the hash by
    hashing a list of addresses.

    :param identifier: What somebody typed.
    :return: A hex digest.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(),
        identifier.strip().lower().encode(),
        hashlib.sha256,
    ).hexdigest()


def record_auth_event(
    *,
    request: HttpRequest | None,
    method: str,
    outcome: str,
    user: User | None = None,
    identifier: str = "",
    connection: SSOConnection | None = None,
    detail: str = "",
) -> AuthEvent:
    """Write one sign-in event to the audit log.

    :param request: The request, used for the viewer's IP address.
    :param method: An ``AuthMethod`` value.
    :param outcome: An ``AuthOutcome`` value.
    :param user: The account involved, if known.
    :param identifier: The submitted identifier, stored only as a hash and
    only when no account is known.
    :param connection: The SSO connection involved, if any.
    :param detail: A short note for reviewers. Never put secrets here.
    :return: The saved event.
    """
    ip = get_viewer_ip(request) if request is not None else ""
    if not ip and request is not None:
        ip = request.META.get("REMOTE_ADDR", "")
    return AuthEvent.objects.create(
        user=user,
        identifier_hash=(
            hash_identifier(identifier) if identifier and not user else ""
        ),
        method=method,
        outcome=outcome,
        connection=connection,
        ip_address=ip or None,
        detail=detail[:500],
    )
