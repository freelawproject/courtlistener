from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialLogin
from django.http import HttpRequest

from cl.sso.linking import resolve_sso_login


class AccountAdapter(DefaultAccountAdapter):
    """allauth account adapter for a site that keeps its own account views.

    CourtListener's ``register`` view is the only way to create a password
    account, so allauth's own signup stays closed.
    """

    def is_open_for_signup(self, request: HttpRequest) -> bool:
        """Refuse allauth's local signup; use the ``register`` view instead.

        :param request: The current request.
        :return: Always False.
        """
        return False


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """allauth adapter that hands SSO logins to CourtListener's rules.

    ``resolve_sso_login`` links or creates the account before allauth
    logs anybody in, so allauth's own signup flow (and its email-based
    linking) never runs.
    """

    def pre_social_login(
        self, request: HttpRequest, sociallogin: SocialLogin
    ) -> None:
        """Link the IdP identity to a CourtListener account, or refuse it.

        :param request: The current request.
        :param sociallogin: The pending SSO login.
        :raises ImmediateHttpResponse: To stop the login with an error page.
        """
        resolve_sso_login(request, sociallogin)

    def is_open_for_signup(
        self, request: HttpRequest, sociallogin: SocialLogin
    ) -> bool:
        """Keep allauth's signup closed; ``resolve_sso_login`` makes accounts.

        :param request: The current request.
        :param sociallogin: The pending SSO login.
        :return: Always False.
        """
        return False

    def is_auto_signup_allowed(
        self, request: HttpRequest, sociallogin: SocialLogin
    ) -> bool:
        """Never let allauth create an account on its own.

        :param request: The current request.
        :param sociallogin: The pending SSO login.
        :return: Always False.
        """
        return False
