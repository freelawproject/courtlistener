from datetime import date
from unittest.mock import MagicMock

from httpx import HTTPError, Response, TimeoutException

from cl.corpus_importer.factories import (
    CaseQueryDataFactory,
    FreeOpinionRowDataFactory,
)

DOCKET_NUMBER = "5:18-cr-00227"
CASE_NAME = "United States v. Maldonado-Passage"


class FakeDocketReport:
    response = MagicMock(text="asdf")

    def __init__(self, *args, **kwargs):
        pass

    async def query(self, *args, **kwargs):
        pass

    @property
    def data(self):
        return {
            "docket_number": DOCKET_NUMBER,
            "case_name": CASE_NAME,
            "pacer_case_id": "104490",
            "court_id": "cacd",
            "date_filed": date(2018, 6, 9),
            "docket_entries": [
                {
                    "date_filed": date(2018, 6, 9),
                    "description": "Fake Description",
                    "document_number": "27",
                    "pacer_case_id": "104490",
                    "pacer_doc_id": "02705212035",
                    "pacer_magic_num": "99963705",
                    "pacer_seq_no": "83",
                }
            ],
            "parties": [],
        }


class FakeAppellateDocketReport(FakeDocketReport):
    @property
    def data(self):
        data = super(FakeAppellateDocketReport, self).data
        data["court_id"] = "ca1"
        return data


class FakeNewAppellateCaseDocketReport(FakeDocketReport):
    @property
    def data(self):
        data = super(FakeNewAppellateCaseDocketReport, self).data
        data["court_id"] = "ca1"
        data["docket_number"] = "10-1081"
        data["case_name"] = "United States v. Brown"
        data["pacer_case_id"] = "49959"
        return data


class FakeEmptyAcmsCaseSearch(FakeDocketReport):
    @property
    def data(self):
        return {}


class FakeAcmsCaseSearch(FakeDocketReport):
    @property
    def data(self):
        return {"pcx_caseid": "e85b4453-6c94-4c68-93ed-4e2e0018e842"}


class FakeAcmsDocketReport(FakeDocketReport):
    @property
    def data(self):
        return {
            "court_id": "ca9",
            "pacer_case_id": "e85b4453-6c94-4c68-93ed-4e2e0018e842",
            "docket_number": "25-4097",
            "case_name": "Wortman, et al. v. All Nippon Airways",
            "date_filed": date(2025, 7, 1),
            "appeal_from": "San Francisco, Northern California",
            "fee_status": "Paid",
            "originating_court_information": {
                "name": "San Francisco, Northern California"
            },
            "case_type_information": "Civil, Private",
            "parties": [],
            "docket_entries": [
                {
                    "document_number": 2,
                    "description_html": "<p>fake docket entry</p>",
                    "description": "fake docket entry",
                    "date_entered": "2025-07-01 16:42:00",
                    "date_filed": date(2025, 7, 1),
                    "pacer_doc_id": "acc416ff-d456-f011-877b-001dd80bcf93",
                    "page_count": 6,
                }
            ],
        }


class FakeAcmsDocketReportToUpdate(FakeAcmsDocketReport):
    @property
    def data(self):
        data = super(FakeAcmsDocketReportToUpdate, self).data
        data["court_id"] = "ca2"
        data["docket_number"] = "25-1671"
        data["case_name"] = "G.F.F. v. Trump"
        data["pacer_case_id"] = "2f1af701-d529-410e-a653-376e1fdc4034"
        return data


class FakePossibleCaseNumberApi:
    def __init__(self, *args, **kwargs):
        pass

    async def query(self, *args, **kwargs):
        pass

    def data(self, *args, **kwargs):
        return {
            "docket_number": DOCKET_NUMBER,
            "pacer_case_id": "104490",
            "title": CASE_NAME,
            "pass_through": None,
        }


class FakeAttachmentPage:
    response = MagicMock(text="")
    _parse_text = MagicMock()

    def __init__(self, *args, **kwargs):
        pass

    async def query(self, *args, **kwargs):
        pass

    @property
    def data(self, *args, **kwargs):
        return {
            "pacer_doc_id": "17711118263",
            "document_number": "1",
            "attachments": [],
        }


class FakeAppellateAttachmentPage:
    response = MagicMock(text="")
    _parse_text = MagicMock()

    def __init__(self, *args, **kwargs):
        pass

    async def query(self, *args, **kwargs):
        pass

    @property
    def data(self, *args, **kwargs):
        return {
            "pacer_doc_id": "1208699339",
            "document_number": "1",
            "attachments": [],
        }


class FakeAcmsAttachmentPage(FakeAppellateAttachmentPage):
    @property
    def data(self, *args, **kwargs):
        return {
            "pacer_doc_id": "4e108d6c-ad5b-f011-bec2-001dd80b194b",
            "pacer_case_id": "5d8e355d-b229-4b16-b00f-7552d2f79d4f",
            "entry_number": 9,
            "description": "MOTION [Entered: 07/07/2025 08:41 PM]",
            "date_filed": date(2025, 7, 8),
            "date_end": date(2025, 7, 7),
            "attachments": [
                {
                    "attachment_number": 1,
                    "description": "Motion",
                    "page_count": 30,
                    "pacer_doc_id": "4e108d6c-ad5b-f011-bec2-001dd80b194b",
                    "acms_document_guid": "d1358903-ad5b-f011-a2da-001dd80b00cb",
                    "cost": 3.0,
                    "date_filed": date(2025, 7, 8),
                    "permission": "Public",
                    "file_size": 864.0,
                },
                {
                    "attachment_number": 2,
                    "description": "Declaration",
                    "page_count": 4,
                    "pacer_doc_id": "4e108d6c-ad5b-f011-bec2-001dd80b194b",
                    "acms_document_guid": "2f373c0f-ad5b-f011-a2da-001dd80b00cb",
                    "cost": 0.4,
                    "date_filed": date(2025, 7, 8),
                    "permission": "Public",
                    "file_size": 288.0,
                },
                {
                    "attachment_number": 3,
                    "description": "Declaration",
                    "page_count": 30,
                    "pacer_doc_id": "4e108d6c-ad5b-f011-bec2-001dd80b194b",
                    "acms_document_guid": "c6aae921-ad5b-f011-a2da-001dd80b00cb",
                    "cost": 3.0,
                    "date_filed": date(2025, 7, 8),
                    "permission": "Public",
                    "file_size": 11264.0,
                },
            ],
        }


class FakeFreeOpinionReport:
    def __init__(self, *args, **kwargs):
        pass

    async def download_pdf(self, *args, **kwargs) -> tuple[Response, str]:
        return Response(200, content=b"Hello World"), ""

    async def query(self, *args, **kwargs):
        pass

    @property
    def data(self, *args, **kwargs):
        return [
            FreeOpinionRowDataFactory(
                court_id="cand", docket_number="5:18-ap-07075"
            )
        ]


class FakeConfirmationPage:
    def __init__(self, *args, **kwargs):
        pass

    async def query(self, *args, **kwargs):
        pass

    @property
    def data(self, *args, **kwargs):
        return {}

    @property
    def response(self, *args, **kwargs):
        pass


class FakeAvailableConfirmationPage(FakeConfirmationPage):
    @property
    def data(self, *args, **kwargs):
        return {
            "docket_number": "2:25-cv-10997-MFL-CI",
            "cost": "2.00",
            "billable_pages": "20",
            "document_description": "Image1-0",
        }


test_patterns = {
    "canb": {
        1: True,
        2: True,
        4: False,
        8: False,
        16: False,
        32: False,
        64: False,
    },
    "gand": {
        5: True,
        6: True,
        7: True,
        8: True,
        9: True,
    },
    "cand": {
        9: False,  # 1
        10: False,  # 2
        12: True,  # 4
        13: True,  # 5
        16: True,  # 8
        18: True,  # 10
        24: True,  # 16
        40: False,  # 32
        72: False,  # 64
        136: False,  # 128
        137: True,  # 129
        264: True,  # 256
    },
    "nysd": {
        9: False,
        10: False,
        12: False,
        16: True,
        24: True,
        40: True,
        72: True,
        104: True,
        136: True,
        168: True,
        200: True,
        232: True,
        264: True,
        296: True,
        328: True,
        360: True,
        392: True,
        424: True,
        456: True,
    },
    "txed": {
        9: True,
        10: True,
        11: True,
        12: True,
        13: False,
        16: False,
    },
    "gamb": HTTPError,
    "hib": TimeoutException,
    "cacd": {
        1: False,
        2: False,
        4: False,
        8: False,
        16: False,
        32: False,
        64: False,
    },
    "vib": {
        1: False,
        2: False,
        4: False,
        8: False,
        16: False,
        32: False,
        64: False,
    },
    "mowd": {
        3000: False,
        3008: False,
        3015: True,
        3017: True,
        3019: True,
        3020: False,
        3021: True,
        3022: True,
    },
}


class FakeCaseQueryResponse:
    """Mock a Fake CaseQuery Request Response"""

    def __init__(self, text):
        self.text = text


class FakeCaseQueryReport:
    def __init__(self, court_id, pacer_session=None):
        self.pacer_case_id = None
        self.court_id = court_id

    async def query(self, pacer_case_id):
        self.pacer_case_id = pacer_case_id

    @property
    def data(self):
        test_pattern = test_patterns.get(self.court_id, {})
        if not isinstance(test_pattern, dict) and issubclass(
            test_pattern, (HTTPError | TimeoutException)
        ):
            raise test_pattern(message="Test Pattern Exception")

        if test_pattern and test_pattern.get(self.pacer_case_id):
            return CaseQueryDataFactory()
        return None

    @property
    def response(self):
        return FakeCaseQueryResponse("<span>Test</span>")
