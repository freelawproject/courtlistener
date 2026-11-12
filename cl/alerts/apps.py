"""Django app configuration for alerts."""

from django.apps import AppConfig


class AlertsConfig(AppConfig):
    """App config for alerts."""

    name = "cl.alerts"

    def ready(self):
        """Connect the alert signal handlers."""
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.alerts import signals  # noqa: F401
