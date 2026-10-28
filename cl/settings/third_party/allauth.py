import environ

env = environ.FileAwareEnv()

# django-allauth provides single sign-on (OIDC and SAML) and nothing else.
# CourtListener keeps its own sign-in, registration, email confirmation and
# password reset views, so these settings switch off every allauth behavior
# that would compete with them.

ACCOUNT_ADAPTER = "cl.sso.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "cl.sso.adapters.SocialAccountAdapter"

# auth_user.email is not unique in CourtListener. allauth's migrations read
# this setting, so it must be False before they run, or they add a unique
# constraint on verified addresses that existing data can violate.
ACCOUNT_UNIQUE_EMAIL = False

# Keep allauth's addresses in its own account_emailaddress table. Its
# migrations otherwise lowercase every auth_user.email, and the email bounce
# and SES ban checks match addresses exactly.
ACCOUNT_USER_MODEL_EMAIL_FIELD = None

# allauth refuses email login methods when emails aren't unique. Nothing uses
# allauth's password login anyway; this only satisfies its system checks.
ACCOUNT_LOGIN_METHODS = {"username"}

# UserProfile.email_confirmed is the source of truth for confirmed addresses.
# Keep allauth from sending its own verification emails or tracking a second
# "verified" flag at login.
ACCOUNT_EMAIL_VERIFICATION = "none"

# Never link an SSO identity to an existing account just because the email
# addresses match. Linking rules belong in SocialAccountAdapter.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False
SOCIALACCOUNT_AUTO_SIGNUP = False

# Start the IdP redirect from a POST, so a third-party page can't sign
# somebody in through a plain link.
SOCIALACCOUNT_LOGIN_ON_GET = False

# CourtListener only needs the identity, not the IdP's access tokens.
SOCIALACCOUNT_STORE_TOKENS = False

# Each organization's IdP is a SocialApp row (provider "openid_connect", a
# unique provider_id, and its server_url in settings), so no apps are listed
# here.
SOCIALACCOUNT_PROVIDERS = {
    "openid_connect": {
        "OAUTH_PKCE_ENABLED": True,
    },
}

# CourtListener's own SSO policy (see cl.sso.policy).

# Require staff and superusers to sign in through the staff organization's
# IdP (Organization.is_staff_organization). Turn on only after every staff
# account is linked; run the check_staff_sso command first.
SSO_REQUIRED_FOR_STAFF = env.bool("SSO_REQUIRED_FOR_STAFF", default=False)

# Accounts that aren't people (e.g. upload bots) and authenticate with API
# tokens. check_staff_sso skips them when looking for unlinked staff, and
# flags any that still has a usable password.
SSO_SERVICE_ACCOUNT_USERNAMES = env.list(
    "SSO_SERVICE_ACCOUNT_USERNAMES", default=[]
)

# How often an existing session is re-checked against the SSO policy, so
# turning on enforcement ends password sessions within this many seconds.
SSO_POLICY_RECHECK_SECONDS = env.int("SSO_POLICY_RECHECK_SECONDS", default=300)

# How recently somebody must have signed in through their IdP to skip a
# password re-prompt (e.g. deleting their account) on an account that has
# no password.
SSO_REAUTHENTICATION_SECONDS = env.int(
    "SSO_REAUTHENTICATION_SECONDS", default=60 * 15
)
