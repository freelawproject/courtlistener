from datetime import date, datetime
from typing import Tuple

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.http import HttpHeaders  # type: ignore[attr-defined]
from django.test import AsyncClient
from django.utils.encoding import force_bytes
from django.utils.http import urlencode
from requests import Response
from rest_framework.authtoken.models import Token
from rest_framework.test import APIRequestFactory
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from cl.recap.factories import (
    ACMSAttachmentFactory,
    ACMSAttachmentPageFactory,
    DocketDataFactory,
    DocketEntryDataFactory,
)


class AsyncAPIClient(AsyncClient, APIRequestFactory):
    def credentials(self, **kwargs):
        """
        Sets headers that will be used on every outgoing request.
        """
        self._credentials = [
            (k.encode("latin1"), v.encode("latin1"))
            for k, v in HttpHeaders(kwargs).items()
        ]

    async def get(self, path, data=None, **extra):
        r = {
            "QUERY_STRING": urlencode(data or {}, doseq=True),
        }
        if not data and "?" in path:
            # Fix to support old behavior where you have the arguments in the
            # url. See #1461.
            query_string = force_bytes(path.split("?")[1])
            query_string = query_string.decode("iso-8859-1")
            r["QUERY_STRING"] = query_string
        r.update(extra)
        return await self.generic("GET", path, **r)

    async def post(
        self, path, data=None, format=None, content_type=None, **extra
    ):
        data, content_type = self._encode_data(data, format, content_type)
        return await self.generic("POST", path, data, content_type, **extra)

    async def put(
        self, path, data=None, format=None, content_type=None, **extra
    ):
        data, content_type = self._encode_data(data, format, content_type)
        return await self.generic("PUT", path, data, content_type, **extra)

    async def patch(
        self, path, data=None, format=None, content_type=None, **extra
    ):
        data, content_type = self._encode_data(data, format, content_type)
        return await self.generic("PATCH", path, data, content_type, **extra)

    async def delete(
        self, path, data=None, format=None, content_type=None, **extra
    ):
        data, content_type = self._encode_data(data, format, content_type)
        return await self.generic("DELETE", path, data, content_type, **extra)

    async def options(
        self, path, data=None, format=None, content_type=None, **extra
    ):
        data, content_type = self._encode_data(data, format, content_type)
        return await self.generic("OPTIONS", path, data, content_type, **extra)

    async def generic(
        self,
        method,
        path,
        data="",
        content_type="application/octet-stream",
        secure=False,
        **extra,
    ):
        # Include the CONTENT_TYPE, regardless of whether or not data is empty.
        if content_type is not None:
            extra["CONTENT_TYPE"] = str(content_type)

        return await super().generic(
            method, path, data, content_type, secure, **extra
        )

    async def request(self, **kwargs):
        # Ensure that any credentials set get added to every request.
        if hasattr(self, "_credentials"):
            kwargs.get("headers", []).extend(self._credentials)
        return await super().request(**kwargs)


def make_client(user_pk: int) -> AsyncAPIClient:
    user = User.objects.get(pk=user_pk)
    token, created = Token.objects.get_or_create(user=user)
    token_header = f"Token {token}"
    client = AsyncAPIClient()
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
            appeal_from="Department of Justice",
            case_name="Ascent Pharmaceuticals, Inc. v. United States Drug Enforcement Administration",
            case_type_information="Agency, Non-Immigration Petition for Review",
            date_filed=date(2023, 10, 2),
            docket_number="23-6364",
            fee_status="IFP Granted",
            originating_court_information={
                "identifier": "DOJ",
                "name": "Department of Justice",
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


class MockACMSAttachmentPage:
    def __init__(self, court_id):
        pass

    def _parse_text(self, json):
        self.data = ACMSAttachmentPageFactory(
            entry_number=3,
            description="NOTICE OF CRIMINAL APPEAL, on behalf of Appellant Mustapha Raji, OPENED. [Entered: 10/02/2023 11:23 AM]",
            pacer_case_id="9f5ae37f-c44e-4194-b075-3f8f028559c4",
            pacer_doc_id="7fae3c58-1ced-ee11-904c-001dd83058b7",
            date_filed=date(2023, 10, 2),
            date_end=date(2023, 10, 2),
            attachments=[
                ACMSAttachmentFactory(
                    attachment_number=1,
                    description="T-1080 Form",
                    pacer_doc_id="7fae3c58-1ced-ee11-904c-001dd83058b7",
                    page_count=1,
                    acms_document_guid="ea52cd72-1ced-ee11-904d-001dd8306e7a",
                    cost=0.1,
                    permission="Public",
                    file_size=1330,
                    date_filed=date(2024, 3, 28),
                ),
                ACMSAttachmentFactory(
                    attachment_number=2,
                    description="Affidavit",
                    pacer_doc_id="7fae3c58-1ced-ee11-904c-001dd83058b7",
                    page_count=3,
                    acms_document_guid="d1f94280-1ced-ee11-904d-001dd83065dd",
                    cost=0.3,
                    permission="Public",
                    file_size=337,
                    date_filed=date(2024, 3, 28),
                ),
                ACMSAttachmentFactory(
                    attachment_number=3,
                    description="Exhibit",
                    pacer_doc_id="7fae3c58-1ced-ee11-904c-001dd83058b7",
                    page_count=2,
                    acms_document_guid="b6a2a618-1ded-ee11-904d-001dd830668f",
                    cost=0.2,
                    permission="Public",
                    file_size=112,
                    date_filed=date(2024, 3, 28),
                ),
            ],
        )
