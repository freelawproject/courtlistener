from datetime import date

from mock import MagicMock


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
            "date_filed": date(2018, 6, 9),
            "docket_entries": [],
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
    response = MagicMock(text=u"")
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

    def download_pdf(self, *args, **kwargs):
        return MagicMock(content="")
