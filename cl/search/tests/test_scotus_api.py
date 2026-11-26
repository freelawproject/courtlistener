import re
from datetime import date
from http import HTTPStatus
from unittest import mock

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse
from waffle.testutils import override_flag

from cl.api.utils import LoggingMixin
from cl.corpus_importer.tasks import add_scotus_placeholder_document
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
PREFIXES = [
    "scotus-docket-metadata",
    "scotus-docket-entries",
    "scotus-documents",
]

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

# The keys of a SCOTUS document on list pages and nested in its entry, which
# leave out plain_text.
LISTED_DOCUMENT_KEYS = DOCUMENT_KEYS - {"plain_text"}


class ScotusAPITestCase(TestCase):
    """Shared SCOTUS data for the API tests, with the endpoints' flag on.

    The flag is enabled in setUp, so subclasses that override setUp must
    call super().setUp().

    The entry with documents gets its attachment 2 created before attachment
    1, so tests can tell display order apart from id order. The entry
    without documents gets the empty placeholder document production gives
    such entries, which the API must hide.
    """

    def setUp(self) -> None:
        """Turn on the endpoints' flag in a waffle cache of this test's own.

        Tests run in parallel and share the cache, so a common prefix would
        let a test that turns the flag off leak its cached value into others.
        The flag is set here rather than with a decorator because async tests
        can't write it to the database.
        """
        super().setUp()
        self.enterContext(override_settings(WAFFLE_CACHE_PREFIX=self.id()))
        self.enterContext(override_flag("scotus-api", active=True))

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
        add_scotus_placeholder_document(cls.entry_no_docs)
        cls.placeholder = SCOTUSDocument.objects.get(
            docket_entry=cls.entry_no_docs
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


class ScotusAPIFlagTest(ScotusAPITestCase):
    """The SCOTUS endpoints stay hidden until the scotus-api flag is on."""

    def setUp(self) -> None:
        """Log in as a plain user."""
        super().setUp()
        self.client.force_login(self.user)

    def get_root_prefixes(self) -> set[str]:
        """Return the route prefixes the v4 API root lists."""
        r = self.client.get(reverse("api-root", kwargs={"version": "v4"}))
        self.assertEqual(r.status_code, HTTPStatus.OK)
        return set(r.json())

    def test_endpoints_are_hidden_when_flag_is_off(self) -> None:
        """Do the endpoints 404 and drop out of the API root?"""
        detail_pks = {
            "scotusdocketmetadata": self.metadata.pk,
            "scotusdocketentry": self.entry.pk,
            "scotusdocument": self.attachment_1.pk,
        }
        with override_flag("scotus-api", active=False):
            for basename in BASENAMES:
                with self.subTest(basename=basename):
                    r = self.client.get(self.list_path(basename))
                    self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)
                    r = self.client.get(
                        self.detail_path(basename, detail_pks[basename])
                    )
                    self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)
            root_prefixes = self.get_root_prefixes()
        self.assertTrue(root_prefixes.isdisjoint(PREFIXES), root_prefixes)
        # Unflagged routes are still listed.
        self.assertIn("dockets", root_prefixes)

    def test_anonymous_users_get_404_when_flag_is_off(self) -> None:
        """Does the flag hide the endpoints before asking for credentials?"""
        self.client.logout()
        with override_flag("scotus-api", active=False):
            for basename in BASENAMES:
                with self.subTest(basename=basename):
                    r = self.client.get(self.list_path(basename))
                    self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)

    def test_endpoints_are_listed_when_flag_is_on(self) -> None:
        """Does the API root list the endpoints once the flag is on?"""
        root_prefixes = self.get_root_prefixes()
        self.assertTrue(set(PREFIXES) <= root_prefixes, root_prefixes)


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
        super().setUp()
        self.async_client.force_login(self.user)

    @staticmethod
    def absolute(path: str) -> str:
        """Return the absolute URL the test client's host gives a path."""
        return f"http://testserver{path}"

    async def test_metadata(self) -> None:
        """Does metadata link its docket and expose its file's path?"""
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
            self.metadata.questions_presented_file.name,
        )

        r = await self.async_client.get(
            self.detail_path("scotusdocketmetadata", self.metadata_no_file.pk)
        )
        self.assertIsNone(r.json()["questions_presented_file"])

    async def test_docket_entry(self) -> None:
        """Does an entry nest its documents in display order, but not its placeholder?"""
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
                self.assertEqual(set(doc), LISTED_DOCUMENT_KEYS)

        r = await self.async_client.get(
            self.detail_path("scotusdocketentry", self.entry_no_docs.pk)
        )
        self.assertEqual(r.json()["scotus_documents"], [])

    async def test_document(self) -> None:
        """Does a document link its entry and expose its file's path and page?"""
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
            self.attachment_1.filepath_local.name,
        )

    async def test_placeholders_are_hidden(self) -> None:
        """Are placeholder documents missing from the document endpoints?"""
        r = await self.async_client.get(
            self.detail_path("scotusdocument", self.placeholder.pk)
        )
        self.assertEqual(r.status_code, HTTPStatus.NOT_FOUND)
        r = await self.async_client.get(self.list_path("scotusdocument"))
        self.assertNotIn(
            self.placeholder.pk, [doc["id"] for doc in r.json()["results"]]
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
        super().setUp()
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
                # Only entry_no_number's real document, not the placeholder.
                ({"scotus_documents__document_number__isnull": "true"}, 1),
            ],
        )

    async def test_document_filters(self) -> None:
        """Can documents be filtered by their fields and related objects?"""
        await self.assert_filter_counts(
            "scotusdocument",
            [
                ({"docket_entry": self.entry.pk}, 2),
                ({"docket_entry": self.entry_no_docs.pk}, 0),
                # Both documents of the entry that has an available one.
                ({"docket_entry__scotus_documents__is_available": "true"}, 2),
                ({"docket_entry__docket": self.docket.pk}, 2),
                ({"document_number__isnull": "true"}, 1),
                ({"is_available": "true"}, 1),
                ({"is_available": "false"}, 2),
                ({"sha1": "a" * 40}, 1),
                ({"ocr_status": SCOTUSDocument.OCR_COMPLETE}, 1),
            ],
        )

    async def test_invalid_document_filter_values_are_rejected(self) -> None:
        """Do bad values in document filters on entries return a 400?"""
        r = await self.async_client.get(
            self.list_path("scotusdocketentry"),
            {"scotus_documents__document_number": "abc"},
        )
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
        self.assertIn("scotus_documents__document_number", r.json())

    async def test_unknown_params_are_rejected(self) -> None:
        """Do typos in filter names return a 400 instead of everything?"""
        for basename in BASENAMES:
            with self.subTest(basename=basename):
                r = await self.async_client.get(
                    self.list_path(basename), {"bogus": "1"}
                )
                self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
                self.assertEqual(r.json()["unknown_params"], ["bogus"])

    async def test_unindexed_sort_keys_are_ignored(self) -> None:
        """Do entries ignore sort keys their table has no index for?

        Sorting the whole table on them would be slow, so the view doesn't
        offer them and the default -id order applies. Each key here would put
        self.entry first if it were honored.
        """
        for order_by in ("-sequence_number", "entry_number", "date_filed"):
            with self.subTest(order_by=order_by):
                r = await self.async_client.get(
                    self.list_path("scotusdocketentry"),
                    {"docket": self.docket.pk, "order_by": order_by},
                )
                self.assertEqual(
                    [entry["id"] for entry in r.json()["results"]],
                    [self.entry_no_docs.pk, self.entry.pk],
                )


class ScotusAPIDynamicFieldsTest(ScotusAPITestCase):
    """The fields and omit params work on the nested documents."""

    async def test_nested_fields_and_omit(self) -> None:
        """Do fields and omit trim the nested documents?

        They must keep leaving out placeholders and keep their display order.
        """
        await self.async_client.aforce_login(self.user)
        expected_ids = {
            self.entry.pk: [self.attachment_1.pk, self.attachment_2.pk],
            self.entry_no_docs.pk: [],
        }
        cases = [
            (
                {"fields": "id,scotus_documents__id"},
                {"id", "scotus_documents"},
                {"id"},
            ),
            (
                {"omit": "scotus_documents__description"},
                ENTRY_KEYS,
                LISTED_DOCUMENT_KEYS - {"description"},
            ),
        ]
        for params, entry_keys, document_keys in cases:
            for entry_pk, ids in expected_ids.items():
                with self.subTest(params=params, entry=entry_pk):
                    r = await self.async_client.get(
                        self.detail_path("scotusdocketentry", entry_pk),
                        params,
                    )
                    self.assertEqual(r.status_code, HTTPStatus.OK)
                    data = r.json()
                    self.assertEqual(set(data), entry_keys)
                    nested = data["scotus_documents"]
                    self.assertEqual([doc["id"] for doc in nested], ids)
                    for doc in nested:
                        self.assertEqual(set(doc), document_keys)


class ScotusAPIRelatedColumnsTest(ScotusAPITestCase):
    """The documents endpoint reads only the related columns it uses."""

    def setUp(self) -> None:
        """Log in as a plain user."""
        super().setUp()
        self.client.force_login(self.user)

    def test_documents_read_only_docket_slug(self) -> None:
        """Do documents read just the entry and docket columns they need?

        absolute_url needs the entry's docket_id and the docket's slug; the
        rest of the docket row is wide and unused.
        """
        expected_url = reverse(
            "view_recap_attachment",
            kwargs={
                "docket_id": self.docket.pk,
                "doc_num": 1,
                "att_num": 1,
                "slug": self.docket.slug,
            },
        )
        cases = [
            (self.list_path("scotusdocument"), {"id": self.attachment_1.pk}),
            (self.detail_path("scotusdocument", self.attachment_1.pk), {}),
        ]
        for path, params in cases:
            with self.subTest(path=path):
                with CaptureQueriesContext(connection) as ctx:
                    r = self.client.get(path, params)
                self.assertEqual(r.status_code, HTTPStatus.OK)
                data = r.json()
                document = data["results"][0] if "results" in data else data
                self.assertEqual(document["absolute_url"], expected_url)

                selects = [
                    q["sql"].split(" FROM ")[0]
                    for q in ctx.captured_queries
                    if 'FROM "search_scotusdocument"' in q["sql"]
                ]
                self.assertEqual(len(selects), 1, selects)
                for table, columns in (
                    ("search_scotusdocketentry", {"id", "docket_id"}),
                    ("search_docket", {"id", "slug"}),
                ):
                    selected = set(
                        re.findall(rf'"{table}"\."(\w+)"', selects[0])
                    )
                    self.assertEqual(selected, columns)

    def test_entries_read_only_docket_slug(self) -> None:
        """Do entries read just the docket columns their documents need?

        The nested documents' absolute_url needs the docket's slug; the rest
        of the docket row is wide and unused.
        """
        expected_url = reverse(
            "view_recap_attachment",
            kwargs={
                "docket_id": self.docket.pk,
                "doc_num": 1,
                "att_num": 1,
                "slug": self.docket.slug,
            },
        )
        cases = [
            (self.list_path("scotusdocketentry"), {"id": self.entry.pk}),
            (
                self.list_path("scotusdocketentry"),
                {"scotus_documents__id": self.attachment_1.pk},
            ),
            (self.detail_path("scotusdocketentry", self.entry.pk), {}),
        ]
        for path, params in cases:
            with self.subTest(path=path, params=params):
                with CaptureQueriesContext(connection) as ctx:
                    r = self.client.get(path, params)
                self.assertEqual(r.status_code, HTTPStatus.OK)
                data = r.json()
                entry = data["results"][0] if "results" in data else data
                urls = {
                    doc["id"]: doc["absolute_url"]
                    for doc in entry["scotus_documents"]
                }
                self.assertEqual(urls[self.attachment_1.pk], expected_url)

                selects = [
                    q["sql"].split(" FROM ")[0]
                    for q in ctx.captured_queries
                    if 'FROM "search_scotusdocketentry"' in q["sql"]
                ]
                self.assertEqual(len(selects), 1, selects)
                selected = set(
                    re.findall(r'"search_docket"\."(\w+)"', selects[0])
                )
                self.assertEqual(selected, {"id", "slug"})

    def test_related_filter_lookups_read_only_ids(self) -> None:
        """Do related filters look up their object by reading only its id?

        A related filter's exact value is checked by fetching that object,
        and only its pk is used afterwards.
        """
        cases = [
            ("scotusdocument", {"docket_entry": self.entry.pk}, 2),
            ("scotusdocketentry", {"docket": self.docket.pk}, 2),
            (
                "scotusdocketentry",
                {"scotus_documents": self.attachment_1.pk},
                1,
            ),
            ("scotusdocketmetadata", {"docket": self.docket.pk}, 1),
        ]
        tables = {
            "docket_entry": "search_scotusdocketentry",
            "docket": "search_docket",
            "scotus_documents": "search_scotusdocument",
        }
        for basename, params, expected_count in cases:
            with self.subTest(endpoint=basename, params=params):
                with CaptureQueriesContext(connection) as ctx:
                    r = self.client.get(self.list_path(basename), params)
                self.assertEqual(r.status_code, HTTPStatus.OK)
                self.assertEqual(len(r.json()["results"]), expected_count)

                table = tables[next(iter(params))]
                lookups = [
                    q["sql"]
                    for q in ctx.captured_queries
                    if re.search(rf'"{table}"\."id" = \d+\)? LIMIT', q["sql"])
                ]
                self.assertEqual(len(lookups), 1, lookups)
                selected = set(
                    re.findall(
                        rf'"{table}"\."(\w+)"', lookups[0].split(" FROM ")[0]
                    )
                )
                self.assertEqual(selected, {"id"})


class ScotusAPIPlainTextTest(ScotusAPITestCase):
    """Only the document detail endpoint returns, or reads, plain_text.

    plain_text can be a whole PDF's text, so a page of documents with it can
    exhaust the server's memory.
    """

    def setUp(self) -> None:
        """Log in as a plain user."""
        super().setUp()
        self.client.force_login(self.user)

    def get_documents(
        self, path: str, params: dict[str, str]
    ) -> tuple[list[dict], list[str]]:
        """Return the documents a request serializes and the SQL it ran.

        Documents may be top-level or nested in entries; the SQL is limited
        to the queries against the SCOTUS documents table.
        """
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(path, params)
        self.assertEqual(r.status_code, HTTPStatus.OK)
        data = r.json()
        rows = data.get("results", [data])
        documents = [
            document
            for row in rows
            for document in row.get("scotus_documents", [row])
        ]
        sql = [
            query["sql"]
            for query in ctx.captured_queries
            if '"search_scotusdocument"' in query["sql"]
        ]
        return documents, sql

    def test_lists_and_nested_documents_leave_out_plain_text(self) -> None:
        """Do lists and nested documents leave out plain_text?

        It must stay out even when the fields param asks for it, and it must
        not be read from the database.
        """
        entry_path = self.detail_path("scotusdocketentry", self.entry.pk)
        cases = [
            (self.list_path("scotusdocument"), {}),
            (self.list_path("scotusdocketentry"), {}),
            (entry_path, {}),
            (entry_path, {"omit": "scotus_documents__description"}),
            (
                entry_path,
                {
                    "fields": "id,scotus_documents__id,scotus_documents__plain_text"
                },
            ),
        ]
        for path, params in cases:
            with self.subTest(path=path, params=params):
                documents, sql = self.get_documents(path, params)
                self.assertTrue(documents)
                for document in documents:
                    self.assertNotIn("plain_text", document)
                for query in sql:
                    self.assertNotIn('"plain_text"', query)

    def test_document_detail_returns_plain_text(self) -> None:
        """Does the document detail endpoint still return plain_text?"""
        SCOTUSDocument.objects.filter(pk=self.attachment_1.pk).update(
            plain_text="The text of the petition."
        )
        documents, _ = self.get_documents(
            self.detail_path("scotusdocument", self.attachment_1.pk), {}
        )
        self.assertEqual(
            documents[0]["plain_text"], "The text of the petition."
        )


# The usage stats write milestone events when their request counters reach
# certain values. Those counters live in Redis and other tests reset them, so
# the events are turned off to keep them from adding queries at random.
@mock.patch.object(LoggingMixin, "_handle_events")
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
        self,
        mock_logging_prefix: mock.MagicMock,
        mock_handle_events: mock.MagicMock,
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
