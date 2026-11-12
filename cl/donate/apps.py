"""Django app configuration for donations."""

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """App config for donations."""

    name = "cl.donate"

    def ready(self):
        """Connect the donation signal handlers."""
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.donate import signals  # noqa: F401
