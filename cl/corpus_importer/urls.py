from django.urls import path

from cl.corpus_importer.views import ca_judges

urlpatterns = [
    path(
        "cleanup-tools/ca-judges/",
        ca_judges,
        name="ca_judges",
    ),
]
