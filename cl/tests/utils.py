from typing import Tuple

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from requests import Response
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from cl.recap.factories import DocketDataFactory, DocketEntryDataFactory


def make_client(user_pk: int) -> APIClient:
    user = User.objects.get(pk=user_pk)
    token, created = Token.objects.get_or_create(user=user)
    token_header = f"Token {token}"
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=token_header)
    return client


def get_with_wait(
    wait: WebDriverWait,
    locator: Tuple[str, str],
) -> WebElement:
    """Get an element from a selenium browser without all the rigamarole

    :param wait: A webdriver wait for a bparticular browser instance
    :param locator: A two-string tuple that identifies the type of lookup and
    the lookup string for the lookup. For example, it might be:
    (By.TAG_NAME, "body")
    :return: A webelement if it can be found during the wait.
    """
    return wait.until(EC.presence_of_element_located(locator))


class MockResponse(Response):
    """Mock a Request Response"""

    def __init__(
        self,
        status_code,
        content=None,
        reason=None,
        url=None,
        mock_raw=None,
        raw=None,
    ):
        self.status_code = status_code
        self._content = content
        self.reason = reason
        self.url = url
        self.encoding = None
        self._content_consumed = None
        self.raw = raw
        # Mock response raw content if not provided for stream=True requests.
        if mock_raw is True:
            file_stream = ContentFile("OK")
            self.raw = file_stream


class MockACMSDocketReport:
    def __init__(self, court_id):
        pass

    def _parse_text(self, json):
        acms_data = DocketDataFactory(
            court_id="ca9",
            docket_number="23-6364",
            parties=[
                {
                    "attorneys": [
                        {
                            "contact": "Dawson Parrish, PC\n309 W. 7th St.\nSte 915\nFt. Worth, TX 76102\n817-870-1212\nEmail: hparrish@dawsonparrish.com\n",
                            "name": "John Hunter Parrish",
                            "roles": ["ATTORNEY TO BE NOTICED"],
                        }
                    ],
                    "date_terminated": None,
                    "extra_info": "",
                    "name": "RFC Drilling, LLC",
                    "type": "Plaintiff",
                },
            ],
            docket_entries=[
                DocketEntryDataFactory(
                    pacer_doc_id="bde556a7-bdde-ed11-a7c6-001dd806a1fd",
                    document_number=1,
                )
            ],
        )
        self.data = acms_data
