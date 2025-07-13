from cl.search.factories import CourtFactory, RECAPDocumentFactory
from cl.users.factories import UserFactory, UserProfileWithParentsFactory


class PrayAndPayMixin:
    """Pray And Pay test case factories"""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.user = UserFactory()
        cls.user_2 = UserFactory()
        cls.user_3 = UserFactory()

        # Create profile for test user records
        UserProfileWithParentsFactory(user=cls.user)
        UserProfileWithParentsFactory(user=cls.user_2)
        UserProfileWithParentsFactory(user=cls.user_3)

        cls.rd_1 = RECAPDocumentFactory(
            pacer_doc_id="98763421",
            document_number="1",
            is_available=True,
        )
        cls.rd_2 = RECAPDocumentFactory(
            pacer_doc_id="98763422",
            document_number="2",
            is_available=False,
        )

        cls.rd_3 = RECAPDocumentFactory(
            pacer_doc_id="98763423",
            document_number="3",
            is_available=False,
        )
        cls.rd_4 = RECAPDocumentFactory(
            pacer_doc_id="98763424",
            document_number="4",
            is_available=False,
        )

        cls.rd_5 = RECAPDocumentFactory(
            pacer_doc_id="98763425",
            document_number="5",
            is_available=False,
        )

        cls.rd_6 = RECAPDocumentFactory(
            pacer_doc_id="98763426",
            document_number="6",
            is_available=False,
        )


class CourtMixin:
    """Court test case factories"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.court_1 = CourtFactory(
            id="ca1",
            full_name="First Circuit",
            jurisdiction="F",
            citation_string="1st Cir.",
            url="https://www.ca1.uscourts.gov/",
        )
        cls.court_2 = CourtFactory(
            id="test",
            full_name="Testing Supreme Court",
            jurisdiction="F",
            citation_string="Test",
            url="https://www.courtlistener.com/",
        )
