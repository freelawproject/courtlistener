from http import HTTPStatus

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpResponse
from rest_framework import mixins, serializers, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from cl.donate.api_permissions import AllowNeonWebhook
from cl.donate.models import NeonMembership, NeonWebhookEvent
from cl.lib.neon_utils import NeonClient
from cl.users.utils import create_stub_account


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

    @transaction.atomic
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
        self._store_webhook_payload(webhook_data)
        match webhook_data["eventTrigger"]:
            case "createMembership" | "editMembership" | "updateMembership":
                self._handle_membership_creation_or_update(webhook_data)
            case "deleteMembership":
                self._handle_membership_deletion(webhook_data)
            case _:
                trigger = webhook_data["eventTrigger"]
                raise NotImplementedError(f"Unknown event trigger-{trigger}")

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
        retrieved Neon account email. If this attempt fails, this helper
        will create a stub profile using the available data.

        Args:
            account_id (str): Unique identifier assigned by Neon to an account

        Returns:
            User: User object associated with the Neon account
        """
        try:
            user = User.objects.select_for_update().get(
                profile__neon_account_id=account_id
            )
        except User.DoesNotExist:
            client = NeonClient()
            neon_account = client.get_acount_by_id(account_id)
            contact_data = neon_account["primaryContact"]
            users = User.objects.filter(email=contact_data["email1"]).order_by(
                "-last_login"
            )
            if not users.exists():
                user, _ = create_stub_account(
                    {
                        "email": contact_data["email1"],
                        "first_name": contact_data["firstName"],
                        "last_name": contact_data["lastName"],
                    },
                    {
                        # Neon API returns an array of addresses.
                        "address1": contact_data["addresses"][0][
                            "addressLine1"
                        ],
                        "address2": contact_data["addresses"][0][
                            "addressLine2"
                        ],
                        "city": contact_data["addresses"][0]["city"],
                        "state": contact_data["addresses"][0]["stateProvince"][
                            "code"
                        ],
                        "zip_code": contact_data["addresses"][0]["zipCode"],
                        "wants_newsletter": False,
                    },
                )
            else:
                user = users.first()

            profile = user.profile
            profile.neon_account_id = neon_account["accountId"]
            profile.save()

        return user

    def _get_membership_data(
        self, webhook_data: dict[str, str]
    ) -> dict[str, str]:
        """
        Extracts relevant membership information from a Neon webhook payload.

        Args:
            webhook_data (dict[str, str]): The payload received from a Neon
            webhook.

        Returns:
            dict[str, str]: A dictionary containing the extracted membership
            data, with the following keys:
            - membershipId: Unique identifier for the membership.
            - accountId: Identifier for the user account associated with the
            membership.
            - termEndDate: The date the membership is scheduled to terminate
            - membershipName: The name of the membership level the user is
            enrolled in.
        """
        # checks whether the webhook payloads match the expected schema defined
        # in the documentation
        #
        # see: https://github.com/freelawproject/courtlistener/pull/3468#discussion_r1433374045
        if "membership" in webhook_data["data"]:
            data = webhook_data["data"]["membership"]
            membership = {
                "membershipId": data["membershipId"],
                "membershipName": data["membershipName"],
            }
        else:
            data = webhook_data["data"]
            membership = {
                "membershipId": data["id"],
                "membershipName": data["membershipLevel"]["name"],
            }

        membership.update(
            {
                "accountId": data["accountId"],
                "termEndDate": data["termEndDate"],
                "status": data["status"].lower(),
            }
        )

        return membership

    def _map_trigger_value(self, trigger_event: str) -> int:
        """
        Maps a string trigger event received from a Neon webhook to the
        corresponding integer value representing the trigger event type in
        the NeonWebhookEvent model.

        Args:
            trigger_event (str): The string representing the trigger event
            type received in the Neon webhook payload.

        Returns:
            int: The integer value of the trigger event type according to
            the NeonWebhookEvent model
        """
        match trigger_event:
            case "createMembership":
                trigger = NeonWebhookEvent.MEMBERSHIP_CREATION
            case "updateMembership":
                trigger = NeonWebhookEvent.MEMBERSHIP_UPDATE
            case "editMembership":
                trigger = NeonWebhookEvent.MEMBERSHIP_EDIT
            case "deleteMembership":
                trigger = NeonWebhookEvent.MEMBERSHIP_DELETE

        return trigger

    def _store_webhook_payload(self, webhook_data) -> None:
        trigger = self._map_trigger_value(webhook_data["eventTrigger"])
        if trigger != NeonWebhookEvent.MEMBERSHIP_DELETE:
            membership_data = self._get_membership_data(webhook_data)
        else:
            membership_data = webhook_data["data"]["membership"]
        NeonWebhookEvent.objects.create(
            content=webhook_data,
            account_id=membership_data.get("accountId", ""),
            membership_id=membership_data["membershipId"],
            trigger=trigger,
        )

    def _handle_membership_creation_or_update(self, webhook_data) -> None:
        membership_data = self._get_membership_data(webhook_data)
        if membership_data["status"] not in ["succeeded", "succeed"]:
            return None
        user = self._get_member_record(membership_data["accountId"])
        try:
            neon_membership = user.membership
        except ObjectDoesNotExist:
            NeonMembership.objects.create(
                user=user,
                neon_id=membership_data["membershipId"],
                level=NeonMembership.TYPES_INVERTED[
                    membership_data["membershipName"]
                ],
                termination_date=membership_data["termEndDate"],
            )
        else:
            if webhook_data["eventTrigger"] != "updateMembership":
                neon_membership.neon_id = membership_data["membershipId"]
            elif neon_membership.neon_id != membership_data["membershipId"]:
                # The membership record was previously updated and we should
                # ignore this webhook notification.
                #
                # The updateMembership is triggered when a membership upgrade
                # occurs. Its payload contains the details of the previous
                # membership record, but with an updated 'termEndDate' field.
                #
                # During the upgrade process, a createMembership webhook is also
                # triggered, and both requests are sent almost simultaneously.
                # However, we are skipping this webhooks to avoid data integrity
                # issues.
                #
                # See: https://github.com/freelawproject/courtlistener/pull/3468#discussion_r1433398175
                return None
            neon_membership.level = NeonMembership.TYPES_INVERTED[
                membership_data["membershipName"]
            ]
            neon_membership.termination_date = membership_data["termEndDate"]
            neon_membership.save()

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
