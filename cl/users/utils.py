import hashlib
from cl.users.models import UserProfile
from django.contrib.auth.models import User
from django.conf import settings
from django.contrib import messages


def create_stub_account(user_data, profile_data):
    email = user_data['email']
    new_user = User.objects.create_user(
        # Username can only be 30 chars long. Use a hash of the
        # email address to reduce the odds of somebody
        # wanting to create an account that already exists.
        # We'll change this to good values later, when the stub
        # account is upgraded to a real account with a real
        # username.
        hashlib.md5(email).hexdigest()[:30],
        email,
    )
    new_user.first_name = user_data['first_name']
    new_user.last_name = user_data['last_name']

    # Associate a profile
    profile = UserProfile(
        user=new_user,
        stub_account=True,
        address1=profile_data['address1'],
        address2=profile_data.get('address2'),
        city=profile_data['city'],
        state=profile_data['state'],
        zip_code=profile_data['zip_code'],
        wants_newsletter=profile_data['wants_newsletter']
    )
    return new_user, profile


def convert_to_stub_account(user):
    """ Set all fields to as blank as possible.

    :param user: The user to operate on.
    :return: The new user object.
    """
    user.first_name = "Deleted"
    user.last_name = ''
    user.username = hashlib.md5(user.email).hexdigest()[:30]
    user.set_unusable_password()
    user.save()

    profile = user.profile
    profile.address1 = None
    profile.address2 = None
    profile.barmembership = []
    profile.city = None
    profile.employer = None
    profile.state = None
    profile.stub_account = True
    profile.wants_newsletter = False
    profile.zip_code = None
    profile.save()

    return user


emails = {
    'account_deleted': {
        'subject': "User deleted their account on CourtListener!",
        'body': "Sad day indeed. Somebody deleted their account completely, "
                "blowing it to smithereens. The user that deleted their "
                "account was: \n\n"
                " - %s\n\n"
                "Can't keep 'em all, I suppose.\n\n",
        'from': settings.DEFAULT_FROM_EMAIL,
        'to': [a[1] for a in settings.ADMINS]
    },
    'email_changed_successfully': {
        'subject': 'Email changed successfully on CourtListener',
        'body': "Hello, %s,\n\n"
                "You have successfully changed your email address at "
                "CourtListener. Please confirm this change by clicking the "
                "following link within five days:\n\n"
                "https://www.courtlistener.com/email/confirm/%s\n\n"
                "Thanks for using our site,\n\n"
                "The CourtListener team\n\n"
                "------------------\n"
                "For questions or comments, please see our contact page, "
                "https://www.courtlistener.com/contact/.",
        'from': settings.DEFAULT_FROM_EMAIL,
    },
    'confirm_your_new_account': {
        'subject': 'Confirm your account on CourtListener.com',
        'body': "Hello, %s, and thanks for signing up for an account!\n\n"
                "To send you emails, we need you to activate your account with "
                "CourtListener. To activate your account, click this link "
                "within five days:\n\n"
                "https://www.courtlistener.com/email/confirm/%s\n\n"
                "Thanks for using our site,\n\n"
                "The CourtListener Team\n\n"
                "-------------------\n"
                "For questions or comments, please see our contact page, "
                "https://www.courtlistener.com/contact/.",
        'from': settings.DEFAULT_FROM_EMAIL,
    },
    'confirm_existing_account': {
        'subject': 'Confirm your account on CourtListener.com',
        'body': "Hello,\n\n"
                "Somebody, probably you, has asked that we send an email "
                "confirmation link to this address.\n\n"
                "If this was you, please confirm your email address by "
                "clicking the following link within five days:\n\n"
                "https://www.courtlistener.com/email/confirm/%s\n\n"
                "If this was not you, you can disregard this email.\n\n"
                "Thanks for using our site,\n"
                "The CourtListener Team\n\n"
                "-------\n"
                "For questions or comments, please visit our contact page, "
                "https://www.courtlistener.com/contact/\n"
                "We're always happy to hear from you.",
        'from': settings.DEFAULT_FROM_EMAIL,
    },
    'email_not_confirmed': {
        'subject': 'Please confirm your account on %s',
        'body': "Hello, %s,\n\n"
                "During routine maintenance of our site, we discovered that "
                "your email address has not been confirmed. To confirm your "
                "email address and continue using our site, please click the "
                "following link:\n\n"
                " - https://www.courtlistener.com/email/confirm/%s\n\n"
                "Unfortunately, accounts that are not confirmed cannot log in, "
                "will stop receiving alerts, and will eventually be deleted "
                "from our system.\n\n"
                "Thanks for using our site,\n\n"
                "The CourtListener team\n\n\n"
                "------------------\n"
                "For questions or comments, please see our contact page, "
                "https://www.courtlistener.com/contact/.",
        'from': settings.DEFAULT_FROM_EMAIL,
    },
    'new_account_created': {
        'subject': 'New user confirmed on CourtListener: %s',
        'body': "A new user has signed up on CourtListener and they'll be "
                "automatically welcomed soon!\n\n"
                "  Their name is: %s\n"
                "  Their email address is: %s\n\n"
                "Sincerely,\n\n"
                "The CourtListener Bots",
        'from': settings.DEFAULT_FROM_EMAIL,
        'to': [a[1] for a in settings.ADMINS],
    },
}

message_dict = {
    'email_changed_successfully': {
        'level': messages.SUCCESS,
        'message': 'Your settings were saved successfully and you have been '
                   'logged out. To sign back in and continue using '
                   'CourtListener, please confirm your new email address by '
                   'checking your email within five days.'
    },
    'settings_changed_successfully': {
        'level': messages.SUCCESS,
        'message': 'Your settings were saved successfully.',
    },
    'pwd_changed_successfully': {
        'level': messages.SUCCESS,
        'message': 'Your password was changed successfully',
    },
}
