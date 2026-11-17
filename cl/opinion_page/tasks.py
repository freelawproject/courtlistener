import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.template import loader

from cl.celery_init import app
from cl.lib.storage import IncrementingAWSMediaStorage
from cl.opinion_page.utils import (
    generate_docket_pdf_zip_data,
    get_available_recap_documents,
)
from cl.search.models import Docket


@app.task(ignore_result=True)
def build_and_email_docket_pdf_zip(docket_id: int, user_id: int) -> None:
    """Build a zip of a docket's available PDFs and email the user a link.

    Used for dockets with more available documents than
    ``settings.MAX_DOCKET_PDF_ZIP_DOCUMENTS_SYNC``, where building the zip
    inline in the request/response cycle would be too slow.

    :param docket_id: The docket whose available PDFs should be zipped.
    :param user_id: The user who requested the download and should receive
        the email.
    """
    docket = Docket.objects.get(pk=docket_id)
    user = User.objects.get(pk=user_id)
    recap_documents = get_available_recap_documents(docket_id)

    zip_content = generate_docket_pdf_zip_data(docket, recap_documents)
    if zip_content is None:
        return

    storage = IncrementingAWSMediaStorage()
    zip_path = storage.save(
        f"recap/bulk-pdfs/{docket_id}-{uuid.uuid4().hex}.zip",
        ContentFile(zip_content),
    )
    download_url = storage.url(zip_path)

    txt_template = loader.get_template("docket_pdf_zip_email.txt")
    email_context = {
        "username": user.username,
        "case_name": docket.case_name,
        "download_url": download_url,
    }
    message = EmailMessage(
        subject="Your Case's PDFs are Ready to Download",
        body=txt_template.render(email_context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.send(fail_silently=False)
