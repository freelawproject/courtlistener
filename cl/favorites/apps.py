from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "cl.favorites"

    def ready(self):
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.favorites import signals
