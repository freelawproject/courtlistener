from django.apps import AppConfig


class AlertsConfig(AppConfig):
    name = "cl.alerts"

    def ready(self):
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.alerts import signals
