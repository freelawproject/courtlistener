"""Django app configuration for OAuth."""

from django.apps import AppConfig


class OAuthConfig(AppConfig):
    """App config for OAuth."""

    name = "cl.oauth"
    verbose_name = "OAuth"

    def ready(self) -> None:
        """Connect the OAuth signal handlers."""
        from cl.oauth import signals  # noqa: F401
