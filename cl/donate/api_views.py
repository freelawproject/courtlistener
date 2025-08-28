from collections import defaultdict
from http import HTTPStatus

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from rest_framework import mixins, serializers, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from cl.donate.api_permissions import AllowNeonWebhook
from cl.donate.models import (
    MembershipPaymentStatus,
    NeonMembership,
    NeonWebhookEvent,
)
from cl.lib.neon_utils import NeonClient
from cl.lib.types import EmailType
from cl.users.utils import (
    create_stub_account,
    emails,
)


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
        self._store_webhook_payload(webhook_data)
        with transaction.atomic():
            match webhook_data["eventTrigger"]:
                case "createMembership":
                    self._handle_membership_creation(webhook_data)
                case "editMembership" | "updateMembership":
                    self._handle_membership_update(webhook_data)
                case "deleteMembership":
                    self._handle_membership_deletion(webhook_data)
                case _:
                    trigger = webhook_data["eventTrigger"]
                    raise NotImplementedError(
                        f"Unknown event trigger-{trigger}"
                    )

        return Response(status=HTTPStatus.CREATED)

    def _get_address_from_neon_response(self, addresses: list[dict[str, str]]):
        """
        Retrieves an address from the Neon response.

        Args:
            addresses: An array of dictionaries representing addresses.

        Returns:
            A dictionary containing the first address if available, otherwise a defaultdict.
        """
        if not addresses:
            address = defaultdict(lambda: "")
            return address

        return {
            # Neon API returns an array of addresses.
            "address1": addresses[0]["addressLine1"],
            "address2": addresses[0]["addressLine2"],
            "city": addresses[0]["city"],
            "state": addresses[0]["stateProvince"]["code"],
            "zip_code": addresses[0]["zipCode"],
        }

    def _get_member_record(self, account_id: str) -> User:
        """
        Retrieves a user record associated with a Neon CRM account ID.

        This method attempts to find a matching Django user in two ways:

        1. first tries to directly query the database for a user whose
        `neon_account_id` field matches the provided `account_id`.

        2. If no matching user is found in the database:
            - Fetch the account from the Neon API.
            - If the account contains a `cl_user_id` in its custom fields,
              attempt to match by that user ID.
            - Otherwise, attempt to match by the account's primary email
              address, prioritizing the most recently active account.
           If no user is found by either method, create a stub user profile
           using the data returned by Neon..

        In all cases, if a user is found or created, their profile is updated
        with the Neon account ID.

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
            neon_account = client.get_account_by_id(account_id)
            if (
                "accountCustomFields" in neon_account
                and "cl_user_id" in neon_account["accountCustomFields"]
            ):
                user_id = neon_account["accountCustomFields"]["cl_user_id"]
                users = User.objects.filter(id=user_id)
            else:
                contact_data = neon_account["primaryContact"]
                users = User.objects.filter(
                    email__iexact=contact_data["email1"]
                ).order_by(F("last_login").desc(nulls_last=True))
            if not users.exists():
                address = self._get_address_from_neon_response(
                    contact_data["addresses"]
                )
                user, _ = create_stub_account(
                    {
                        "email": contact_data["email1"],
                        "first_name": contact_data["firstName"],
                        "last_name": contact_data["lastName"],
                    },
                    address,
                )
            else:
                user = users.first()

            profile = user.profile
            profile.neon_account_id = neon_account["accountId"]
            profile.save()

        return user

    @staticmethod
    def _get_membership_data(webhook_data: dict[str, str]) -> dict[str, str]:
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
            - paymentStatus: The current payment status for the membership.
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

        payment_status = (
            data.get("payments")[0].get("paymentStatus", "").lower()
            if data.get("payments", [])
            else ""
        )
        membership.update(
            {
                "accountId": data["accountId"],
                "termEndDate": data["termEndDate"],
                "status": data["status"].lower(),
                "paymentStatus": payment_status,
            }
        )

        return membership

    @staticmethod
    def _map_trigger_value(trigger_event: str) -> int:
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

    @staticmethod
    def _map_payment_status_value(status: str) -> int:
        """
        Maps a payment status string into its corresponding
        integer value defined in the `MembershipPaymentStatus` class.

        Args:
            status (str): The payment status string (e.g., "succeeded", "failed").

        Returns:
            int: The mapped constant value from `MembershipPaymentStatus`.
                Defaults to `PENDING` for unrecognized values.
        """
        match status:
            case "succeeded":
                payment_status = MembershipPaymentStatus.SUCCEEDED
            case "failed":
                payment_status = MembershipPaymentStatus.FAILED
            case _:
                payment_status = MembershipPaymentStatus.PENDING

        return payment_status

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

    def _handle_membership_update(self, webhook_data) -> None:
        membership_data = self._get_membership_data(webhook_data)
        membership_query = NeonMembership.objects.filter(
            neon_id=membership_data["membershipId"]
        )
        if not membership_query.exists():
            return None

        membership_level = NeonMembership.TYPES_INVERTED[
            membership_data["membershipName"]
        ]
        payment_status = self._map_payment_status_value(
            membership_data["paymentStatus"]
        )

        neon_membership = membership_query.first()
        neon_membership.level = membership_level
        neon_membership.termination_date = membership_data["termEndDate"]
        neon_membership.payment_status = payment_status
        neon_membership.save()

    def _handle_membership_creation(self, webhook_data) -> None:
        membership_data = self._get_membership_data(webhook_data)
        user = self._get_member_record(membership_data["accountId"])
        membership_level = NeonMembership.TYPES_INVERTED[
            membership_data["membershipName"]
        ]

        if membership_level == NeonMembership.EDU:
            is_valid_edu_account = (
                user.profile.email_confirmed and user.email.endswith(".edu")
            )
            if not is_valid_edu_account:
                email: EmailType = emails["not_valid_edu_account"]
                send_mail(
                    email["subject"],
                    email["body"] % (user.username),
                    email["from_email"],
                    [user.email],
                )
                return None

        payment_status = self._map_payment_status_value(
            membership_data["paymentStatus"]
        )

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
                payment_status=payment_status,
            )
        else:
            neon_membership.neon_id = membership_data["membershipId"]
            neon_membership.level = membership_level
            neon_membership.termination_date = membership_data["termEndDate"]
            neon_membership.payment_status = payment_status
            neon_membership.save()

    @staticmethod
    def _handle_membership_deletion(webhook_data) -> None:
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
