from datetime import date
from http import HTTPStatus
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse

from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    SCOTUSDocketEntryFactory,
    ScotusDocketMetadataFactory,
    SCOTUSDocumentFactory,
)
from cl.search.models import (
    Docket,
    SCOTUSDocketEntry,
    ScotusDocketMetadata,
    SCOTUSDocument,
)
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory

BASENAMES = ["scotusdocketmetadata", "scotusdocketentry", "scotusdocument"]

# The keys of a serialized SCOTUS docket entry.
ENTRY_KEYS = {
    "resource_uri",
    "id",
    "docket",
    "scotus_documents",
    "date_created",
    "date_modified",
    "entry_number",
    "description",
    "date_filed",
    "sequence_number",
}

# The keys of a serialized SCOTUS document, without its docket_entry link.
DOCUMENT_KEYS = {
    "resource_uri",
    "id",
    "absolute_url",
    "is_available",
    "date_created",
    "date_modified",
    "sha1",
    "page_count",
    "file_size",
    "filepath_local",
    "plain_text",
    "ocr_status",
    "description",
    "document_number",
    "attachment_number",
    "url",
    "filepath_ia",
    "ia_upload_failure_count",
    "thumbnail",
    "thumbnail_status",
}


class ScotusAPITestCase(TestCase):
    """Shared SCOTUS data for the API tests.

    The entry with documents gets its attachment 2 created before attachment
    1, so tests can tell display order apart from id order.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        """Create the users, dockets, entries and documents shared by tests."""
        cls.user = UserFactory()
        cls.superuser = UserFactory(is_staff=True, is_superuser=True)
        cls.court = CourtFactory(id="scotus", jurisdiction="F")
        cls.docket = DocketFactory(court=cls.court, source=Docket.SCRAPER)
        cls.docket_2 = DocketFactory(court=cls.court, source=Docket.SCRAPER)
        cls.metadata = ScotusDocketMetadataFactory(
            docket=cls.docket,
            capital_case=True,
            date_discretionary_court_decision=date(2025, 6, 24),
            questions_presented_file="recap/gov.uscourts.scotus.1/qp.pdf",
        )
        cls.metadata_no_file = ScotusDocketMetadataFactory(docket=cls.docket_2)
        cls.entry = SCOTUSDocketEntryFactory(
            docket=cls.docket,
            entry_number=1,
            sequence_number="2",
            date_filed=date(2025, 1, 10),
        )
        cls.entry_no_docs = SCOTUSDocketEntryFactory(
            docket=cls.docket,
            entry_number=2,
            sequence_number="1",
            date_filed=date(2025, 2, 20),
        )
        cls.entry_no_number = SCOTUSDocketEntryFactory(
            docket=cls.docket_2,
            entry_number=None,
            sequence_number="3",
            date_filed=date(2025, 1, 5),
        )
        cls.attachment_2 = SCOTUSDocumentFactory(
            docket_entry=cls.entry, document_number=1, attachment_number=2
        )
        cls.attachment_1 = SCOTUSDocumentFactory(
            docket_entry=cls.entry,
            document_number=1,
            attachment_number=1,
            filepath_local="recap/gov.uscourts.scotus.1/1.1.pdf",
            sha1="a" * 40,
            ocr_status=SCOTUSDocument.OCR_COMPLETE,
        )
        cls.document_no_number = SCOTUSDocumentFactory(
            docket_entry=cls.entry_no_number,
            document_number=None,
            attachment_number=1,
        )

    @staticmethod
    def list_path(basename: str) -> str:
        """Return the v4 list URL for an endpoint basename."""
        return reverse(f"{basename}-list", kwargs={"version": "v4"})

    @staticmethod
    def detail_path(basename: str, pk: int) -> str:
        """Return the v4 detail URL for an endpoint basename and pk."""
        return reverse(
            f"{basename}-detail", kwargs={"version": "v4", "pk": pk}
        )


class ScotusAPIRoutingTest(ScotusAPITestCase):
    """The SCOTUS endpoints exist in v4 only."""

    async def test_endpoints_are_absent_from_v3(self) -> None:
        """Are the endpoints missing from v3, both as routes and URLs?"""
        for basename in BASENAMES:
            with self.subTest(basename=basename):
                with self.assertRaises(NoReverseMatch):
                    reverse(f"{basename}-list", kwargs={"version": "v3"})
                path = self.list_path(basename).replace("/v4/", "/v3/")
                r = await self.async_client.get(path)
                self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)


class ScotusAPIPermissionTest(ScotusAPITestCase):
    """The SCOTUS endpoints require an account and are read only."""

    async def test_anonymous_users_are_rejected(self) -> None:
        """Do anonymous requests get a 401?"""
        for basename in BASENAMES:
            with self.subTest(basename=basename):
                r = await self.async_client.get(self.list_path(basename))
                self.assertEqual(r.status_code, HTTPStatus.UNAUTHORIZED)

    async def test_write_methods_are_rejected(self) -> None:
        """Are writes refused, even for superusers?

        Plain users fail the model permission check first (403); superusers
        pass it and then hit the read-only viewset (405).
        """
        targets = {
            "scotusdocketmetadata": (ScotusDocketMetadata, self.metadata.pk),
            "scotusdocketentry": (SCOTUSDocketEntry, self.entry.pk),
            "scotusdocument": (SCOTUSDocument, self.attachment_1.pk),
        }
        counts_before = {
            name: await model.objects.acount()
            for name, (model, _) in targets.items()
        }
        for user, expected in (
            (self.user, HTTPStatus.FORBIDDEN),
            (self.superuser, HTTPStatus.METHOD_NOT_ALLOWED),
        ):
            await self.async_client.aforce_login(user)
            for name, (_, pk) in targets.items():
                requests = [
                    ("post", self.list_path(name)),
                    ("put", self.detail_path(name, pk)),
                    ("patch", self.detail_path(name, pk)),
                    ("delete", self.detail_path(name, pk)),
                ]
                for method, path in requests:
                    with self.subTest(
                        user=user.username, endpoint=name, method=method
                    ):
                        r = await getattr(self.async_client, method)(path)
                        self.assertEqual(r.status_code, expected)
        for name, (model, _) in targets.items():
            with self.subTest(endpoint=name):
                self.assertEqual(
                    await model.objects.acount(), counts_before[name]
                )


class ScotusAPISerializationTest(ScotusAPITestCase):
    """The SCOTUS endpoints return SCOTUS fields and links."""

    def setUp(self) -> None:
        """Log in as a plain user."""
        self.async_client.force_login(self.user)

    @staticmethod
    def absolute(path: str) -> str:
        """Return the absolute URL the test client's host gives a path."""
        return f"http://testserver{path}"

    async def test_metadata(self) -> None:
        """Does metadata link its docket and expose its file as a URL?"""
        r = await self.async_client.get(
            self.detail_path("scotusdocketmetadata", self.metadata.pk)
        )
        data = r.json()
        self.assertEqual(
            set(data),
            {
                "resource_uri",
                "id",
                "docket",
                "date_created",
                "date_modified",
                "capital_case",
                "date_discretionary_court_decision",
                "linked_with",
                "questions_presented_url",
                "questions_presented_file",
            },
        )
        self.assertEqual(
            data["docket"],
            self.absolute(self.detail_path("docket", self.docket.pk)),
        )
        self.assertTrue(data["capital_case"])
        self.assertEqual(
            data["questions_presented_file"],
            self.absolute(self.metadata.questions_presented_file.url),
        )

        r = await self.async_client.get(
            self.detail_path("scotusdocketmetadata", self.metadata_no_file.pk)
        )
        self.assertIsNone(r.json()["questions_presented_file"])

    async def test_docket_entry(self) -> None:
        """Does an entry nest its documents in display order?"""
        r = await self.async_client.get(
            self.detail_path("scotusdocketentry", self.entry.pk)
        )
        data = r.json()
        self.assertEqual(set(data), ENTRY_KEYS)
        self.assertEqual(
            data["docket"],
            self.absolute(self.detail_path("docket", self.docket.pk)),
        )
        nested = data["scotus_documents"]
        self.assertEqual(
            [doc["id"] for doc in nested],
            [self.attachment_1.pk, self.attachment_2.pk],
        )
        for doc in nested:
            with self.subTest(document=doc["id"]):
                self.assertEqual(set(doc), DOCUMENT_KEYS)

        r = await self.async_client.get(
            self.detail_path("scotusdocketentry", self.entry_no_docs.pk)
        )
        self.assertEqual(r.json()["scotus_documents"], [])

    async def test_document(self) -> None:
        """Does a document link its entry and expose its file and page?"""
        r = await self.async_client.get(
            self.detail_path("scotusdocument", self.attachment_1.pk)
        )
        data = r.json()
        self.assertEqual(set(data), DOCUMENT_KEYS | {"docket_entry"})
        self.assertEqual(
            data["docket_entry"],
            self.absolute(
                self.detail_path("scotusdocketentry", self.entry.pk)
            ),
        )
        self.assertEqual(
            data["absolute_url"],
            reverse(
                "view_recap_attachment",
                kwargs={
                    "docket_id": self.docket.pk,
                    "doc_num": 1,
                    "att_num": 1,
                    "slug": self.docket.slug,
                },
            ),
        )
        self.assertTrue(data["is_available"])
        self.assertEqual(
            data["filepath_local"],
            self.absolute(self.attachment_1.filepath_local.url),
        )

    async def test_document_without_file_or_page(self) -> None:
        """Do missing files come back as null and missing pages as blanks?

        The blank absolute_url matches what RECAP documents return.
        """
        cases = [
            (self.attachment_2, "filepath_local", None),
            (self.attachment_2, "is_available", False),
            (self.document_no_number, "absolute_url", ""),
        ]
        for document, key, expected in cases:
            with self.subTest(document=document.pk, key=key):
                r = await self.async_client.get(
                    self.detail_path("scotusdocument", document.pk)
                )
                self.assertEqual(r.json()[key], expected)


class ScotusAPIFilterTest(ScotusAPITestCase):
    """The SCOTUS endpoints filter on their own fields and on related ones."""

    def setUp(self) -> None:
        """Log in as a plain user."""
        self.async_client.force_login(self.user)

    async def assert_filter_counts(
        self, basename: str, cases: list[tuple[dict, int]]
    ) -> None:
        """Check the number of results each set of query params returns."""
        for params, expected in cases:
            with self.subTest(endpoint=basename, params=params):
                r = await self.async_client.get(
                    self.list_path(basename), params
                )
                self.assertEqual(r.status_code, HTTPStatus.OK, r.json())
                self.assertEqual(len(r.json()["results"]), expected)

    async def test_metadata_filters(self) -> None:
        """Can metadata be filtered by its fields and its docket?"""
        await self.assert_filter_counts(
            "scotusdocketmetadata",
            [
                ({"id": self.metadata.pk}, 1),
                ({"docket": self.docket.pk}, 1),
                ({"docket__id": self.docket.pk}, 1),
                ({"capital_case": "true"}, 1),
                ({"capital_case": "false"}, 1),
                ({"date_discretionary_court_decision__year": 2025}, 1),
            ],
        )

    async def test_docket_entry_filters(self) -> None:
        """Can entries be filtered by their fields and related objects?

        Filtering through scotus_documents must not repeat an entry once per
        matching document.
        """
        await self.assert_filter_counts(
            "scotusdocketentry",
            [
                ({"docket": self.docket.pk}, 2),
                ({"docket__id": self.docket.pk}, 2),
                ({"entry_number": 1}, 1),
                ({"entry_number__isnull": "true"}, 1),
                ({"date_filed__gte": "2025-02-01"}, 1),
                ({"date_filed__range": "2025-01-01,2025-01-31"}, 2),
                ({"scotus_documents__id": self.attachment_2.pk}, 1),
                ({"scotus_documents__document_number": 1}, 1),
            ],
        )

    async def test_document_filters(self) -> None:
        """Can documents be filtered by their fields and related objects?"""
        await self.assert_filter_counts(
            "scotusdocument",
            [
                ({"docket_entry": self.entry.pk}, 2),
                ({"docket_entry__docket": self.docket.pk}, 2),
                ({"attachment_number": 2}, 1),
                ({"document_number__isnull": "true"}, 1),
                ({"is_available": "true"}, 1),
                ({"is_available": "false"}, 2),
                ({"sha1": "a" * 40}, 1),
                ({"ocr_status": SCOTUSDocument.OCR_COMPLETE}, 1),
            ],
        )

    async def test_unknown_params_are_rejected(self) -> None:
        """Do typos in filter names return a 400 instead of everything?"""
        for basename in BASENAMES:
            with self.subTest(basename=basename):
                r = await self.async_client.get(
                    self.list_path(basename), {"bogus": "1"}
                )
                self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
                self.assertEqual(r.json()["unknown_params"], ["bogus"])

    async def test_docket_entry_ordering(self) -> None:
        """Can entries be ordered by their SCOTUS sequence number?"""
        for order_by, expected in (
            ("sequence_number", [self.entry_no_docs, self.entry]),
            ("-sequence_number", [self.entry, self.entry_no_docs]),
        ):
            with self.subTest(order_by=order_by):
                r = await self.async_client.get(
                    self.list_path("scotusdocketentry"),
                    {"docket": self.docket.pk, "order_by": order_by},
                )
                self.assertEqual(
                    [entry["id"] for entry in r.json()["results"]],
                    [entry.pk for entry in expected],
                )


class ScotusAPIDynamicFieldsTest(ScotusAPITestCase):
    """The fields and omit params work on the nested documents."""

    async def test_nested_fields_and_omit(self) -> None:
        """Do fields and omit trim the nested documents?"""
        await self.async_client.aforce_login(self.user)
        path = self.detail_path("scotusdocketentry", self.entry.pk)
        cases = [
            (
                {"fields": "id,scotus_documents__id"},
                {"id", "scotus_documents"},
                {"id"},
            ),
            (
                {"omit": "scotus_documents__plain_text"},
                ENTRY_KEYS,
                DOCUMENT_KEYS - {"plain_text"},
            ),
        ]
        for params, entry_keys, document_keys in cases:
            with self.subTest(params=params):
                r = await self.async_client.get(path, params)
                self.assertEqual(r.status_code, HTTPStatus.OK)
                data = r.json()
                self.assertEqual(set(data), entry_keys)
                for doc in data["scotus_documents"]:
                    self.assertEqual(set(doc), document_keys)


@mock.patch(
    "cl.api.utils.get_logging_prefix",
    return_value="api:test_counts",
)
class ScotusAPIQueryCountTest(ScotusAPITestCase):
    """The number of queries doesn't grow with the number of results."""

    def count_queries(self, basename: str) -> int:
        """Return the queries a filtered list request runs.

        The filter keeps NoFilterCacheListMixin from serving a cached
        response.
        """
        self.client.force_login(self.user)
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(self.list_path(basename), {"id__gt": 0})
        self.assertEqual(r.status_code, HTTPStatus.OK)
        return len(ctx.captured_queries)

    def test_queries_are_flat(
        self, mock_logging_prefix: mock.MagicMock
    ) -> None:
        """Does adding entries with documents add no queries?"""
        # Warm up process-level caches that other tests may have cleared,
        # so the first measurement doesn't count one-time lookups.
        for name in BASENAMES:
            self.count_queries(name)
        before = {name: self.count_queries(name) for name in BASENAMES}
        for number in range(3, 6):
            entry = SCOTUSDocketEntryFactory(
                docket=self.docket, entry_number=number
            )
            for attachment in (1, 2):
                SCOTUSDocumentFactory(
                    docket_entry=entry, attachment_number=attachment
                )
            ScotusDocketMetadataFactory(docket=DocketFactory(court=self.court))
        for name in BASENAMES:
            with self.subTest(endpoint=name):
                self.assertEqual(self.count_queries(name), before[name])
