"""Django app configuration for users."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """App config for users."""

    name = "cl.users"

    def ready(self):
        """Connect the user signal handlers."""
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.users import signals  # noqa: F401
