"""The waffle flag that turns SSO on for the site."""

from waffle import get_waffle_flag_model

SSO_FLAG = "sso"


def sso_enabled() -> bool:
    """Whether SSO is turned on for the site.

    Controlled by the "sso" waffle flag with Everyone set to Yes. Some
    checks run without a request, so the flag's per-user, group and
    percentage settings are ignored. While it's off nobody is offered SSO,
    required to use it, or given benefits through an organization.

    :return: True if the flag is on for everyone.
    """
    return bool(get_waffle_flag_model().get(SSO_FLAG).everyone)
