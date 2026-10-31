from django.conf import settings

from cl.lib.types import EmailType

# Plain-text messages for SSO, in the same shape as cl.users.utils.emails.
# Bodies are %-formatted by the callers in cl.sso.linking and cl.users.forms.
emails: dict[str, EmailType] = {
    "account_linked": {
        "subject": "Your CourtListener account now uses %s single sign-on",
        "body": "Hello %s,\n\n"
        "You just signed in to CourtListener through %s's single sign-on, "
        "and your existing account (username: %s) is now linked to it. "
        "Your alerts, notes and other data are unchanged.\n\n"
        "From now on, sign in with your organization's SSO:\n\n"
        "    https://www.courtlistener.com%s\n\n"
        "If you didn't do this, please write to security@free.law right "
        "away.\n\n"
        "The Free Law Project Team\n\n",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "sign_in_with_sso": {
        "subject": "Sign in to CourtListener with your organization's SSO",
        "body": "Hello,\n\n"
        "Somebody, hopefully you, asked to reset the CourtListener password "
        "for this address. %s requires its people to sign in through its "
        "single sign-on instead of a password, so there is nothing to "
        "reset. Sign in here:\n\n"
        "    https://www.courtlistener.com%s\n\n"
        "If you can't sign in through your organization, ask its IT team, "
        "or write to support@free.law.\n\n"
        "The Free Law Project Team\n\n",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "seat_limit_reached": {
        "subject": "%s has used all of its CourtListener seats",
        "body": "Hello,\n\n"
        "%s just signed in to CourtListener through %s's single sign-on, "
        "but all %s of the organization's seats are taken. They can use "
        "CourtListener, but without the organization's membership "
        "benefits.\n\n"
        "To give them a seat, remove somebody who no longer needs one or "
        "ask Free Law Project about more seats at support@free.law.\n\n"
        "The Free Law Project Team\n\n",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
    "firm_now_uses_sso": {
        "subject": "%s now uses single sign-on for CourtListener",
        "body": "Hello %s,\n\n"
        "%s has set up single sign-on (SSO) for CourtListener. Next time "
        "you sign in, use your organization's SSO:\n\n"
        "    https://www.courtlistener.com%s\n\n"
        "The first time you do, your existing account (username: %s) will "
        "be linked to it automatically. Your alerts, notes and other data "
        "stay as they are.\n\n"
        "The Free Law Project Team\n\n",
        "from_email": settings.DEFAULT_FROM_EMAIL,
    },
}
