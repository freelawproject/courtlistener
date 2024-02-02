from typing import NotRequired, TypedDict

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
    def __init__(self, timeout=10) -> None:
        self._timeout = timeout
        self._basic = HTTPBasicAuth(
            settings.NEON_ORG_ID, settings.NEON_API_KEY
        )

    def get_acount_by_id(self, account_id: int):
        response = requests.get(
            f"{NEON_API_URL}/accounts/{account_id}",
            auth=self._basic,
            timeout=self._timeout,
        )
        response.raise_for_status()
        json_data = response.json()

        return (
            json_data["individualAccount"]
            if json_data["individualAccount"]
            else json_data["companyAccount"]
        )

    def search_account_by_email(self, email: str) -> list[dict[str, str]]:
        search_payload = {
            "searchFields": [
                {"field": "Email", "operator": "EQUAL", "value": email}
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

    def create_account(self, user: User) -> int:

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
