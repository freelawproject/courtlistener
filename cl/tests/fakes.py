from datetime import date
from unittest.mock import MagicMock

from requests.exceptions import HTTPError, Timeout

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

    def query(self, *args, **kwargs):
        pass

    @property
    def data(self):
        return {
            "docket_number": DOCKET_NUMBER,
            "case_name": CASE_NAME,
            "pacer_case_id": "104490",
            "court_id": "scotus",
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


class FakePossibleCaseNumberApi:
    def __init__(self, *args, **kwargs):
        pass

    def query(self, *args, **kwargs):
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

    def query(self, *args, **kwargs):
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

    def query(self, *args, **kwargs):
        pass

    @property
    def data(self, *args, **kwargs):
        return {
            "pacer_doc_id": "1208699339",
            "document_number": "1",
            "attachments": [],
        }


class FakeFreeOpinionReport:
    def __init__(self, *args, **kwargs):
        pass

    def download_pdf(self, *args, **kwargs) -> tuple[MagicMock, str]:
        return MagicMock(content=b""), ""

    def query(self, *args, **kwargs):
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

    def query(self, *args, **kwargs):
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
    "hib": Timeout,
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
}


class FakeCaseQueryResponse:
    """Mock a Fake CaseQuery Request Response"""

    def __init__(self, text):
        self.text = text


class FakeCaseQueryReport:

    def __init__(self, court_id, pacer_session=None):
        self.pacer_case_id = None
        self.court_id = court_id

    def query(self, pacer_case_id):
        self.pacer_case_id = pacer_case_id

    @property
    def data(self):
        test_pattern = test_patterns.get(self.court_id, {})
        if not isinstance(test_pattern, dict) and issubclass(
            test_pattern, Exception
        ):
            raise test_pattern()

        if test_pattern and test_pattern.get(self.pacer_case_id):
            return CaseQueryDataFactory()
        return None

    @property
    def response(self):
        return FakeCaseQueryResponse("<span>Test</span>")
