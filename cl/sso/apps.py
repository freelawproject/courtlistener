from django.apps import AppConfig


class SSOConfig(AppConfig):
    name = "cl.sso"
    verbose_name = "Single sign-on"

    def ready(self) -> None:
        # Connect the signal handlers decorated with @receiver.
        from cl.sso import signals  # noqa: F401
