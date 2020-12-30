import requests
from django.conf import settings
from django.core.files.base import ContentFile

from cl.celery_init import app
from cl.lib.models import THUMBNAIL_STATUSES
from cl.scrapers.transformer_extractor_utils import generate_thumbnail


@app.task
def make_financial_disclosure_thumbnail_from_pdf(pk: int) -> None:
    """Generate Thumbnail and save to AWS

    Attempt to generate thumbnail from PDF and save to AWS.

    :param pk: PK of disclosure in database
    :return: None
    """
    from cl.disclosures.models import FinancialDisclosure

    disclosure = FinancialDisclosure.objects.get(pk=pk)
    pdf_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{disclosure.filepath}"
    pdf_content = requests.get(url=pdf_url, timeout=2).content

    thumbnail_content = generate_thumbnail(pdf_content)
    if thumbnail_content is not None:
        disclosure.thumbnail_status = THUMBNAIL_STATUSES.COMPLETE
        disclosure.thumbnail.save(None, ContentFile(thumbnail_content))
    else:
        disclosure.thumbnail_status = THUMBNAIL_STATUSES.FAILED
        disclosure.save()
