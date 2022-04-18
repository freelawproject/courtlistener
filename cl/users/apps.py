from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "cl.users"

    def ready(self):
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.users import signals
