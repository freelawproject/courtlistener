"""Model-level enforcement for OAuth Application redirect URIs.

``ALLOWED_REDIRECT_URI_SCHEMES`` includes ``http`` so native-app loopback
redirects (RFC 8252 §7.3) work. That setting is scheme-only and does not
restrict non-loopback hosts, which means an admin could otherwise register
an Application with ``http://attacker.example.com/cb``. The DCR serializer
rejects that, but admin-created apps bypass the serializer — so the same
rule is enforced here at ``pre_save`` for any save path (admin, shell,
direct ORM).
"""

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver
from oauth2_provider.models import get_application_model

from cl.oauth.api_serializers import check_redirect_uri

Application = get_application_model()


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
