from contextlib import AbstractContextManager, nullcontext
from unittest import mock

from django.test.utils import override_settings

from cl.alerts.factories import AlertFactory
from cl.alerts.models import SEARCH_TYPES, Alert, ScheduledAlertHit
from cl.alerts.utils import prepare_percolator_content
from cl.api.factories import WebhookFactory
from cl.api.models import WebhookEventType
from cl.corpus_importer.tasks import (
    download_scotus_document_pdf,
    merge_scotus_docket,
    merge_scotus_document,
    percolate_scotus_document,
)
from cl.lib.redis_utils import get_redis_interface
from cl.search.documents import (
    RECAPPercolator,
)
from cl.search.factories import (
    CourtFactory,
    DocketEntryFactory,
    DocketFactory,
    RECAPDocumentFactory,
    ScotusDocketDataFactory,
    SCOTUSDocketEntryFactory,
    ScotusDocketMetadataFactory,
    SCOTUSDocumentFactory,
    SCOTUSPartyDataFactory,
)
from cl.search.models import Docket, SCOTUSDocketEntry, SCOTUSDocument
from cl.tests.cases import ESIndexTestCase, TransactionTestCase
from cl.users.factories import UserProfileWithParentsFactory


@override_settings(
    PERCOLATOR_SCOTUS_SEARCH_ALERTS_ENABLED=True,
    PERCOLATOR_RECAP_SEARCH_ALERTS_ENABLED=False,
)
@mock.patch(
    "cl.alerts.utils.get_alerts_set_prefix",
    return_value="alert_hits_scotus_percolator",
)
class SCOTUSAlertsPercolatorTest(ESIndexTestCase, TransactionTestCase):
    """SCOTUS content is percolated against the RECAP percolator index on
    every indexing update, without missing or duplicating alert hits.
    """

    @classmethod
    def setUpClass(cls) -> None:
        """Build the people and RECAP indices once for the class."""
        super().setUpClass()
        cls.rebuild_index("people_db.Person")
        cls.rebuild_index("search.Docket")

    def setUp(self) -> None:
        """Start each test with an empty percolator index and no recorded
        alert hits, plus the scotus court and an alert owner.
        """
        RECAPPercolator._index.delete(ignore=404)
        RECAPPercolator.init()
        self.r = get_redis_interface("CACHE")
        if keys := self.r.keys("alert_hits_scotus_percolator:*"):
            self.r.delete(*keys)
        self.court = CourtFactory(id="scotus", jurisdiction="F")
        self.user = UserProfileWithParentsFactory().user
        super().setUp()

    def _make_alert(
        self, query: str, alert_type: str = SEARCH_TYPES.RECAP
    ) -> Alert:
        """Create a daily alert, which is always scheduled regardless of the
        user's membership.
        """
        return AlertFactory(
            user=self.user,
            rate=Alert.DAILY,
            query=query,
            alert_type=alert_type,
        )

    def _make_scotus_entry(self) -> SCOTUSDocketEntry:
        """Create a SCOTUS docket the way merge_scotus_docket does: its
        metadata is what makes it SCOTUS content in ES.
        """
        docket = DocketFactory(court=self.court, source=Docket.SCRAPER)
        ScotusDocketMetadataFactory(docket=docket)
        return SCOTUSDocketEntryFactory(docket=docket)

    def _hits(self, alert: Alert) -> list[ScheduledAlertHit]:
        """Return the hits scheduled for an alert."""
        return list(ScheduledAlertHit.objects.filter(alert=alert))

    def _count_percolations(self) -> AbstractContextManager[mock.MagicMock]:
        """Count percolations by wrapping prepare_percolator_content."""
        return mock.patch(
            "cl.alerts.tasks.prepare_percolator_content",
            wraps=prepare_percolator_content,
        )

    def test_new_document_is_percolated_once_its_pdf_is_processed(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """A new SCOTUS document whose PDF will be downloaded isn't
        percolated when created, nor when its text is saved. It's percolated
        once by percolate_scotus_document, the last step of its PDF chain,
        so alerts on its text match too.
        """
        description_alert = self._make_alert('q="writ of certiorari"&type=r')
        text_alert = self._make_alert('q="habeas petition"&type=r')
        other_court_alert = self._make_alert(
            'q="writ of certiorari"&type=r&court=ca1'
        )
        entry = self._make_scotus_entry()

        with (
            self._count_percolations() as mock_percolate,
            mock.patch("cl.corpus_importer.tasks.chain") as mock_chain,
        ):
            created, doc_pk = merge_scotus_document(
                entry,
                {
                    "document_number": 1,
                    "attachment_number": 1,
                    "description": "Petition for a writ of certiorari",
                    "document_url": "https://www.supremecourt.gov/a.pdf",
                },
                download_file=True,
            )
        self.assertTrue(created)
        self.assertEqual(mock_percolate.call_count, 0)
        self.assertEqual(
            mock_chain.call_args.args[-1], percolate_scotus_document.si(doc_pk)
        )

        scotus_document = SCOTUSDocument.objects.get(pk=doc_pk)
        scotus_document.plain_text = "The habeas petition is denied."
        with self._count_percolations() as mock_percolate:
            scotus_document.save(update_fields=["plain_text"])
        self.assertEqual(mock_percolate.call_count, 0)

        with self._count_percolations() as mock_percolate:
            percolate_scotus_document(doc_pk)
        self.assertEqual(mock_percolate.call_count, 1)
        hits = self._hits(description_alert)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].object_id, entry.docket_id)
        self.assertEqual(hits[0].content_type.model, "scotusdocument")
        child_doc = hits[0].document_content["child_docs"][0]
        self.assertEqual(child_doc["uid"], f"scotus_{doc_pk}")
        self.assertEqual(len(self._hits(text_alert)), 1)
        self.assertEqual(self._hits(other_court_alert), [])

    def test_failed_pdf_download_still_percolates_the_document(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """If the PDF download fails the chain stops, so the document is
        percolated right away with its metadata.
        """
        scotus_document = SCOTUSDocumentFactory(
            docket_entry=self._make_scotus_entry()
        )
        with (
            mock.patch(
                "cl.corpus_importer.tasks.download_document_in_stream",
                return_value=nullcontext(None),
            ),
            mock.patch(
                "cl.corpus_importer.tasks.percolate_scotus_document.delay"
            ) as mock_percolate_task,
        ):
            download_scotus_document_pdf(scotus_document.pk)
        mock_percolate_task.assert_called_once_with(scotus_document.pk)

    def test_failed_pdf_chain_still_percolates_the_document(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """The PDF chain is sent with percolate_scotus_document as its error
        callback, so a task that fails for good (e.g. an HTTP error on the
        download) still gets the new document percolated. Eager chains
        re-raise instead of running error callbacks, so this checks the
        wiring; the other tests cover what the task does.
        """
        with mock.patch("cl.corpus_importer.tasks.chain") as mock_chain:
            _, doc_pk = merge_scotus_document(
                self._make_scotus_entry(),
                {
                    "document_number": 1,
                    "attachment_number": 1,
                    "description": "Petition for a writ of certiorari",
                    "document_url": "https://www.supremecourt.gov/a.pdf",
                },
                download_file=True,
            )
        pdf_chain = mock_chain.return_value
        pdf_chain.link_error.assert_called_once_with(
            percolate_scotus_document.si(doc_pk)
        )
        pdf_chain.apply_async.assert_called_once_with()

    def test_document_without_a_pdf_download_is_percolated_on_creation(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """A SCOTUS document created without a PDF download coming is
        percolated when it's created.
        """
        alert = self._make_alert('q="writ of certiorari"&type=r')
        with self._count_percolations() as mock_percolate:
            SCOTUSDocumentFactory(
                docket_entry=self._make_scotus_entry(),
                description="Petition for a writ of certiorari",
            )
        self.assertEqual(mock_percolate.call_count, 1)
        self.assertEqual(len(self._hits(alert)), 1)

    def test_scotus_updates_are_percolated_without_duplicate_hits(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """Updates to SCOTUS documents, entries, dockets and their metadata
        are percolated. An alert that already hit a document or docket
        doesn't hit it again.
        """
        entry = self._make_scotus_entry()
        docket = entry.docket
        first_alert = self._make_alert('q="writ of certiorari"&type=r')
        scotus_document = SCOTUSDocumentFactory(
            docket_entry=entry, description="Petition for a writ of certiorari"
        )
        self.assertEqual(len(self._hits(first_alert)), 1)

        def update_document() -> None:
            """Change the document's description."""
            scotus_document.description = (
                "Brief in opposition to the writ of certiorari"
            )
            scotus_document.save(update_fields=["description"])

        def update_entry() -> None:
            """Change the docket entry's description."""
            entry.description = "Motion to dismiss granted"
            entry.save()

        def update_docket() -> None:
            """Change the docket's case name."""
            docket.case_name = "Roe v. Wade"
            docket.save()

        def update_metadata() -> None:
            """Turn on capital_case in the docket's SCOTUS metadata."""
            docket.scotus_metadata.capital_case = True
            docket.scotus_metadata.save()

        # (alert query, alert type, change to make, hit content type)
        cases = [
            (
                'q="brief in opposition"&type=r',
                SEARCH_TYPES.RECAP,
                update_document,
                "scotusdocument",
            ),
            (
                'q="motion to dismiss"&type=r',
                SEARCH_TYPES.RECAP,
                update_entry,
                "scotusdocument",
            ),
            (
                'q="Roe v. Wade"&type=d',
                SEARCH_TYPES.DOCKETS,
                update_docket,
                "docket",
            ),
            (
                "q=capital_case:true&type=d",
                SEARCH_TYPES.DOCKETS,
                update_metadata,
                "docket",
            ),
        ]
        for query, alert_type, change, content_type in cases:
            with self.subTest(query=query):
                alert = self._make_alert(query, alert_type)
                with self._count_percolations() as mock_percolate:
                    change()
                self.assertEqual(mock_percolate.call_count, 1)
                hits = self._hits(alert)
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0].content_type.model, content_type)
                # Updated content is percolated again, but the first alert
                # never gets a second hit for the same document.
                self.assertEqual(len(self._hits(first_alert)), 1)

    def test_scotus_docket_percolated_after_its_parties(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """merge_scotus_docket percolates a docket once its parties are
        indexed, so party alerts match it. Merging again percolates it again
        without duplicating hits, and matches alerts on the new data.
        """
        party_alert = self._make_alert(
            "party_name=Encino Motorcars&type=d", SEARCH_TYPES.DOCKETS
        )
        report_data = ScotusDocketDataFactory(
            docket_entries=[],
            questions_presented=None,
            parties=[
                SCOTUSPartyDataFactory(
                    name="Encino Motorcars, LLC", type="Petitioner"
                )
            ],
        )

        with self._count_percolations() as mock_percolate:
            docket, _, _ = merge_scotus_docket(
                report_data, download_file=False
            )
        self.assertEqual(mock_percolate.call_count, 1)
        hits = self._hits(party_alert)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].object_id, docket.pk)
        self.assertEqual(hits[0].content_type.model, "docket")

        case_name_alert = self._make_alert(
            'q="Encino Motorcars, LLC v. Navarro"&type=d',
            SEARCH_TYPES.DOCKETS,
        )
        report_data["case_name"] = "Encino Motorcars, LLC v. Navarro"
        with self._count_percolations() as mock_percolate:
            merge_scotus_docket(report_data, download_file=False)
        # The docket's own save is skipped; it's percolated after parties.
        self.assertEqual(mock_percolate.call_count, 1)
        self.assertEqual(len(self._hits(party_alert)), 1)
        self.assertEqual(len(self._hits(case_name_alert)), 1)

    def test_scotus_webhooks_follow_the_docket_alert_webhooks_setting(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """SCOTUS search alert hits only send webhooks when
        SCOTUS_ALERT_WEBHOOKS_ENABLED is on. The hit is still
        scheduled for the email either way.
        """
        WebhookFactory(
            user=self.user,
            event_type=WebhookEventType.SEARCH_ALERT,
            url="https://example.com/",
            enabled=True,
        )
        alert = self._make_alert('q="writ of certiorari"&type=r')
        for enabled in (False, True):
            with (
                self.subTest(enabled=enabled),
                override_settings(SCOTUS_ALERT_WEBHOOKS_ENABLED=enabled),
                mock.patch(
                    "cl.alerts.tasks.send_search_alert_webhook_es.delay"
                ) as mock_webhook,
            ):
                ScheduledAlertHit.objects.all().delete()
                SCOTUSDocumentFactory(
                    docket_entry=self._make_scotus_entry(),
                    description="Petition for a writ of certiorari",
                )
                self.assertEqual(mock_webhook.called, enabled)
                self.assertEqual(len(self._hits(alert)), 1)

    def test_metadata_change_waits_for_the_new_parties(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """When a merge changes both the metadata (capital_case) and the
        parties, the docket is percolated once, after its new parties are
        indexed, not before with the old ones. Otherwise an alert excluding
        an incoming party could match the old parties.
        """
        report_data = ScotusDocketDataFactory(
            capital_case=False,
            docket_entries=[],
            questions_presented=None,
            parties=[
                SCOTUSPartyDataFactory(
                    name="Encino Motorcars, LLC", type="Petitioner"
                )
            ],
        )
        merge_scotus_docket(report_data, download_file=False)

        capital_alert = self._make_alert(
            "q=capital_case:true&type=d", SEARCH_TYPES.DOCKETS
        )
        excluding_alert = self._make_alert(
            'q=capital_case:true AND NOT party:"Acme Corp"&type=d',
            SEARCH_TYPES.DOCKETS,
        )
        report_data["capital_case"] = True
        report_data["parties"].append(
            SCOTUSPartyDataFactory(name="Acme Corp", type="Respondent")
        )
        with self._count_percolations() as mock_percolate:
            merge_scotus_docket(report_data, download_file=False)

        self.assertEqual(mock_percolate.call_count, 1)
        self.assertEqual(len(self._hits(capital_alert)), 1)
        self.assertEqual(self._hits(excluding_alert), [])

    def test_metadata_change_without_parties_is_percolated(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """A merge that changes the metadata but has no parties still
        percolates the docket, through the metadata update.
        """
        report_data = ScotusDocketDataFactory(
            capital_case=False,
            docket_entries=[],
            questions_presented=None,
            parties=[],
        )
        merge_scotus_docket(report_data, download_file=False)

        capital_alert = self._make_alert(
            "q=capital_case:true&type=d", SEARCH_TYPES.DOCKETS
        )
        report_data["capital_case"] = True
        with self._count_percolations() as mock_percolate:
            merge_scotus_docket(report_data, download_file=False)

        self.assertEqual(mock_percolate.call_count, 1)
        self.assertEqual(len(self._hits(capital_alert)), 1)

    @override_settings(PERCOLATOR_SCOTUS_SEARCH_ALERTS_ENABLED=False)
    def test_scotus_percolation_follows_its_own_setting(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """Without PERCOLATOR_SCOTUS_SEARCH_ALERTS_ENABLED, SCOTUS content
        isn't percolated.
        """
        alert = self._make_alert('q="writ of certiorari"&type=r')
        with mock.patch(
            "cl.alerts.tasks.prepare_percolator_content",
            wraps=prepare_percolator_content,
        ) as mock_percolate:
            SCOTUSDocumentFactory(
                docket_entry=self._make_scotus_entry(),
                description="Petition for a writ of certiorari",
            )
        self.assertEqual(mock_percolate.call_count, 0)
        self.assertEqual(self._hits(alert), [])

    @override_settings(PERCOLATOR_RECAP_SEARCH_ALERTS_ENABLED=True)
    def test_scotus_and_recap_documents_with_the_same_pk(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """A SCOTUS document whose pk equals an already-alerted RECAP
        document's pk still triggers its own hit.
        """
        alert = self._make_alert('q="writ of certiorari"&type=r')
        # A pk no factory reaches: the ES index is shared by the whole class,
        # so a lower pk could match a SCOTUS document another test indexed.
        shared_pk = 9_000_000
        RECAPDocumentFactory(
            id=shared_pk,
            docket_entry=DocketEntryFactory(
                docket=DocketFactory(
                    court=CourtFactory(id="ca1", jurisdiction="F"),
                    source=Docket.RECAP,
                )
            ),
            description="Petition for a writ of certiorari",
        )
        self.assertEqual(len(self._hits(alert)), 1)

        SCOTUSDocumentFactory(
            id=shared_pk,
            docket_entry=self._make_scotus_entry(),
            description="Petition for a writ of certiorari",
        )
        self.assertEqual(
            {hit.content_type.model for hit in self._hits(alert)},
            {"recapdocument", "scotusdocument"},
        )

    def test_alerts_indexed_and_removed_with_only_scotus_enabled(
        self, mock_prefix: mock.MagicMock
    ) -> None:
        """RECAP and docket-only alerts are indexed into the RECAP
        percolator when only SCOTUS percolation is on, and removed from it
        when deleted.
        """
        for alert_type in (SEARCH_TYPES.RECAP, SEARCH_TYPES.DOCKETS):
            with self.subTest(alert_type=alert_type):
                alert = self._make_alert(
                    'q="writ of certiorari"&type=r', alert_type
                )
                self.assertTrue(RECAPPercolator.exists(id=alert.pk))
                alert_id = alert.pk
                alert.delete()
                self.assertFalse(RECAPPercolator.exists(id=alert_id))
