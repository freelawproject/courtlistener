from django.conf import settings
from django.core.mail import send_mail

emails = {
    'donation_thanks': {
        'subject': 'Thanks for your donation to Free Law Project!',
        'body': ('Hello %s,\n\nThanks for your donation of $%0.2f to Free '
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
        'from': 'Free Law Project <donate@free.law>',
    }
}


def send_thank_you_email(donation):
    user = donation.donor
    email = emails['donation_thanks']
    send_mail(
        email['subject'],
        email['body'] % (user.first_name, donation.amount, settings.EIN),
        email['from'],
        [user.email]
    )
