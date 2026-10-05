from datetime import timedelta

from django.contrib.auth.models import User
from django.utils.timezone import now

from cl.favorites.factories import NoteFactory, PrayerFactory
from cl.favorites.models import Note, Prayer
from cl.favorites.utils import get_noted_object, get_notes_for
from cl.recap.management.commands.clean_duplicate_appellate_email_entries import (
    clean_duplicate_appellate_email_entries,
)
from cl.recap.models import EmailProcessingQueue, EmailSource
from cl.search.factories import (
    CourtFactory,
    DocketEntryFactory,
    DocketFactory,
    RECAPDocumentFactory,
)
from cl.search.models import DocketEntry, RECAPDocument
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory


class CleanDuplicateAppellateEmailEntriesTest(TestCase):
    """Tests for clean_duplicate_appellate_email_entries()."""

    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="ca8", jurisdiction="F")
        cls.uploader = User.objects.get(username="recap-email")

    def make_duplicate_pair(
        self,
        pacer_doc_id="002189877401",
        first_has_pdf=True,
        second_has_pdf=False,
        first_ocr_status=None,
        second_ocr_status=None,
        first_date_modified=None,
        second_date_modified=None,
        docket=None,
    ) -> tuple[DocketEntry, RECAPDocument, DocketEntry, RECAPDocument]:
        """Build two DocketEntry/RECAPDocument pairs sharing a
        pacer_doc_id, and an EmailProcessingQueue marking the docket as a
        candidate.

        :return: (entry_a, doc_a, entry_b, doc_b).
        """
        docket = docket or DocketFactory(court=self.court)
        entry_a = DocketEntryFactory(docket=docket)
        doc_a = RECAPDocumentFactory(
            docket_entry=entry_a,
            pacer_doc_id=pacer_doc_id,
            document_type=RECAPDocument.PACER_DOCUMENT,
            filepath_local=("recap/test.pdf" if first_has_pdf else ""),
            ocr_status=first_ocr_status,
        )
        entry_b = DocketEntryFactory(docket=docket)
        doc_b = RECAPDocumentFactory(
            docket_entry=entry_b,
            pacer_doc_id=pacer_doc_id,
            document_type=RECAPDocument.PACER_DOCUMENT,
            filepath_local=("recap/test2.pdf" if second_has_pdf else ""),
            ocr_status=second_ocr_status,
        )
        if first_date_modified:
            RECAPDocument.objects.filter(pk=doc_a.pk).update(
                date_modified=first_date_modified
            )
        if second_date_modified:
            RECAPDocument.objects.filter(pk=doc_b.pk).update(
                date_modified=second_date_modified
            )
        EmailProcessingQueue.objects.create(
            court=docket.court,
            uploader=self.uploader,
            message_id=f"msg-{pacer_doc_id}",
            source=EmailSource.PACER,
        ).recap_documents.add(doc_a)
        return entry_a, doc_a, entry_b, doc_b

    def test_keeps_the_copy_with_a_pdf(self):
        """Exactly one copy has a PDF - it survives, the other's
        DocketEntry is deleted, and document_number/entry_number are
        recomputed from pacer_doc_id."""
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair(
            pacer_doc_id="002189877401",
            first_has_pdf=True,
            second_has_pdf=False,
        )

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        self.assertTrue(DocketEntry.objects.filter(pk=entry_a.pk).exists())
        self.assertFalse(DocketEntry.objects.filter(pk=entry_b.pk).exists())
        doc_a.refresh_from_db()
        entry_a.refresh_from_db()
        self.assertEqual(doc_a.document_number, "2089877401")
        self.assertEqual(entry_a.entry_number, 2089877401)

    def test_dry_run_makes_no_changes(self):
        """clean=False only logs the plan"""
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair()

        clean_duplicate_appellate_email_entries([self.court.pk], clean=False)

        self.assertTrue(DocketEntry.objects.filter(pk=entry_b.pk).exists())
        doc_a.refresh_from_db()
        self.assertNotEqual(doc_a.document_number, "2089877401")

    def test_three_way_duplicate_group(self):
        """A group with 3 copies (not just 2) sharing a pacer_doc_id is
        still resolved down to a single keeper."""
        docket = DocketFactory(court=self.court)
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair(
            pacer_doc_id="002189877402",
            first_has_pdf=True,
            second_has_pdf=False,
            docket=docket,
        )
        entry_c = DocketEntryFactory(docket=docket)
        doc_c = RECAPDocumentFactory(
            docket_entry=entry_c,
            pacer_doc_id="002189877402",
            document_type=RECAPDocument.PACER_DOCUMENT,
            filepath_local="",
        )

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        self.assertTrue(DocketEntry.objects.filter(pk=entry_a.pk).exists())
        self.assertFalse(DocketEntry.objects.filter(pk=entry_b.pk).exists())
        self.assertFalse(DocketEntry.objects.filter(pk=entry_c.pk).exists())

    def test_tie_break_zero_pdfs_prefers_most_recent_with_ocr_status(self):
        """Neither copy has a PDF - the tie-break picks the most
        recently modified copy among those with a non-null ocr_status."""
        older = now() - timedelta(days=5)
        newer = now() - timedelta(days=1)
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair(
            pacer_doc_id="002189877403",
            first_has_pdf=False,
            second_has_pdf=False,
            first_ocr_status=None,
            second_ocr_status=RECAPDocument.OCR_COMPLETE,
            first_date_modified=newer,
            second_date_modified=older,
        )

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        # doc_b has an ocr_status set (even though it's older), so it
        # wins over doc_a despite doc_a being more recently modified.
        self.assertFalse(DocketEntry.objects.filter(pk=entry_a.pk).exists())
        self.assertTrue(DocketEntry.objects.filter(pk=entry_b.pk).exists())

    def test_tie_break_all_null_ocr_status_falls_back_to_most_recent(self):
        """Neither copy has a PDF or an ocr_status - falls back to the
        most recently modified copy overall."""
        older = now() - timedelta(days=5)
        newer = now() - timedelta(days=1)
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair(
            pacer_doc_id="002189877404",
            first_has_pdf=False,
            second_has_pdf=False,
            first_date_modified=older,
            second_date_modified=newer,
        )

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        self.assertFalse(DocketEntry.objects.filter(pk=entry_a.pk).exists())
        self.assertTrue(DocketEntry.objects.filter(pk=entry_b.pk).exists())

    def test_tie_break_two_pdfs_uses_same_recency_rule(self):
        """Both copies have a PDF, so the same recency/ocr_status
        tie-break applies."""
        older = now() - timedelta(days=5)
        newer = now() - timedelta(days=1)
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair(
            pacer_doc_id="002189877405",
            first_has_pdf=True,
            second_has_pdf=True,
            first_date_modified=older,
            second_date_modified=newer,
        )

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        self.assertFalse(DocketEntry.objects.filter(pk=entry_a.pk).exists())
        self.assertTrue(DocketEntry.objects.filter(pk=entry_b.pk).exists())

    def test_loser_with_unrelated_extra_document_skips_the_group(self):
        """A losing DocketEntry that also holds a document outside this
        duplicate group (e.g. an attachment) is left untouched."""
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair(
            pacer_doc_id="002189877406",
            first_has_pdf=True,
            second_has_pdf=False,
        )
        RECAPDocumentFactory(
            docket_entry=entry_b,
            document_type=RECAPDocument.ATTACHMENT,
            attachment_number=1,
            pacer_doc_id="999999999",
        )

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        self.assertTrue(DocketEntry.objects.filter(pk=entry_b.pk).exists())

    def test_loser_note_is_repointed_to_keeper(self):
        """A Note on the losing copy is moved to the keeper, not
        destroyed."""
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair(
            pacer_doc_id="002189877407",
            first_has_pdf=True,
            second_has_pdf=False,
        )
        user = UserFactory()
        note = NoteFactory.for_object(doc_b, user=user)

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        note.refresh_from_db()
        self.assertEqual(get_noted_pk(note), doc_a.pk)

    def test_loser_prayer_is_repointed_to_keeper(self):
        """A Prayer on the losing copy is moved to the keeper, not
        destroyed."""
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair(
            pacer_doc_id="002189877408",
            first_has_pdf=True,
            second_has_pdf=False,
        )
        user = UserFactory()
        prayer = PrayerFactory(user=user, recap_document=doc_b)

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        prayer.refresh_from_db()
        self.assertEqual(prayer.recap_document_id, doc_a.pk)

    def test_same_user_note_on_both_copies_deletes_the_losers_copy(self):
        """If the same user already has a Note on the keeper, the
        loser's Note isn't moved there (would collide) - it's left for
        delete_orphaned_notes to clean up once the loser is deleted."""
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair(
            pacer_doc_id="002189877409",
            first_has_pdf=True,
            second_has_pdf=False,
        )
        user = UserFactory()
        keeper_note = NoteFactory.for_object(doc_a, user=user)
        loser_note = NoteFactory.for_object(doc_b, user=user)

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        self.assertTrue(Note.objects.filter(pk=keeper_note.pk).exists())
        self.assertFalse(Note.objects.filter(pk=loser_note.pk).exists())
        self.assertEqual(get_notes_for(doc_a).count(), 1)

    def test_same_user_prayer_on_both_copies_deletes_the_losers_copy(self):
        """Same collision case as Notes."""
        entry_a, doc_a, entry_b, doc_b = self.make_duplicate_pair(
            pacer_doc_id="002189877410",
            first_has_pdf=True,
            second_has_pdf=False,
        )
        user = UserFactory()
        keeper_prayer = PrayerFactory(user=user, recap_document=doc_a)
        loser_prayer = PrayerFactory(user=user, recap_document=doc_b)

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        self.assertTrue(Prayer.objects.filter(pk=keeper_prayer.pk).exists())
        self.assertFalse(Prayer.objects.filter(pk=loser_prayer.pk).exists())

    def test_docket_without_duplicates_is_a_no_op(self):
        """A candidate docket with no actual pacer_doc_id collisions
        isn't touched."""
        docket = DocketFactory(court=self.court)
        entry = DocketEntryFactory(docket=docket)
        doc = RECAPDocumentFactory(
            docket_entry=entry,
            pacer_doc_id="002189877412",
            document_type=RECAPDocument.PACER_DOCUMENT,
        )
        EmailProcessingQueue.objects.create(
            court=docket.court,
            uploader=self.uploader,
            message_id="msg-no-dup",
            source=EmailSource.PACER,
        ).recap_documents.add(doc)

        clean_duplicate_appellate_email_entries([self.court.pk], clean=True)

        self.assertTrue(DocketEntry.objects.filter(pk=entry.pk).exists())


def get_noted_pk(note: Note) -> int | None:
    """Test helper: the pk of the RECAPDocument a Note points to,
    dual-read aware."""
    obj = get_noted_object(note)
    return obj.pk if obj is not None else None
