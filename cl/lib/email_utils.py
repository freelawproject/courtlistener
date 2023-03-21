from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import loader


def make_multipart_email(
    subject: str,
    html_template: str,
    txt_template: str,
    context: dict[str, Any],
    to: list[str],
    from_email: str | None = None,
) -> EmailMultiAlternatives:
    """Composes an email multipart message from the provided data.

    :param subject: The email subject.
    :param html_template: The html template path.
    :param txt_template: The text template path.
    :param to: A list of email addresses to send the email to.
    :param context: A context dict used to render the email message.
    :param from_email: The sender's email address, if not provided uses the
    DEFAULT_FROM_EMAIL defined in settings.
    :return: An EmailMultiAlternatives object.
    """

    if from_email is None:
        from_email = settings.DEFAULT_FROM_EMAIL

    txt = loader.get_template(txt_template).render(context)
    html = loader.get_template(html_template).render(context)
    msg = EmailMultiAlternatives(
        subject,
        txt,
        from_email,
        to,
    )
    msg.attach_alternative(html, "text/html")
    return msg
