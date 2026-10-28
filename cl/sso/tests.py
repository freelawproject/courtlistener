import time_machine
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from cl.sso.factories import (
    OrganizationDomainFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocialAppFactory,
    SSOConnectionFactory,
)
from cl.sso.models import (
    AuthEvent,
    AuthMethod,
    AuthOutcome,
    Enforcement,
    Organization,
    OrganizationDomain,
)
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory


class OrganizationTest(TestCase):
    """Organizations and their seats."""

    def test_active_through_grace_period(self) -> None:
        """Do benefits last through the grace period after termination?"""
        with time_machine.travel("2026-03-01 12:00:00-05:00", tick=False):
            org = OrganizationFactory.create(termination_date=timezone.now())
            self.assertTrue(org.is_active)
            self.assertIn(org, Organization.objects.active())
        with time_machine.travel("2026-06-01 12:00:00-05:00", tick=False):
            org.refresh_from_db()
            self.assertFalse(org.is_active)
            self.assertNotIn(org, Organization.objects.active())

    def test_no_level_is_inactive(self) -> None:
        """Is an organization without a membership level inactive?"""
        org = OrganizationFactory.create(membership_level=None)
        self.assertFalse(org.is_active)
        self.assertNotIn(org, Organization.objects.active())

    def test_seat_limit(self) -> None:
        """Are only members with a seat counted against the limit?"""
        org = OrganizationFactory.create(seat_limit=1)
        OrganizationMembershipFactory.create(organization=org, has_seat=False)
        self.assertTrue(org.has_free_seat())

        OrganizationMembershipFactory.create(organization=org)
        self.assertEqual(org.seats_used(), 1)
        self.assertFalse(org.has_free_seat())


class DomainTest(TestCase):
    """Domain records."""

    def test_free_email_domains_rejected(self) -> None:
        """Can't an organization claim gmail.com?"""
        domain = OrganizationDomain(
            organization=OrganizationFactory.create(), domain="Gmail.com"
        )
        with self.assertRaises(ValidationError):
            domain.full_clean()

    def test_enforcement_needs_verification(self) -> None:
        """Can't enforcement be turned on before the domain is verified?"""
        domain = OrganizationDomainFactory.build(
            organization=OrganizationFactory.create(),
            verified_at=None,
            enforcement=Enforcement.REQUIRED,
        )
        with self.assertRaises(ValidationError):
            domain.full_clean()

    def test_save_lowercases(self) -> None:
        """Are domains stored lowercased?"""
        domain = OrganizationDomainFactory.create(domain="Acme.TEST")
        self.assertEqual(domain.domain, "acme.test")


class SSOConnectionTest(TestCase):
    """Validation of IdP connections."""

    def test_saml_requires_signed_assertions(self) -> None:
        """Is a SAML app that accepts unsigned assertions rejected?"""
        for advanced, valid in (
            ({}, False),
            ({"want_assertion_signed": True}, True),
        ):
            with self.subTest(advanced=advanced):
                app = SocialAppFactory.create(
                    provider="saml",
                    settings={"idp": {}, "advanced": advanced},
                )
                connection = SSOConnectionFactory.build(
                    organization=OrganizationFactory.create(), social_app=app
                )
                if valid:
                    connection.clean()
                else:
                    with self.assertRaises(ValidationError):
                        connection.clean()

    def test_saml_refuses_idp_initiated_sign_in(self) -> None:
        """Is a SAML app that accepts IdP-started sign-ins rejected?"""
        for reject, valid in ((None, True), (True, True), (False, False)):
            advanced: dict[str, bool] = {"want_assertion_signed": True}
            if reject is not None:
                advanced["reject_idp_initiated_sso"] = reject
            with self.subTest(reject_idp_initiated_sso=reject):
                app = SocialAppFactory.create(
                    provider="saml",
                    settings={"idp": {}, "advanced": advanced},
                )
                connection = SSOConnectionFactory.build(
                    organization=OrganizationFactory.create(), social_app=app
                )
                if valid:
                    connection.clean()
                else:
                    with self.assertRaises(ValidationError):
                        connection.clean()

    def test_provider_id_required(self) -> None:
        """Must every connection have its own provider ID?"""
        connection = SSOConnectionFactory.build(
            organization=OrganizationFactory.create(),
            social_app=SocialAppFactory.create(provider_id=""),
        )
        with self.assertRaises(ValidationError):
            connection.clean()

    def test_shared_provider_id_rejected(self) -> None:
        """Is a provider ID that another SocialApp uses rejected?"""
        SocialAppFactory.create(provider_id="shared")
        connection = SSOConnectionFactory.build(
            organization=OrganizationFactory.create(),
            social_app=SocialAppFactory.create(provider_id="shared"),
        )
        with self.assertRaises(ValidationError):
            connection.clean()


class AdminTest(TestCase):
    """The SSO admin pages."""

    def setUp(self) -> None:
        self.org = OrganizationFactory.create()
        SSOConnectionFactory.create(organization=self.org)
        self.client.force_login(
            UserFactory.create(is_staff=True, is_superuser=True)
        )

    def test_organization_pages_load(self) -> None:
        """Do the organization list and change pages load?"""
        for url in (
            reverse("admin:sso_organization_changelist"),
            reverse("admin:sso_organization_change", args=[self.org.pk]),
        ):
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, self.org.name)

    def test_export_members(self) -> None:
        """Does the CSV export list the organization's members?"""
        member = OrganizationMembershipFactory.create(organization=self.org)

        r = self.client.post(
            reverse("admin:sso_organization_changelist"),
            {"action": "export_members", "_selected_action": [self.org.pk]},
        )

        self.assertEqual(r["Content-Type"], "text/csv")
        self.assertIn(member.user.username, r.content.decode())

    def test_auth_events_are_read_only(self) -> None:
        """Can't audit records be added, edited or deleted in the admin?"""
        event = AuthEvent.objects.create(
            method=AuthMethod.PASSWORD,
            outcome=AuthOutcome.REFUSED,
            identifier_hash="0" * 64,
        )
        for url in (
            reverse("admin:sso_authevent_add"),
            reverse("admin:sso_authevent_delete", args=[event.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        r = self.client.post(
            reverse("admin:sso_authevent_change", args=[event.pk]),
            {"detail": "edited"},
        )
        self.assertEqual(r.status_code, 403)
