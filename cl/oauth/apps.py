from django.apps import AppConfig


class OAuthConfig(AppConfig):
    name = "cl.oauth"
    verbose_name = "OAuth"

    def ready(self) -> None:
        from cl.oauth import signals  # noqa: F401
