import requests
from django.conf import settings
from requests.auth import HTTPBasicAuth

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
