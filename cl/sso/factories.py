from typing import Any

import factory
from allauth.socialaccount.models import SocialApp
from django.contrib.sites.models import Site
from django.utils import timezone
from factory.django import DjangoModelFactory

from cl.donate.models import NeonMembershipLevel
from cl.sso.models import (
    Enforcement,
    MembershipSource,
    Organization,
    OrganizationDomain,
    OrganizationMembership,
    SSOConnection,
)
from cl.users.factories import UserFactory


class OrganizationFactory(DjangoModelFactory):
    """An organization with a Tier 1 membership and no seat limit."""

    class Meta:
        model = Organization

    name = factory.Sequence("Firm {}".format)
    slug = factory.Sequence("firm-{}".format)
    membership_level = NeonMembershipLevel.TIER_1


class OrganizationDomainFactory(DjangoModelFactory):
    """A verified domain with enforcement off."""

    class Meta:
        model = OrganizationDomain

    organization = factory.SubFactory(OrganizationFactory)
    domain = factory.Sequence("firm{}.test".format)
    verified_at = factory.LazyFunction(timezone.now)
    enforcement = Enforcement.OFF


class SocialAppFactory(DjangoModelFactory):
    """An OIDC app on the current site."""

    class Meta:
        model = SocialApp

    provider = "openid_connect"
    provider_id = factory.Sequence("idp-{}".format)
    name = factory.Sequence("IdP {}".format)
    client_id = factory.Sequence("client-{}".format)
    secret = "client-secret"
    settings = factory.Dict({"server_url": "https://idp.firm.test"})

    @classmethod
    def _create(
        cls, model_class: type[SocialApp], *args: Any, **kwargs: Any
    ) -> SocialApp:
        """Save the app and attach it to the current site.

        allauth only finds apps attached to the site being served.
        """
        app = super()._create(model_class, *args, **kwargs)
        app.sites.add(Site.objects.get_current())
        return app


class SSOConnectionFactory(DjangoModelFactory):
    """An enabled connection to an OIDC app."""

    class Meta:
        model = SSOConnection

    organization = factory.SubFactory(OrganizationFactory)
    social_app = factory.SubFactory(SocialAppFactory)
    is_enabled = True


class OrganizationMembershipFactory(DjangoModelFactory):
    """A seated member who joined through SSO."""

    class Meta:
        model = OrganizationMembership

    organization = factory.SubFactory(OrganizationFactory)
    user = factory.SubFactory(UserFactory)
    source = MembershipSource.SSO
    has_seat = True
