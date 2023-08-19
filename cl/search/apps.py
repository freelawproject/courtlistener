from django.apps import AppConfig


class SearchConfig(AppConfig):
    name = "cl.search"

    def ready(self):
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.search import signals
