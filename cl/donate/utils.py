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
    "donation_thanks": {
        "subject": "Thanks for your donation to Free Law Project!",
        "body": (
            "Hello %s,\n\n"
            "Thank you for your donation of $%0.2f to Free "
            "Law Project. We are currently using donations like yours "
            "for a variety of important projects that would never exist "
            "without your help.\n\n"
            "We are a federally-recognized 501(c)(3) public charity "
            "and a California non-profit public benefit corporation. "
            "Our EIN is %s. This letter may serve as a record of your "
            "donation. No goods or services were provided, in whole or "
            "in part, for this contribution.\n\n"
            "If you have any questions about your donation, please "
            "don't hesitate to get in touch.\n\n"
            "Thanks again,\n\n"
            "Michael Lissner and Brian Carver\n"
            "Founders of Free Law Project\n"
            "https://free.law/contact/"
        ),
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
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
    "payment_thanks": {
        "subject": "Receipt for your payment to Free Law Project",
        "body": (
            "Dear %s,\n\n"
            "Your payment of $%0.2f was successfully charged with "
            "charge ID %s.\n\n"
            "If you have any questions about this payment or need any "
            "help, please contact us at info@free.law. Thank you for "
            "supporting our work!\n\n"
            "Michael Lissner and Brian Carver\n"
            "Founders of Free Law Project\n"
            "https://free.law/contact/"
        ),
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "badge_thanks": {
        "subject": "Thanks for becoming a Free Law Project supporter!",
        "body": (
            "Dear %s,\n\n"
            "Your decision to support Free Law Project is one you won't "
            "regret. We are a small non-profit that is working hard to "
            "make the legal ecosystem more fair, open, and competitive. "
            "Your ongoing support of Free Law Project allows us to "
            "continue making high quality legal data and tools widely "
            "available.\n\n"
            "Simply put, we would not be able to do our work without "
            "your help and that of others like you.\n\n"
            "As a thank you, over the next few business days, we will "
            "work with Justia to upgrade your profile with the Free Law "
            "Project supporter badge. Watch for it soon!\n\n"
            "We are a federally-recognized 501(c)(3) public charity "
            "and a California non-profit public benefit corporation. "
            "Our EIN is %s. This letter may serve as a record of your "
            "donation. No goods or services were provided, in whole or "
            "in part, for this contribution.\n\n"
            "If you have any questions about your donation or need any "
            "help, please contact us at info@free.law. Thank you for "
            "supporting our work!\n\n"
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
        "processing your card. As a result, unfortunately, we have disabled "
        "this monthly contribution.\n\n"
        "You were donating $%0.2f each month. The easiest way to fix this is "
        "to set up a new monthly contribution, here:\n\n"
        "    https://www.courtlistener.com%s?amount_other=%0.2f\n\n"
        "Would you mind setting that up again so that your donations and "
        "other services keep working properly?\n\n"
        "Sorry for the hassle. Hopefully this isn't too much trouble to fix, "
        "and thank you for supporting Free Law Project!\n\n"
        "Thanks again,\n\n\n"
        "Free Law Project\n"
        "https://free.law/contact/",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "admin_donation_report": {
        "subject": "$%s were donated by monthly donors today",
        "body": "The following monthly donors contributed a total of $%s:\n\n "
        "%s\n\n"
        "(Note that some of these charges still can fail to go "
        "through.)",
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "to": [a[1] for a in settings.MANAGERS],
    },
    "admin_big_donation_fyi": {
        "body": "Just got a donation of $%0.2f from %s %s, with email %s.",
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "to": [a[1] for a in settings.MANAGERS],
    },
}


def send_big_donation_email(
    donation: Donation,
    payment_type: str,
    recurring: bool = False,
) -> None:
    """Send an email if it's a big donation

    :param donation: The donation object to process
    :param payment_type: A payment type in the PAYMENT_TYPES object
    :param recurring: Whether it's a recurring payment
    :return: None
    """
    user = donation.donor
    amount = donation.amount

    if payment_type != PAYMENT_TYPES.DONATION:
        return

    big_recurring = recurring and amount > 100
    big_one_time = not recurring and amount > 500
    if big_recurring or big_one_time:
        if recurring:
            subject = f"Got big recurring donation of ${amount:0.2f}"
        else:
            subject = f"Got big non-recurring donation of ${amount:0.2f}"

        email = emails["admin_big_donation_fyi"]
        send_mail(
            subject,
            email["body"]
            % (
                amount,
                user.first_name,
                user.last_name,
                user.email,
            ),
            email["from_email"],
            email["to"],
        )


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
    if recurring:
        if payment_type == PAYMENT_TYPES.DONATION:
            email = emails["donation_thanks_recurring"]
            body = email["body"] % (
                user.first_name,
                donation.amount,
                settings.EIN_SECRET,  # type: ignore
            )
            send_mail(
                email["subject"], body, email["from_email"], [user.email]
            )
        elif payment_type == PAYMENT_TYPES.BADGE_SIGNUP:
            email = emails["badge_thanks"]
            body = email["body"] % (user.first_name, settings.EIN_SECRET)  # type: ignore
            send_mail(
                email["subject"], body, email["from_email"], [user.email]
            )
    else:
        if payment_type == PAYMENT_TYPES.DONATION:
            email = emails["donation_thanks"]
            body = email["body"] % (
                user.first_name,
                donation.amount,
                settings.EIN_SECRET,  # type: ignore
            )
            send_mail(
                email["subject"], body, email["from_email"], [user.email]
            )
        elif payment_type == PAYMENT_TYPES.PAYMENT:
            email = emails["payment_thanks"]
            body = email["body"] % (
                user.first_name,
                donation.amount,
                donation.pk,
            )
            send_mail(
                email["subject"], body, email["from_email"], [user.email]
            )


def send_failed_subscription_email(m_donation: MonthlyDonation) -> None:
    """Send an email to the user to tell them their subscription failed.

    m_donation: The MonthlyDonation object that failed.
    """
    email = emails["user_bad_subscription"]
    body = email["body"] % (
        m_donation.donor.first_name,
        m_donation.monthly_donation_amount,
        "https://donate.free.law/forms/supportflp",
        m_donation.monthly_donation_amount,
    )
    send_mail(
        email["subject"], body, email["from_email"], [m_donation.donor.email]
    )


class TotalResponseType(TypedDict):
    total: Optional[Decimal]
    last_year: Optional[Decimal]


def get_donation_totals_by_email(email: str) -> TotalResponseType:
    """Get the total donations for somebody if they've made any

    :return Dict with None for each value if no user, else the amount
    """
    profiles = UserProfile.objects.filter(user__email=email)
    if len(profiles) == 0:
        return {"total": None, "last_year": None}

    total = Decimal(0)
    last_year = Decimal(0)
    for profile in profiles:
        # One email address can have more than one profile (sigh). Just add 'em
        # all up.
        total += profile.total_donated
        last_year += profile.total_donated_last_year
    return {"total": total, "last_year": last_year}
