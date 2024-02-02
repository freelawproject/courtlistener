from typing import Any

import requests
from django.conf import settings
from requests.auth import HTTPBasicAuth

from cl.users.models import UserProfile

NEON_API_URL = "https://api.neoncrm.com/v2"


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
        self, user: UserProfile.user
    ) -> dict[str, Any]:
        return {
            "individualAccount": {
                "primaryContact": {
                    "firstName": user.first_name,
                    "lastName": user.last_name,
                    "email1": user.email,
                }
            }
        }

    def create_account(self, user: UserProfile.user) -> int:
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
