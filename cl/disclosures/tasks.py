from django.apps import apps

from cl.celery_init import app
from cl.people_db.tasks import make_png_thumbnail_for_instance


@app.task
def make_financial_disclosure_thumbnail_from_pdf(pk):
    make_png_thumbnail_for_instance(
        pk=pk,
        InstanceClass=apps.get_model("disclosures", "FinancialDisclosure"),
        file_attr="filepath",
        max_dimension=350,
    )
