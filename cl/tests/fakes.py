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


test_patterns = {
    "canb": {
        1: True,
        2: True,
        3: True,
        4: True,
        5: True,
        6: True,
        7: True,
        8: True,
        9: True,
    },
    "gand": {
        5: True,
        6: True,
        7: True,
        8: True,
        9: True,
    },
    "cand": {
        9: True,
        10: False,
        12: True,
        16: False,
        24: True,
        40: True,
        72: False,
        136: False,
        264: True,
    },
    "nysd": {
        9: True,
        10: False,
        12: True,
        16: False,
        24: True,
        40: True,
        72: True,
        136: False,
        264: True,
        520: True,
    },
    "gamb": HTTPError,
    "hib": Timeout,
}


class FakeCaseQueryReport:

    def __init__(self, court_id, pacer_session=None):
        self.pacer_case_id = None
        self.court_id = court_id

    def query(self, pacer_case_id):
        self.pacer_case_id = pacer_case_id

    @property
    def data(self):
        test_pattern = test_patterns.get(self.court_id)
        if not isinstance(test_pattern, dict) and issubclass(
            test_pattern, Exception
        ):
            raise test_pattern()

        if test_pattern:
            if test_pattern[self.pacer_case_id]:
                return CaseQueryDataFactory()
            else:
                return None
        else:
            return CaseQueryDataFactory()
