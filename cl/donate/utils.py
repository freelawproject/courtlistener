from django.conf import settings
from django.core.mail import send_mail


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
    'bad_subscription': {
        'subject': 'Something went wrong with a donor\'s subscription',
        'body': ("Something went wrong while processing the monthly donation "
                 "with ID %s. It had a message of:\n\n"
                 
                 "     %s\n\n"
                 
                 "An admin should look into this."),
        'from': settings.DEFAULT_FROM_EMAIL,
        'to': [a[1] for a in settings.ADMINS],
    },
    'donation_report': {
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
        send_mail(
            email['subject'],
            email['body'] % (user.first_name, donation.amount,
                             settings.EIN_SECRET),
            email['from'],
            [user.email],
        )
    else:
        email = emails['donation_thanks']
        send_mail(
            email['subject'],
            email['body'] % (user.first_name, donation.amount,
                             settings.EIN_SECRET),
            email['from'],
            [user.email]
        )
