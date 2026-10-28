from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.providers.base.constants import AuthProcess
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from cl.lib.ratelimiter import ratelimiter_unsafe_10_per_m
from cl.lib.url_utils import (
    get_redirect_or_abort,
    is_safe_url,
    parse_url_with_ada,
)
from cl.sso.forms import SSOStartForm
from cl.sso.models import SSOConnection
from cl.sso.policy import email_domain, sso_option_for_email

WELL_KNOWN_SUFFIX = "/.well-known/openid-configuration"


@never_cache
@ratelimiter_unsafe_10_per_m
def sso_start(request: HttpRequest) -> HttpResponse:
    """Ask for a work address and send the person on to their IdP.

    The identifier-first half of signing in: somebody whose organization
    uses SSO types their address here instead of a password. Whether a
    domain uses SSO isn't secret, so the page says plainly when it doesn't.

    The IdP login has to be started with a POST (SOCIALACCOUNT_LOGIN_ON_GET
    is off), so a found organization gets a one-button page that POSTs to
    its login URL.
    """
    next_url = get_redirect_or_abort(request, "next")
    if request.method == "POST":
        form = SSOStartForm(request.POST)
    else:
        form = SSOStartForm(initial={"email": request.GET.get("email", "")})

    context = {"form": form, "next": next_url, "private": False}
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        if option := sso_option_for_email(email):
            domain, connection = option
            return TemplateResponse(
                request,
                "sso/continue.html",
                {
                    "organization": domain.organization,
                    "login_url": connection.get_login_url(),
                    "next": next_url,
                    "private": False,
                },
            )
        context["no_sso_domain"] = email_domain(email)
    return TemplateResponse(request, "sso/start.html", context)


def normalize_issuer(url: str) -> str:
    """Reduce an OIDC issuer or discovery URL to the bare issuer.

    A connection's ``server_url`` may be stored with or without the
    discovery path or a trailing slash, so compare issuers through this.

    :param url: An issuer URL, or its discovery document's URL.
    :return: The issuer, without the discovery path or a trailing slash.
    """
    return url.strip().removesuffix(WELL_KNOWN_SUFFIX).rstrip("/")


# The IdP may POST here from its own page, which has no CSRF token. Nothing
# changes until the person authenticates at the IdP and the callback checks
# the state this view stores, so there's nothing for CSRF to protect.
# nosemgrep: python.django.security.audit.csrf-exempt.no-csrf-exempt
@csrf_exempt
@never_cache
@require_http_methods(["GET", "POST"])
def oidc_initiate_login(
    request: HttpRequest, provider_id: str
) -> HttpResponse:
    """Start an OIDC sign-in the IdP asked for, e.g. from an Okta tile.

    This is the "initiate login URI" of OpenID Connect's third-party
    initiated login (Core §4): the IdP links or posts here with ``iss`` and,
    optionally, ``login_hint`` and ``target_link_uri``. Unlike the POST-only
    login URL, a plain link works here. That's what lets a dashboard tile
    sign people in with one click.

    It's safe to start from a link because it only starts the normal
    authorization code flow against the connection's own issuer, with fresh
    state and PKCE. The person still authenticates at their IdP, and the
    usual linking rules decide which account they get.

    :param request: The request from the IdP's link or form.
    :param provider_id: The OIDC connection's provider ID.
    :return: A redirect to the IdP, or a 400 when ``iss`` isn't the
    connection's issuer.
    :raises Http404: If there's no enabled OIDC connection with that ID.
    """
    connection = get_object_or_404(
        SSOConnection.objects.select_related("social_app"),
        social_app__provider="openid_connect",
        social_app__provider_id=provider_id,
        is_enabled=True,
    )
    params = request.POST if request.method == "POST" else request.GET

    # The spec requires iss so a site that trusts several IdPs knows which
    # one is asking. Refusing a mismatch also keeps a link made for one IdP
    # from starting a login at another.
    issuer = normalize_issuer(connection.social_app.settings["server_url"])
    if normalize_issuer(params.get("iss", "")) != issuer:
        return TemplateResponse(
            request,
            "sso/error.html",
            {
                "reason": "This sign-in link doesn't match your "
                "organization's sign-on settings. Ask your IT team to check "
                "CourtListener's initiate login URI.",
                "private": True,
            },
            status=400,
        )

    next_url = parse_url_with_ada(params.get("target_link_uri", ""))
    if not is_safe_url(next_url, request):
        next_url = settings.LOGIN_REDIRECT_URL

    provider = get_adapter(request).get_provider(request, provider_id)
    auth_params = provider.get_auth_params()
    if login_hint := params.get("login_hint", "").strip():
        auth_params["login_hint"] = login_hint
    return provider.redirect(
        request,
        AuthProcess.LOGIN,
        next_url=next_url,
        auth_params=auth_params,
    )
