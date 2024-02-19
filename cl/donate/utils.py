from decimal import Decimal
from typing import Dict, Optional, TypedDict

from django.conf import settings
from django.core.mail import send_mail

from cl.donate.models import PAYMENT_TYPES, Donation, MonthlyDonation
from cl.lib.types import EmailType
from cl.users.models import UserProfile


class PaymentFailureException(Exception):
    def __init__(self, message):
        self.message = message


emails: Dict[str, EmailType] = {
    "donation_thanks_recurring": {
        "subject": "We have received your recurring contribution to Free Law "
        "Project",
        "body": (
            "Dear %s,\n\n"
            "Your recurring donation of $%0.2f was successfully charged "
            "today. Your ongoing support of Free Law Project allows us "
            "to continue making high quality legal data and tools widely "
            "available. We would be unable to do our work without "
            "your help.\n\n"
            "We are a federally-recognized 501(c)(3) public charity "
            "and a California non-profit public benefit corporation. "
            "Our EIN is %s. This letter may serve as a record of your "
            "donation. No goods or services were provided, in whole or "
            "in part, for this contribution.\n\n"
            "If you have any questions about your donation or need any "
            "help disabling this, please contact donate@free.law. "
            "More information about recurring donations can be found here:\n\n"
            "https://www.courtlistener.com/help/donations/#recurring-donations\n\n"
            "Thank you for supporting our work!\n\n"
            "Michael Lissner and Brian Carver\n"
            "Founders of Free Law Project\n"
            "https://free.law/contact/"
        ),
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "user_bad_subscription": {
        "subject": "Your monthly donation to Free Law Project has failed",
        "body": "Dear %s,\n\n"
        "We just attempted to process your recurring donation to Free Law "
        "Project, host of CourtListener and RECAP, but we had an issue "
        "processing your card.\n\n"
        "As a result, unfortunately, we have disabled this monthly contribution.\n\n"
        "We hope you will continue supporting Free Law Project. To do so, "
        "you can either become a member (and enjoy member benefits like swag, "
        "features on CourtListener, and more):\n\n"
        "https://donate.free.law/forms/membership\n\n"
        "Or you can continue being a monthly supporter of our work without a "
        "full membership (more of your money will support our work and you'll "
        "enjoy a greater tax benefit):\n\n"
        "https://donate.free.law/forms/supportflp\n\n"
        "Please let us know if you have any questions, and thank thank you for "
        "supporting Free Law Project!\n\n"
        "Free Law Project\n"
        "https://free.law/contact/",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "admin_monthly_donation_report": {
        "subject": "$%s were donated by monthly donors today",
        "body": "The following monthly donors contributed a total of $%s:\n\n "
        "%s\n\n"
        "(Note that some of these charges still can fail to go "
        "through.)",
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "to": [a[1] for a in settings.MANAGERS],
    },
}


def send_thank_you_email(
    donation: Donation,
    payment_type: str,
    recurring: bool = False,
) -> None:
    """Send an appropriate email for the payment or donation.

    :param donation: The donation object to process
    :param payment_type: A payment type in the PAYMENT_TYPES object
    :param recurring: Whether it's a recurring payment
    :return: None
    """
    user = donation.donor
    if recurring and payment_type == PAYMENT_TYPES.DONATION:
        email = emails["donation_thanks_recurring"]
        body = email["body"] % (
            user.first_name,
            donation.amount,
            settings.EIN_SECRET,  # type: ignore
        )
        send_mail(email["subject"], body, email["from_email"], [user.email])


def send_failed_subscription_email(m_donation: MonthlyDonation) -> None:
    """Send an email to the user to tell them their subscription failed.

    m_donation: The MonthlyDonation object that failed.
    """
    email = emails["user_bad_subscription"]
    send_mail(
        email["subject"],
        email["body"],
        email["from_email"],
        [m_donation.donor.email],
    )
