from datetime import date
from unittest.mock import MagicMock

from cl.corpus_importer.factories import FreeOpinionRowDataFactory

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
