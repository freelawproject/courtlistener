from django.apps import AppConfig


class SSOConfig(AppConfig):
    """The single sign-on app."""

    name = "cl.sso"
    verbose_name = "Single sign-on"

    def ready(self) -> None:
        """Connect the app's signal handlers."""
        from cl.sso import signals  # noqa: F401
