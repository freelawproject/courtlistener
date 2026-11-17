"""Django app configuration for the corpus importer."""

from django.apps import AppConfig


class CorpusImporterConfig(AppConfig):
    """App config for the corpus importer."""

    name = "cl.corpus_importer"

    def ready(self):
        """Connect the corpus importer signal handlers."""
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.corpus_importer import signals  # noqa: F401
