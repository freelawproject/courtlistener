from django.apps import AppConfig


class CorpusImporterConfig(AppConfig):
    name = "cl.corpus_importer"

    def ready(self):
        # Implicitly connect a signal handlers decorated with @receiver.
        from cl.corpus_importer import signals
