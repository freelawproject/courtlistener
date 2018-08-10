from django.conf import settings
from django.core.mail import send_mail
from django.core.urlresolvers import reverse


class PaymentFailureException(Exception):
    def __init__(self, message):
        self.message = message


emails = {
    'donation_thanks': {
        'subject': 'Thanks for your donation to Free Law Project!',
        'body': ('Hello %s,\n\n'
                 
                 'Thanks for your donation of $%0.2f to Free '
                 'Law Project. We are currently using donations like yours '
                 'for a variety of important projects that would never exist '
                 'without your help.\n\n'

                 'We are a federally-recognized 501(c)(3) public charity '
                 'and a California non-profit public benefit corporation. '
                 'Our EIN is %s.\n\n'

                 'If you have any questions about your donation, please '
                 'don\'t hesitate to get in touch.\n\n'

                 'Thanks again,\n\n'
                 'Michael Lissner and Brian Carver\n'
                 'Founders of Free Law Project\n'
                 'https://free.law/contact/'),
        'from': settings.DEFAULT_FROM_EMAIL,
    },
    'donation_thanks_recurring': {
        'subject': 'We have received your recurring contribution to Free Law '
                   'Project',
        'body': ('Dear %s,\n\n'
                 
                 'Your recurring donation of $%0.2f was successfully charged '
                 'today. Your ongoing support of Free Law Project allows us '
                 'to continue making high quality legal data and tools widely '
                 'available. We would be unable to do our work without '
                 'your help.\n\n'
                 
                 'If you have any questions about your donation or need any '
                 'help, please contact us at info@free.law. Thank you for '
                 'supporting our work!\n\n'
                 
                 'Michael Lissner and Brian Carver\n'
                 'Founders of Free Law Project\n'
                 'https://free.law/contact\n\n'
                 
                 'PS: Free Law Project is a U.S. 501(c)(3) non-profit, with '
                 'tax ID of %s. Your gift is tax deductible as allowed by '
                 'law.'),
        'from': settings.DEFAULT_FROM_EMAIL,
    },
    'user_bad_subscription': {
        'subject': "We have disabled your monthly contributions to Free Law "
                   "Project",
        'body': 'Dear %s\n\n'
                
                'We attempted to process your recurring donation to Free Law '
                'Project this morning, but we had an issue processing your '
                'card. It has failed three times now, and as a result, we '
                'have disabled your monthly contributions.\n\n'
                
                'You were donating $%0.2f each month. If you still want to '
                'contribute to Free Law Project, the easiest way to fix this '
                'is to just set up a new monthly contribution, here:\n\n'
                
                '    https://www.courtlistener.com%s\n\n'
                
                'Thank you as always for your continued support, and if you '
                'have any questions or need any help, do not hesitate to '
                'reach out to us.\n\n'
                
                'Thanks again,\n\n'

                'Michael Lissner and Brian Carver\n'
                'Founders of Free Law Project\n'
                'https://free.law/contact/',
        'from': settings.DEFAULT_FROM_EMAIL,
    },
    'admin_bad_subscription': {
        'subject': 'Something went wrong with a donor\'s subscription',
        'body': "Something went wrong while processing the monthly donation "
                "with ID %s. It had a message of:\n\n"
                 
                "     %s\n\n"
                 
                "An admin should look into this before it gets disabled.",
        'from': settings.DEFAULT_FROM_EMAIL,
        'to': [a[1] for a in settings.ADMINS],
    },
    'admin_donation_report': {
        'subject': '$%s were donated by monthly donors today',
        'body': "The following monthly donors contributed a total of $%s:\n\n "
                "%s\n\n"
                "(Note that some of these charges still can fail to go "
                "through.)",
        'from': settings.DEFAULT_FROM_EMAIL,
        'to': [a[1] for a in settings.ADMINS],
    },
}


def send_thank_you_email(donation, recurring=False):
    user = donation.donor
    if recurring:
        email = emails['donation_thanks_recurring']
        body = email['body'] % (user.first_name, donation.amount,
                                settings.EIN_SECRET),
        send_mail(email['subject'], body, email['from'], [user.email])
    else:
        email = emails['donation_thanks']
        body = email['body'] % (user.first_name, donation.amount,
                                settings.EIN_SECRET),
        send_mail(email['subject'], body, email['from'], [user.email])


def send_failed_subscription_email(m_donation):
    """Send an email to the user to tell them their subscription failed.

    m_donation: The MonthlyDonation object that failed.
    """
    email = emails['disabled_subscription']
    body = email['body'] % (
        m_donation.user.first_name,
        m_donation.monthly_donation_amount,
        reverse('donate'),
    )
    send_mail(email['subject'], body, email['from'], [m_donation.user.email])
