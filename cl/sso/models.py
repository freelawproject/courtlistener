from typing import Any, Self

import pghistory
from allauth.socialaccount.models import SocialApp
from disposable_email_domains import blocklist
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone

from cl.donate.models import NeonMembership, NeonMembershipLevel
from cl.lib.models import AbstractDateTimeModel
from cl.lib.url_utils import BASE_URL

# Domains anyone can get an address on. Verifying one of these would let a
# single organization claim every user of the provider, so they can never be
# added as organization domains, nor can their subdomains. The
# disposable-email-domains blocklist covers throwaway providers; this list
# adds the major free ones it leaves out.
FREE_EMAIL_PROVIDERS = frozenset(
    {
        "aol.com",
        "fastmail.com",
        "gmail.com",
        "gmx.com",
        "googlemail.com",
        "hey.com",
        "hotmail.com",
        "icloud.com",
        "live.com",
        "mac.com",
        "mail.com",
        "me.com",
        "msn.com",
        "outlook.com",
        "proton.me",
        "protonmail.com",
        "yahoo.com",
        "yandex.com",
        "zoho.com",
    }
)


class OrganizationQuerySet(models.QuerySet["Organization"]):
    """QuerySet for Organization that owns the shared "active" rule."""

    def active(self) -> Self:
        """Organizations whose members currently get membership benefits.

        Same rule as ``Organization.is_active``, and the same grace period
        as ``NeonMembership.objects.active()``: a membership level is set and
        the termination date, if any, is on or after
        ``NeonMembership.benefits_cutoff_date()``.
        """
        return self.filter(membership_level__isnull=False).filter(
            Q(termination_date__isnull=True)
            | Q(
                termination_date__date__gte=(
                    NeonMembership.benefits_cutoff_date()
                )
            )
        )


class OrganizationManager(models.Manager["Organization"]):
    """Manager that exposes OrganizationQuerySet.active() on ``objects``."""

    def get_queryset(self) -> OrganizationQuerySet:
        """Return an OrganizationQuerySet so its methods chain off objects."""
        return OrganizationQuerySet(self.model, using=self._db)

    def active(self) -> OrganizationQuerySet:
        """See ``OrganizationQuerySet.active``."""
        return self.get_queryset().active()


@pghistory.track()
class Organization(AbstractDateTimeModel):
    """A firm or other group whose people sign in through its own IdP.

    The organization, not each person, holds the membership level. People
    get it through an ``OrganizationMembership``, which the first SSO login
    creates. See ``cl.sso.membership.get_effective_membership``.
    """

    name = models.CharField(max_length=200)
    slug = models.SlugField(
        unique=True,
        help_text="Short identifier, e.g. 'acme-law'. Used in SSO URLs.",
    )
    membership_level = models.SmallIntegerField(
        choices=NeonMembershipLevel.TYPES,
        null=True,
        blank=True,
        help_text="Benefits members get. Leave blank for SSO without "
        "membership benefits.",
    )
    seat_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How many people get the organization's benefits. Blank "
        "means no limit.",
    )
    termination_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When benefits end, before the shared membership grace "
        "period. Blank means they don't expire.",
    )
    neon_account_id = models.CharField(
        blank=True,
        max_length=50,
        help_text="The organization's own account in Neon CRM, if any.",
    )
    session_max_age = models.PositiveIntegerField(
        default=60 * 60 * 12,
        help_text="Seconds an SSO session lasts before the person has to "
        "sign in through the IdP again. Shorter sessions shrink the window "
        "in which somebody who has left keeps access.",
    )
    is_staff_organization = models.BooleanField(
        default=False,
        help_text="This is Free Law Project itself. When staff SSO is "
        "required, staff must sign in through this organization's IdP.",
    )
    notes = models.TextField(blank=True)

    objects = OrganizationManager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_staff_organization"],
                condition=Q(is_staff_organization=True),
                name="only_one_staff_organization",
            )
        ]

    def __str__(self) -> str:
        """Return a readable name for the admin and logs."""
        return self.name

    @property
    def is_active(self) -> bool:
        """Whether members currently get the organization's benefits.

        ``OrganizationQuerySet.active`` applies the same rule in SQL.
        """
        if self.membership_level is None:
            return False
        if not self.termination_date:
            return True
        return (
            timezone.localdate(self.termination_date)
            >= NeonMembership.benefits_cutoff_date()
        )

    def seats_used(self) -> int:
        """Count the memberships that hold one of the organization's seats.

        :return: The number of members with a seat.
        """
        return self.memberships.filter(has_seat=True).count()

    def has_free_seat(self) -> bool:
        """Whether one more person can get the organization's benefits.

        :return: True if there is no seat limit or it hasn't been reached.
        """
        if self.seat_limit is None:
            return True
        return self.seats_used() < self.seat_limit


def normalize_domain(domain: str) -> str:
    """Lowercase a domain and drop a leading "@" and trailing dot.

    :param domain: The domain as typed, e.g. " @Acme-Law.com. ".
    :return: The domain as stored, e.g. "acme-law.com".
    """
    return domain.strip().lower().lstrip("@").rstrip(".")


class Enforcement(models.TextChoices):
    """How strongly a domain's addresses are steered to SSO."""

    OFF = "off", "Off: SSO is set up but not offered"
    OPTIONAL = "optional", "Optional: SSO offered, passwords still work"
    REQUIRED = "required", "Required: SSO is the only way in"


@pghistory.track()
class OrganizationDomain(AbstractDateTimeModel):
    """An email domain an organization has proven it controls.

    FLP staff confirm the organization controls the domain and then set
    ``verified_at`` in the admin. Until a domain is verified, its
    enforcement must stay off and SSO logins can't claim addresses on it.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="domains"
    )
    domain = models.CharField(
        max_length=253,
        unique=True,
        help_text="Lowercase, without the '@', e.g. 'acmelaw.com'.",
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set once FLP has confirmed the organization controls "
        "this domain.",
    )
    enforcement = models.CharField(
        max_length=10, choices=Enforcement.choices, default=Enforcement.OFF
    )

    class Meta:
        ordering = ["domain"]

    def __str__(self) -> str:
        """Return a readable name for the admin and logs."""
        return self.domain

    @property
    def is_verified(self) -> bool:
        """Whether the organization has proven it controls this domain."""
        return self.verified_at is not None

    def clean(self) -> None:
        """Normalize the domain and refuse ones nobody may claim.

        :raises ValidationError: For free email providers, or for
        enforcement on a domain that isn't verified yet.
        """
        self.domain = normalize_domain(self.domain)
        labels = self.domain.split(".")
        for i in range(len(labels) - 1):
            parent = ".".join(labels[i:])
            if parent in FREE_EMAIL_PROVIDERS or parent in blocklist:
                raise ValidationError(
                    {"domain": f"{parent} is a public email provider."}
                )
        if self.enforcement != Enforcement.OFF and not self.is_verified:
            raise ValidationError(
                {"enforcement": "Verify the domain before enabling SSO on it."}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Store the domain lowercased, however it was entered."""
        self.domain = normalize_domain(self.domain)
        super().save(*args, **kwargs)


@pghistory.track()
class SSOConnection(AbstractDateTimeModel):
    """Ties an allauth ``SocialApp`` (the IdP settings) to an organization.

    The ``SocialApp`` holds the protocol settings: for OIDC, the issuer URL,
    client ID and secret; for SAML, the IdP metadata. Its ``provider_id``
    namespaces the identities the IdP asserts, so it must be unique to this
    connection.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="connections"
    )
    social_app = models.OneToOneField(
        SocialApp, on_delete=models.CASCADE, related_name="sso_connection"
    )
    is_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "SSO connection"

    def __str__(self) -> str:
        """Return a readable name for the admin and logs."""
        return f"{self.organization}: {self.social_app.name}"

    @property
    def provider_id(self) -> str:
        """The allauth provider ID SSO identities from this IdP are kept under.

        This is what ``SocialAccount.provider`` holds for linked accounts.
        """
        return self.social_app.provider_id or self.social_app.provider

    def clean(self) -> None:
        """Make sure identities from this IdP can't collide with another's.

        :raises ValidationError: If the SocialApp isn't an OIDC or SAML app,
        has no provider_id or shares one with another app, or (for SAML)
        accepts unsigned assertions or sign-ins started at the IdP.
        """
        if self.social_app_id is None:
            return
        if self.social_app.provider not in ("openid_connect", "saml"):
            raise ValidationError(
                {"social_app": "Only OpenID Connect and SAML are supported."}
            )
        if not self.social_app.provider_id:
            raise ValidationError(
                {
                    "social_app": "Give the SocialApp a unique provider ID, "
                    "e.g. 'acme-law', so its identities are kept apart from "
                    "other organizations'."
                }
            )
        if (
            SocialApp.objects.filter(provider_id=self.social_app.provider_id)
            .exclude(pk=self.social_app.pk)
            .exists()
        ):
            raise ValidationError(
                {
                    "social_app": "Another SocialApp already uses this "
                    "provider ID. Give each IdP its own."
                }
            )
        # allauth doesn't require signed assertions by default. A signed
        # response alone leaves room for assertion-wrapping attacks.
        advanced = (self.social_app.settings or {}).get("advanced", {})
        if self.social_app.provider == "saml" and not advanced.get(
            "want_assertion_signed"
        ):
            raise ValidationError(
                {
                    "social_app": 'Set "advanced": {"want_assertion_signed": '
                    "true} in the SAML app's settings."
                }
            )
        # A SAML sign-in started at the IdP answers no request CourtListener
        # made, so nothing ties the response to this browser. allauth refuses
        # them unless this is set to false. IdP dashboard tiles use OIDC's
        # initiate login URI instead (see views.oidc_initiate_login).
        if self.social_app.provider == "saml" and not advanced.get(
            "reject_idp_initiated_sso", True
        ):
            raise ValidationError(
                {
                    "social_app": "SAML sign-ins started at the IdP aren't "
                    'supported. Remove "reject_idp_initiated_sso" from the '
                    "SAML app's advanced settings."
                }
            )

    def get_login_url(self) -> str:
        """Return the URL that starts a login through this IdP.

        The URL must be POSTed to (SOCIALACCOUNT_LOGIN_ON_GET is off).

        :return: A path on this site.
        """
        if self.social_app.provider == "saml":
            return reverse(
                "saml_login",
                kwargs={"organization_slug": self.social_app.client_id},
            )
        return reverse(
            "openid_connect_login",
            kwargs={"provider_id": self.social_app.provider_id},
        )

    def get_idp_settings(self) -> dict[str, str]:
        """List the URLs the organization's IdP admin enters for this app.

        These are what the setup guide tells customers, filled in for this
        connection, so staff can send them without working them out.

        :return: {setting name as IdPs label it: absolute URL}, in the order
        an IdP's setup screens ask for them.
        """
        if self.social_app.provider == "saml":
            slug = {"organization_slug": self.social_app.client_id}
            return {
                "ACS (reply) URL": BASE_URL + reverse("saml_acs", kwargs=slug),
                "SP entity ID (audience)": BASE_URL
                + reverse("saml_metadata", kwargs=slug),
            }
        provider = {"provider_id": self.social_app.provider_id}
        return {
            "Sign-in redirect URI": BASE_URL
            + reverse("openid_connect_callback", kwargs=provider),
            "Initiate login URI": BASE_URL
            + reverse("sso_oidc_initiate", kwargs=provider),
        }


class MembershipRole(models.TextChoices):
    """What a person may do within their organization."""

    MEMBER = "member", "Member"
    ADMIN = "admin", "Organization admin"


class MembershipSource(models.TextChoices):
    """How a person came to belong to an organization."""

    SSO = "sso", "Signed in through the organization's IdP"
    MANUAL = "manual", "Added by Free Law Project staff"


@pghistory.track()
class OrganizationMembership(AbstractDateTimeModel):
    """A person's place in an organization.

    Created by the person's first SSO login through one of the
    organization's connections, or by staff. ``has_seat`` is False when the
    person joined after the organization reached its seat limit; they can
    still sign in but get no organization benefits.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    role = models.CharField(
        max_length=10,
        choices=MembershipRole.choices,
        default=MembershipRole.MEMBER,
    )
    source = models.CharField(
        max_length=10,
        choices=MembershipSource.choices,
        default=MembershipSource.SSO,
    )
    has_seat = models.BooleanField(
        default=True,
        help_text="Whether this person gets the organization's benefits.",
    )
    last_sso_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_organization_member",
            )
        ]

    def __str__(self) -> str:
        """Return a readable name for the admin and logs."""
        return f"{self.user} in {self.organization}"


@pghistory.track()
class SSOEmailException(AbstractDateTimeModel):
    """An address on a required-SSO domain that may still use a password.

    For people who need a CourtListener account at the organization's
    address but aren't in its IdP, such as contractors. Managed by FLP
    staff at the organization's request.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="email_exceptions",
    )
    email = models.EmailField()
    reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "SSO email exception"
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                "organization",
                name="unique_sso_email_exception",
            )
        ]

    def __str__(self) -> str:
        """Return a readable name for the admin and logs."""
        return self.email


class AuthMethod(models.TextChoices):
    """How somebody tried to sign in."""

    PASSWORD = "password", "Password (sign-in page)"
    BASIC_AUTH = "basic_auth", "HTTP Basic auth (API)"
    SSO = "sso", "Single sign-on"
    PASSWORD_RESET = "password_reset", "Password reset request"


class AuthOutcome(models.TextChoices):
    """What happened when somebody tried to sign in."""

    SUCCESS = "success", "Signed in"
    FAILURE = "failure", "Wrong credentials"
    REFUSED = "refused", "Refused by SSO policy"
    LINKED = "linked", "SSO identity linked to an existing account"
    CREATED = "created", "Account created by SSO"
    FLAGGED = "flagged", "Needs support review"


class AuthEvent(models.Model):
    """An append-only record of sign-in activity, kept as audit evidence.

    Written by ``cl.sso.events.record_auth_event``. Successful HTTP Basic
    requests aren't recorded, because every API call would add a row;
    refused and failed ones are.
    """

    date_created = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="auth_events",
    )
    identifier_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="Hash of the identifier submitted in a failed attempt "
        "when it matched no account, so the log holds no raw addresses.",
    )
    method = models.CharField(max_length=20, choices=AuthMethod.choices)
    outcome = models.CharField(max_length=10, choices=AuthOutcome.choices)
    connection = models.ForeignKey(
        SSOConnection, null=True, blank=True, on_delete=models.SET_NULL
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    detail = models.CharField(max_length=500, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "date_created"])]

    def __str__(self) -> str:
        """Return a readable name for the admin and logs."""
        return (
            f"{self.date_created:%Y-%m-%d %H:%M} {self.method} {self.outcome}"
        )
