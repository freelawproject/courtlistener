import json
from http import HTTPStatus

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from rest_framework import mixins, serializers, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from cl.donate.api_permissions import AllowNeonWebhook
from cl.donate.models import NeonMembership, NeonWebhookEvents
from cl.lib.neon_utils import NeonClient


class NeonMembershipWebhookSerializer(serializers.Serializer):
    eventTrigger = serializers.CharField(required=True)
    eventTimestamp = serializers.DateTimeField(required=True)
    data = serializers.DictField()


class MembershipWebhookViewSet(
    mixins.CreateModelMixin, viewsets.GenericViewSet
):
    permission_classes = [AllowNeonWebhook]
    serializer_class = NeonMembershipWebhookSerializer
    queryset = NeonMembership.objects.all()

    def create(self, request: Request, *args, **kwargs):
        """
        Processes membership webhooks received from Neon CRM.

        This method handles POST requests containing JSON data from Neon CRM.
        It extracts relevant information from the data and updates the
        corresponding membership record in the database.

        Args:
            request (Request): A request object containing the webhook data.

        Returns:
            Response: A HttpResponse object with status code 200 if successful,
            or another appropriate response if an error occurs.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        webhook_data = serializer.validated_data
        match webhook_data["eventTrigger"]:
            case "createMembership":
                self._store_webhook_payload(
                    webhook_data, NeonWebhookEvents.MEMBERSHIP_CREATION
                )
                self._handle_membership_creation(webhook_data)
            case "editMembership":
                self._store_webhook_payload(
                    webhook_data, NeonWebhookEvents.MEMBERSHIP_UPDATE
                )
                self._handle_membership_update(webhook_data)
            case "deleteMembership":
                self._store_webhook_payload(
                    webhook_data, NeonWebhookEvents.MEMBERSHIP_DELETE
                )
                self._handle_membership_deletion(webhook_data)
            case _:
                raise NotImplementedError("Unknown event trigger")

        return Response(status=HTTPStatus.CREATED)

    def _get_member_record(self, account_id: str) -> User:
        """
        Retrieves a user record associated with a Neon CRM account ID.

        This method attempts to find a matching Django user in two ways:

        1. first tries to directly query the database for a user whose
        `neon_account_id` field matches the provided `account_id`.
        2. If no matching user is found in the database, it fetches the
        account email address from the Neon API using the `account_id`.
        It then tries to find a user whose email address matches the
        retrieved Neon account email.

        Args:
            account_id (str): Unique identifier assigned by Neon to an account

        Returns:
            User: User object associated with the Neon account
        """
        try:
            user = User.objects.get(profile__neon_account_id=account_id)
        except User.DoesNotExist:
            client = NeonClient()
            neon_account = client.get_acount_by_id(account_id)
            users = User.objects.filter(
                email=neon_account["primaryContact"]["email1"]
            )
            if not users:
                return HttpResponse(
                    "Error processing webhook, User not found",
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            user = users.first()

            profile = user.profile
            profile.neon_account_id = neon_account["accountId"]
            profile.save()

        return user

    def _store_webhook_payload(self, webhook_data, trigger_type: int) -> None:
        membership_data = webhook_data["data"]["membership"]
        NeonWebhookEvents.objects.create(
            content=json.dumps(webhook_data, default=str),
            trigger=trigger_type,
            membership_id=membership_data["membershipId"],
            account_id=membership_data["accountId"],
        )

    def _handle_membership_creation(self, webhook_data) -> None:
        membership_data = webhook_data["data"]["membership"]
        user = self._get_member_record(membership_data["accountId"])
        NeonMembership.objects.create(
            user=user,
            neon_id=membership_data["membershipId"],
            level=NeonMembership.INVERTED[membership_data["membershipName"]],
            termination_date=membership_data["termEndDate"],
        )

    def _handle_membership_update(self, webhook_data) -> None:
        membership_data = webhook_data["data"]["membership"]
        user = self._get_member_record(membership_data["accountId"])
        try:
            neon_membership = user.membership
            neon_membership.level = NeonMembership.INVERTED[
                membership_data["membershipName"]
            ]
            neon_membership.termination_date = membership_data["termEndDate"]
            neon_membership.save()
        except ObjectDoesNotExist:
            NeonMembership.objects.create(
                user=user,
                neon_id=membership_data["membershipId"],
                level=NeonMembership.INVERTED[
                    membership_data["membershipName"]
                ],
                termination_date=membership_data["termEndDate"],
            )

    def _handle_membership_deletion(self, webhook_data) -> None:
        membership_data = webhook_data["data"]["membership"]
        try:
            neon_membership = NeonMembership.objects.get(
                neon_id=membership_data["membershipId"]
            )
        except NeonMembership.DoesNotExist:
            return HttpResponse(
                "Error processing webhook, Membership not found",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        neon_membership.delete()
