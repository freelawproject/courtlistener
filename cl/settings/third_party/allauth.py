# django-allauth provides single sign-on (OIDC and SAML) and nothing else.
# CourtListener keeps its own sign-in, registration, email confirmation and
# password reset views, so these settings switch off every allauth behavior
# that would compete with them.

# auth_user.email is not unique in CourtListener. allauth's migrations read
# this setting, so it must be False before they run, or they add a unique
# constraint on verified addresses that existing data can violate.
ACCOUNT_UNIQUE_EMAIL = False

# allauth refuses email login methods when emails aren't unique. Nothing uses
# allauth's password login anyway; this only satisfies its system checks.
ACCOUNT_LOGIN_METHODS = {"username"}

# UserProfile.email_confirmed is the source of truth for confirmed addresses.
# Keep allauth from sending its own verification emails or tracking a second
# "verified" flag at login.
ACCOUNT_EMAIL_VERIFICATION = "none"

# Never link an SSO identity to an existing account just because the email
# addresses match.
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
