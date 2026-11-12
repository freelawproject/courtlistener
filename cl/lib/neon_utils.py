from http import HTTPStatus
from typing import Any, NotRequired, TypedDict

import requests
from django.conf import settings
from django.contrib.auth.models import User
from requests.auth import HTTPBasicAuth

NEON_API_URL = "https://api.neoncrm.com/v2"


class NeonStateProvince(TypedDict):
    code: str


class NeonAddress(TypedDict):
    isPrimaryAddress: NotRequired[bool]
    addressLine1: str
    addressLine2: str
    city: str
    zipCode: str
    stateProvince: NotRequired[NeonStateProvince]


class NeonContact(TypedDict):
    firstName: str
    lastName: str
    email1: str
    addresses: NotRequired[list[NeonAddress]]


class NeonClient:
    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout
        self._basic = HTTPBasicAuth(
            settings.NEON_ORG_ID, settings.NEON_API_KEY
        )

    def get_account_by_id(self, account_id: str) -> dict:
        """Retrieves account data using the Neon API and the provided account ID.

        Neon answers an account that was merged into another one with HTTP
        222 and the surviving account's record, whose ``accountId`` differs
        from the one requested. Callers that store account IDs should compare
        the two and adopt the new one, as Neon's docs recommend.

        Args:
            account_id (str): The ID of the account to retrieve.
        """
        response = requests.get(
            f"{NEON_API_URL}/accounts/{account_id}",
            auth=self._basic,
            timeout=self._timeout,
        )
        response.raise_for_status()
        json_data = response.json()

        account_data = (
            json_data["individualAccount"]
            if json_data["individualAccount"]
            else json_data["companyAccount"]
        )

        if not account_data.get("accountCustomFields"):
            return account_data

        # The 'accountCustomFields' field contains a list of dictionaries,
        # each with a 'name' and a 'value'. The following logic flattens
        # this list into a single dictionary so we can:
        #   1. Easily check for field existence using the 'in' operator.
        #   2. Simplify downstream operations.
        # Field names are normalized to lowercase and spaces are replaced
        # with underscores.
        custom_fields = {
            "_".join(field["name"].lower().split()): field["value"]
            for field in account_data["accountCustomFields"]
        }
        account_data["accountCustomFields"] = custom_fields
        return account_data

    def get_account_memberships(
        self, account_id: str, page_size: int = 20
    ) -> list[dict[str, Any]]:
        """Retrieve an account's membership history, newest first.

        No status filter is applied. Neon's ``primaryActiveMembership`` and
        ``isActive`` filters reflect flags shown on the account page and have
        returned no results, or only long-expired memberships, for accounts
        with a current paid membership. Callers are responsible for selecting
        the relevant record from the returned history.

        An unknown account ID returns an empty list.

        Args:
            account_id: The ID of the Neon account.
            page_size: The maximum number of memberships to return.

        Returns:
            Membership records shaped like the response of
            ``GET /memberships/{id}`` (``id``, ``accountId``,
            ``membershipLevel``, ``termEndDate``, ``status``, ``payments``,
            etc.), ordered by enrollment date, newest first.
        """
        response = requests.get(
            f"{NEON_API_URL}/accounts/{account_id}/memberships",
            auth=self._basic,
            timeout=self._timeout,
            params={
                "sortColumn": "date",
                "sortDirection": "DESC",
                "pageSize": page_size,
            },
        )
        response.raise_for_status()
        return response.json().get("memberships") or []

    def get_membership(self, membership_id: str) -> dict[str, Any] | None:
        """Retrieves one membership record by its ID.

        The record names the account that currently holds the membership in
        ``accountId``, which can differ from the account it was bought under
        when Neon merged accounts, or when a member has a duplicate account.

        Args:
            membership_id (str): The ID of the Neon membership.

        Returns:
            dict[str, Any] | None: The membership record, or None when Neon
            has no membership with that ID.
        """
        response = requests.get(
            f"{NEON_API_URL}/memberships/{membership_id}",
            auth=self._basic,
            timeout=self._timeout,
        )
        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        response.raise_for_status()
        return response.json()

    def search_account_by_email(self, email: str) -> list[dict[str, str]]:
        """Searches for Neon accounts that match the provided email address using the Neon API search endpoint.

        Args:
            email (str): The email address to search for.

        Returns:
            list[dict[str, str]]: A list of dictionaries, where each dictionary
            represents an account that matches the email address. The list may
            be empty if no matching accounts are found.
        """
        search_payload = {
            "searchFields": [
                {"field": "Email", "operator": "EQUAL", "value": email},
                {
                    "field": "Account Type",
                    "operator": "EQUAL",
                    "value": "Individual",
                },
            ],
            "outputFields": ["Account ID"],
            "pagination": {"pageSize": 10},
        }

        response = requests.post(
            f"{NEON_API_URL}/accounts/search",
            auth=self._basic,
            timeout=self._timeout,
            json=search_payload,
        )

        response.raise_for_status()
        json_data = response.json()

        return json_data["searchResults"]

    def get_individual_account_payload(
        self, user: User
    ) -> dict[str, dict[str, NeonContact]]:
        """Extracts relevant data from the provided user object to form a payload for creating or updating an individual account.

        Args:
            user (User): The user object containing the information to be
            extracted

        Returns:
            dict[str, dict[str, NeonContact]]:A dictionary containing the
            extracted data, ready to be used as a payload for the create/update
            request.
        """
        contact_data: NeonContact = {
            "firstName": user.first_name,
            "lastName": user.last_name,
            "email1": user.email,
        }

        profile = user.profile  # type: ignore
        address_dict: NeonAddress = {
            "addressLine1": profile.address1,
            "addressLine2": profile.address2,
            "city": profile.city,
            "zipCode": profile.zip_code,
        }
        if profile.state:
            address_dict["stateProvince"] = {"code": profile.state}

        if any(address_dict.values()):
            address_dict["isPrimaryAddress"] = True
            contact_data["addresses"] = [address_dict]

        return {"individualAccount": {"primaryContact": contact_data}}

    def create_account(self, user: User) -> str:
        """Creates a new Neon account using the Neon API.

        Args:
            user (User): The user object containing the information required
            to create the account.

        Returns:
            str: ID of the new account.
        """
        payload = self.get_individual_account_payload(user)
        response = requests.post(
            f"{NEON_API_URL}/accounts/",
            auth=self._basic,
            timeout=self._timeout,
            json=payload,
        )

        response.raise_for_status()
        json_data = response.json()

        return json_data["id"]

    def update_account(self, user: User, account_id: str) -> str:
        """Updates an existing Neon account using the Neon API.

        Args:
            user (User): The user object containing the updated information for
            the account.
            account_id (str):  The ID of the Neon account to be updated.

        Returns:
            str: ID of the updated account.
        """
        payload = self.get_individual_account_payload(user)
        response = requests.patch(
            f"{NEON_API_URL}/accounts/{account_id}",
            auth=self._basic,
            timeout=self._timeout,
            json=payload,
        )

        response.raise_for_status()
        json_data = response.json()

        return json_data["accountId"]
