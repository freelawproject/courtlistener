from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "cl.donate"

    def ready(self):
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.donate import signals
