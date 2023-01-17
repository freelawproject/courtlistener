from typing import Dict, Tuple

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction

from cl.lib.crypto import md5
from cl.lib.types import EmailType
from cl.users.models import UserProfile


def create_stub_account(
    user_data: Dict[str, str],
    profile_data: Dict[str, str],
) -> Tuple[User, UserProfile]:
    """Create a minimal user account in CL

    This can be helpful when receiving anonymous donations, payments from
    external applications like XERO, etc.

    :param user_data: Generally cleaned data from a cl.donate.forms.UserForm
    :type user_data: dict
    :param profile_data: Generally cleaned data from a
    cl.donate.forms.ProfileForm
    :type profile_data: dict
    :return: A tuple of a User and UserProfile objects
    """
    with transaction.atomic():
        email = user_data["email"]
        new_user = User.objects.create_user(
            # Use a hash of the email address to reduce the odds of somebody
            # wanting to create an account that already exists. We'll change
            # this to good values later, when/if the stub account is upgraded
            # to a real account with a real username.
            md5(email),
            email,
        )
        new_user.first_name = user_data["first_name"]
        new_user.last_name = user_data["last_name"]

        # Associate a profile
        profile = UserProfile.objects.create(
            user=new_user,
            stub_account=True,
            address1=profile_data["address1"],
            address2=profile_data.get("address2"),
            city=profile_data["city"],
            state=profile_data["state"],
            zip_code=profile_data["zip_code"],
            wants_newsletter=profile_data["wants_newsletter"],
        )
    return new_user, profile


def convert_to_stub_account(user: User) -> User:
    """Set all fields to as blank as possible.

    :param user: The user to operate on.
    :return: The new user object.
    """
    user.first_name = "Deleted"
    user.last_name = ""
    user.is_active = False
    user.username = md5(user.email)
    user.set_unusable_password()
    user.save()

    profile = user.profile
    profile.address1 = None
    profile.address2 = None
    profile.city = None
    profile.employer = None
    profile.state = None
    profile.stub_account = True
    profile.email_confirmed = False
    profile.wants_newsletter = False
    profile.zip_code = None
    profile.save()

    profile.barmembership.all().delete()

    return user


def delete_user_assets(user: User) -> None:
    """Delete any associated data from a user account and profile"""
    user.alerts.all().delete()
    user.docket_alerts.all().delete()
    user.notes.all().delete()
    user.user_tags.all().delete()
    user.monthly_donations.all().update(enabled=False)
    user.scotus_maps.all().update(deleted=True)


emails: Dict[str, EmailType] = {
    "account_deleted": {
        "subject": "User deleted their account on CourtListener!",
        "body": "Sad day indeed. Somebody deleted their account completely, "
        "blowing it to smithereens. The user that deleted their "
        "account was: \n\n"
        " - %s\n\n"
        "Can't keep 'em all, I suppose.\n\n",
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "to": [a[1] for a in settings.MANAGERS],
    },
    "take_out_requested": {
        "subject": "User wants their data. Need to send it to them.",
        "body": "A user has requested their data in accordance with GDPR. "
        "This means that if they're a EU citizen, you have to provide "
        "them with their data. Their username and email are:\n\n"
        " - %s\n"
        " - %s\n\n"
        "Good luck getting this taken care of.",
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "to": [a[1] for a in settings.MANAGERS],
    },
    "email_changed_successfully": {
        "subject": "Email changed successfully on CourtListener",
        "body": "Hello %s,\n\n"
        "You have successfully changed your email address at "
        "CourtListener. Please confirm this change by clicking the "
        "following link within five days:\n\n"
        "  https://www.courtlistener.com/email/confirm/%s\n\n"
        "Thanks for using our site,\n\n"
        "The Free Law Project Team\n\n"
        "------------------\n"
        "For questions or comments, please see our contact page, "
        "https://www.courtlistener.com/contact/.",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "notify_old_address": {
        "subject": "This email address is no longer in use on CourtListener",
        "body": "Hello %s,\n\n"
        "A moment ago somebody, hopefully you, changed the email address on "
        "your CourtListener account. Previously, it used:\n\n"
        "    %s\n\n"
        "But now it is set to:\n\n"
        "    %s\n\n"
        "If you made this change, no action is needed. If you did not make "
        "this change, please get in touch with us as soon as possible by "
        "sending a message to:\n\n"
        "    security@free.law\n\n"
        "Thanks for using our site,\n\n"
        "The Free Law Project Team\n\n",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "confirm_your_new_account": {
        "subject": "Confirm your account on CourtListener.com",
        "body": "Hello, %s, and thanks for signing up for an account on "
        "CourtListener.com.\n\n"
        "To send you emails, we need you to activate your account with "
        "CourtListener. To activate your account, click this link "
        "within five days:\n\n"
        "    https://www.courtlistener.com/email/confirm/%s/\n\n"
        "We're always adding features and listening to your requests. "
        "To join the conversation:\n\n"
        " - Sign up for the Free Law Project newsletter: https://free.law/newsletter/\n"
        " - Follow Free Law project or CourtListener on Twitter: https://twitter.com/freelawproject\n"
        " - Check our blog for the latest news and updates: https://free.law/blog/\n\n"
        "Thanks for using CourtListener and joining our community,\n\n"
        "The Free Law Project Team\n\n"
        "-------------------\n"
        "For questions or comments, please see our contact page, "
        "https://www.courtlistener.com/contact/.",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "confirm_existing_account": {
        "subject": "Confirm your account on CourtListener.com",
        "body": "Hello,\n\n"
        "Somebody, probably you, has asked that we send an email "
        "confirmation link to this address.\n\n"
        "If this was you, please confirm your email address by "
        "clicking the following link within five days:\n\n"
        "https://www.courtlistener.com/email/confirm/%s\n\n"
        "If this was not you, you can disregard this email.\n\n"
        "Thanks for using our site,\n"
        "The Free Law Project Team\n\n"
        "-------\n"
        "For questions or comments, please visit our contact page, "
        "https://www.courtlistener.com/contact/\n"
        "We're always happy to hear from you.",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    # Used both when people want to confirm an email address and when they
    # want to reset their password, with one small tweak in the wording.
    "no_account_found": {
        "subject": "Password reset and username information on "
        "CourtListener.com",
        "body": "Hello,\n\n"
        ""
        "Somebody — probably you — has asked that we send %s "
        "instructions to this address. If this was you, "
        "we regret to inform you that we do not have an account with "
        "this email address. This sometimes happens when people "
        "have have typos in their email address when they sign up or "
        "change their email address.\n\n"
        ""
        "If you think that may have happened to you, the solution is "
        "to simply create a new account using your email address:\n\n"
        ""
        "    https://www.courtlistener.com%s\n\n"
        ""
        "That usually will fix the problem.\n\n"
        ""
        "If this was not you, you can ignore this email.\n\n"
        ""
        "Thanks for using our site,\n\n"
        ""
        "The Free Law Project Team\n\n"
        "-------\n"
        "For questions or comments, please visit our contact page, "
        "https://www.courtlistener.com/contact/\n"
        "We're always happy to hear from you.",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "email_not_confirmed": {
        "subject": "Please confirm your account on %s",
        "body": "Hello, %s,\n\n"
        "During routine maintenance of our site, we discovered that "
        "your email address has not been confirmed. To confirm your "
        "email address and continue using our site, please click the "
        "following link:\n\n"
        " - https://www.courtlistener.com/email/confirm/%s\n\n"
        "Unfortunately, accounts that are not confirmed cannot log in, "
        "will stop receiving alerts, and will eventually be deleted "
        "from our system.\n\n"
        "Thanks for using our site,\n\n"
        "The Free Law Project Team\n\n\n"
        "------------------\n"
        "For questions or comments, please see our contact page, "
        "https://www.courtlistener.com/contact/.",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "new_account_created": {
        "subject": "New user confirmed on CourtListener: %s",
        "body": "A new user has signed up on CourtListener and they'll be "
        "automatically welcomed soon!\n\n"
        "  Their name is: %s\n"
        "  Their email address is: %s\n\n"
        "Sincerely,\n\n"
        "The CourtListener Bots",
        "from_email": settings.DEFAULT_FROM_EMAIL,
        "to": [a[1] for a in settings.MANAGERS],
    },
}

message_dict = {
    "email_changed_successfully": {
        "level": messages.SUCCESS,
        "message": "Your settings were saved successfully and you have been "
        "logged out. To sign back in and continue using "
        "CourtListener, please confirm your new email address by "
        "checking your email within five days.",
    },
    "settings_changed_successfully": {
        "level": messages.SUCCESS,
        "message": "Your settings were saved successfully.",
    },
    "pwd_changed_successfully": {
        "level": messages.SUCCESS,
        "message": "Your password was changed successfully",
    },
}
