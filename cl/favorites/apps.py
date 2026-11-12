"""Django app configuration for favorites."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """App config for favorites."""

    name = "cl.favorites"

    def ready(self):
        """Connect the favorites signal handlers."""
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.favorites import signals  # noqa: F401
