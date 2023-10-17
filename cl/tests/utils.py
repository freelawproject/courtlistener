from datetime import date, datetime
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
            court_id="ca2",
            appeal_from="S.D.N.Y . (NEW YORK CITY)",
            case_name="United States of America v. Raji",
            case_type_information="Criminal, Direct Criminal",
            date_filed=date(2023, 10, 2),
            docket_number="23-6364",
            fee_status="IFP Granted",
            originating_court_information={
                "identifier": "S.D.N.Y. (NEW YORK CITY)",
                "name": "S.D.N.Y . (NEW YORK CITY)",
            },
            pacer_case_id="9f5ae37f-c44e-4194-b075-3f8f028559c4",
            parties=[
                {
                    "attorneys": [
                        {
                            "contact": "Email: won.shin@usdoj.gov\nUnited States Attorney's Office for the Southern District of New York\nOne Saint Andrew's Plaza\nNew York, NY 10007",
                            "name": "Won S. Shin, Assistant U.S. Attorney",
                            "roles": ["US Attorney"],
                        }
                    ],
                    "name": "UNITED STATES OF AMERICA",
                    "type": "AppelleeUSA",
                },
                {
                    "attorneys": [
                        {
                            "contact": "Direct: 212-571-5500\nEmail: jschneider@rssslaaw.com\nRothman, Schneider, Soloway & Stern, LLP\n100 Lafayette Street\nSuite 501\nNew York, NY 10013",
                            "name": "Jeremy Schneider, -",
                            "roles": ["CJA Appointment"],
                        }
                    ],
                    "name": "MUSTAPHA RAJI",
                    "type": "Appellant",
                    "unparsed": [
                        "\u00a0\u00a0\u00a0\u00a0AKA Sealed Defendant 1, "
                    ],
                },
            ],
            docket_entries=[
                DocketEntryDataFactory(
                    date_filed=datetime(2023, 10, 2, 11, 17, 0),
                    date_entered=datetime(2023, 10, 2, 11, 17, 0),
                    description="<p>NOTICE OF CRIMINAL APPEAL, with district court docket, on behalf of Appellant Mustapha Raji, FILED. [Entered: 10/02/2023 11:17 AM]</p>",
                    pacer_doc_id="46de54cd-3561-ee11-be6e-001dd804e087",
                    document_number=1,
                    page_count=18,
                ),
                DocketEntryDataFactory(
                    date_filed=datetime(2023, 10, 2, 11, 20, 0),
                    date_entered=datetime(2023, 10, 2, 11, 20, 0),
                    description="<p>DISTRICT COURT JUDGMENT, dated 09/19/2023, RECEIVED. [Entered: 10/02/2023 11:20 AM]</p>",
                    pacer_doc_id="0d24550b-3761-ee11-be6e-001dd804e087",
                    document_number=2,
                    page_count=8,
                ),
            ],
        )
        self.data = acms_data
