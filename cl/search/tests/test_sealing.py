"""Tests for sealing OpinionClusters and RECAPDocuments.

Covers the OpinionCluster seal admin views/actions (cl.search.admin,
cl.search.utils.delete_cluster_files) and the RECAPDocument seal_documents
admin action, including its propagation into Elasticsearch.
"""

import datetime
from http import HTTPStatus
from unittest import mock

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory
from django.urls import reverse

from cl.favorites.factories import NoteFactory, UserTagFactory
from cl.search.admin import OpinionClusterAdmin, RECAPDocumentAdmin
from cl.search.documents import ES_CHILD_ID, DocketDocument
from cl.search.factories import (
    BankruptcyInformationFactory,
    CaseTransferFactory,
    CourtFactory,
    DocketEntryFactory,
    DocketFactory,
    OpinionClusterFactory,
    OpinionClusterWithParentsFactory,
    OpinionFactory,
    RECAPDocumentFactory,
    SCOTUSDocketEntryFactory,
    TrialCourtDataFactory,
)
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    ClusterRedirection,
    Docket,
    OpinionCluster,
    RECAPDocument,
    ScotusDocketMetadata,
)
from cl.search.state.florida.factories import FloridaDocketEntryFactory
from cl.search.state.texas.factories import TexasDocketEntryFactory
from cl.tests.cases import (
    CountESTasksTestCase,
    ESIndexTestCase,
    TestCase,
    TransactionTestCase,
)
from cl.users.factories import UserFactory


class OpinionClusterSealClustersActionTest(TestCase):
    """Full-coverage tests for the bulk "Seal selected opinion clusters"
    admin action: sealing with and without a docket removal, and blocking
    on related user data."""

    @classmethod
    def setUpTestData(cls):
        cls.factory = RequestFactory()
        cls.superuser = UserFactory(is_staff=True, is_superuser=True)
        cls.court_1 = CourtFactory(id="nyappdiv")
        cls.court_2 = CourtFactory(id="ca6")

        cls.cluster_1 = OpinionClusterWithParentsFactory(
            docket=DocketFactory(
                court=cls.court_1,
                case_name="Lorem v. Ipsum",
                case_name_full="Lorem v. Ipsum",
            ),
            case_name="Lorem v. Ipsum",
            date_filed=datetime.date.today(),
            judges="Doe",
        )

        cls.docket_1 = DocketFactory(
            court=cls.court_2,
            source=Docket.HARVARD_AND_RECAP,
        )
        cls.de_1 = DocketEntryFactory(
            docket=cls.docket_1,
            entry_number=23,
            date_filed=datetime.date(2015, 8, 4),
            description="Main Document",
        )
        cls.cluster_2 = OpinionClusterFactory.create(
            precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            docket=cls.docket_1,
            date_filed=datetime.date(2024, 8, 23),
            case_name="Foo v. Bar",
            source="U",
        )

        cls.user_1 = UserFactory()

        cls.cluster_3 = OpinionClusterWithParentsFactory(
            docket=DocketFactory(
                court=cls.court_1,
                case_name="Lorem v. Ipsum",
                case_name_full="Lorem v. Ipsum",
            ),
            case_name="Lorem v. Ipsum",
            date_filed=datetime.date.today(),
            judges="Doe",
        )

        # The docket from the associated clusted has an user tag
        cls.tag_1_user_1 = UserTagFactory(user=cls.user_1, name="tag_1_user_1")
        cls.tag_1_user_1.dockets.add(cls.cluster_3.docket.pk)

        # The cluster has an user note
        cls.note_cluster_3_user_1 = NoteFactory(
            user=cls.user_1,
            cluster_id=cls.cluster_3,
            notes="Note Test",
        )

    def setUp(self):
        self.site = admin.site

    def test_seal_cluster_action(self):
        """Test seal_clusters action in OpinionCluster admin page"""
        # Test 1: Can we seal cluster without any blockages and create redirection?

        cluster_pk = self.cluster_1.pk
        docket_pk = self.cluster_1.docket.pk

        # Call seal_clusters action.
        clusters_admin = OpinionClusterAdmin(OpinionCluster, self.site)
        clusters_admin.message_user = mock.Mock()
        url = reverse("admin:search_opinioncluster_changelist")
        request = self.factory.post(url)
        # seal_clusters checks the delete permission, so a hand-built request
        # needs a user the way a real admin request would have one.
        request.user = self.superuser

        queryset = OpinionCluster.objects.filter(pk=cluster_pk)
        clusters_admin.seal_clusters(request, queryset)

        # Check sealed correctly
        clusters_admin.message_user.assert_called_once_with(
            request,
            "Sealed 1 cluster(s).",
            messages.SUCCESS,
        )
        # Check docket has been removed
        docket = Docket.objects.filter(pk=docket_pk)
        self.assertEqual(
            docket.count(),
            0,
            msg="Docket has not been removed after sealing the cluster.",
        )
        # Check cluster redirection has been created
        redirection = ClusterRedirection.objects.filter(
            reason=ClusterRedirection.SEALED,
            deleted_cluster_id=cluster_pk,
            cluster=None,
        )
        self.assertEqual(
            redirection.count(),
            1,
            msg="Got incorrect number of ClusterRedirection results",
        )
        clusters_admin.message_user.reset_mock()

        # Test 2: Can we seal a cluster but not removing the docket and create redirection?
        cluster2_pk = self.cluster_2.pk
        docket2_pk = self.cluster_2.docket.pk

        queryset = OpinionCluster.objects.filter(pk=cluster2_pk)
        clusters_admin.seal_clusters(request, queryset)

        # Check sealed correctly
        clusters_admin.message_user.assert_called_once_with(
            request,
            "Sealed 1 cluster(s).",
            messages.SUCCESS,
        )

        # Check that docket has not been removed
        docket = Docket.objects.filter(pk=docket2_pk)
        self.assertEqual(
            docket.count(),
            1,
            msg="Docket shouldn't have been removed after sealing the cluster.",
        )

        # Check that the cluster redirection was still created.
        redirection = ClusterRedirection.objects.filter(
            reason=ClusterRedirection.SEALED,
            deleted_cluster_id=cluster2_pk,
            cluster=None,
        )
        self.assertEqual(
            redirection.count(),
            1,
            msg="Got more or less ClusterRedirection results",
        )
        clusters_admin.message_user.reset_mock()

        # Test 3: Can we block seal if something is related to cluster? No, user related information exists
        cluster3_pk = self.cluster_3.pk

        queryset = OpinionCluster.objects.filter(pk=cluster3_pk)
        clusters_admin.seal_clusters(request, queryset)

        # Check cannot be sealed
        clusters_admin.message_user.assert_called_once_with(
            request,
            f'ERROR: Problem sealing cluster id: {cluster3_pk} - <a href="/admin/search/opinioncluster/blocking-confirmation/{cluster3_pk}/" target="_blank">View Dependencies</a>',
            messages.WARNING,
        )

        # Check blocking objects:
        blocking_relations = clusters_admin.get_blocking_relations(
            self.cluster_3
        )

        user_tag_qs = blocking_relations.get("favorites.UserTag")
        self.assertTrue(user_tag_qs.exists())
        self.assertIn(self.tag_1_user_1, user_tag_qs)

        note_qs = blocking_relations.get("favorites.Note")
        self.assertTrue(note_qs.exists())
        self.assertIn(self.note_cluster_3_user_1, note_qs)


class OpinionClusterAdminSealViewTest(TestCase):
    """Tests for the single-cluster seal confirmation view."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory(is_staff=True, is_superuser=True)
        cls.court = CourtFactory(id="ca9")

        cls.cluster_no_blockers = OpinionClusterWithParentsFactory(
            docket=DocketFactory(
                court=cls.court,
                case_name="No Blockers v. Test",
            ),
            case_name="No Blockers v. Test",
            date_filed=datetime.date.today(),
        )

        # A staff user with no model permissions at all, to check that the
        # seal view is gated on more than the admin's is_staff check.
        cls.staff_user = UserFactory(is_staff=True, is_superuser=False)

        cls.cluster_with_blockers = OpinionClusterWithParentsFactory(
            docket=DocketFactory(
                court=cls.court,
                case_name="Has Blockers v. Test",
            ),
            case_name="Has Blockers v. Test",
            date_filed=datetime.date.today(),
        )
        # Attach a UserTag to make this cluster unsealable via the view
        user = UserFactory()
        tag = UserTagFactory(user=user, name="blocker_tag")
        tag.dockets.add(cls.cluster_with_blockers.docket.pk)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.superuser)

    def test_seal_cluster_view_get_no_blockers(self):
        """GET with no blocking relations renders the confirmation page."""
        url = reverse(
            "admin:opinioncluster_seal_confirmation",
            args=[self.cluster_no_blockers.pk],
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("cluster", response.context)
        self.assertEqual(response.context["cluster"], self.cluster_no_blockers)

    def test_seal_cluster_view_get_with_cluster_blockers_redirects(self):
        """GET with cluster-level blockers redirects to the blocking view."""
        url = reverse(
            "admin:opinioncluster_seal_confirmation",
            args=[self.cluster_with_blockers.pk],
        )
        response = self.client.get(url)
        self.assertRedirects(
            response,
            reverse(
                "admin:opinioncluster_blocking_confirmation",
                args=[self.cluster_with_blockers.pk],
            ),
        )

    def test_seal_cluster_view_post_seals_cluster(self):
        """POST seals the cluster and creates a ClusterRedirection."""
        cluster = OpinionClusterWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
                case_name="Seal Me v. Test",
            ),
            case_name="Seal Me v. Test",
            date_filed=datetime.date.today(),
        )
        pk = cluster.pk
        url = reverse("admin:opinioncluster_seal_confirmation", args=[pk])
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse("admin:search_opinioncluster_changelist"),
        )
        self.assertFalse(
            OpinionCluster.objects.filter(pk=pk).exists(),
            "Cluster should have been deleted after sealing.",
        )
        self.assertTrue(
            ClusterRedirection.objects.filter(
                deleted_cluster_id=pk,
                reason=ClusterRedirection.SEALED,
            ).exists(),
            "A ClusterRedirection record should have been created.",
        )

    def test_seal_cluster_view_requires_delete_permission(self):
        """A staff user without delete permission can't seal a cluster."""
        self.client.force_login(self.staff_user)
        pk = self.cluster_no_blockers.pk
        url = reverse("admin:opinioncluster_seal_confirmation", args=[pk])
        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
        self.assertTrue(
            OpinionCluster.objects.filter(pk=pk).exists(),
            "Cluster should not have been deleted.",
        )


class OpinionClusterSealDocketBlockersTest(TestCase):
    """Sealing a cluster must leave its docket alone when something still
    points at the docket."""

    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="ca8")

    def make_cluster(self) -> OpinionCluster:
        """Build a cluster on a docket of its own.

        :return: The new OpinionCluster
        """
        return OpinionClusterWithParentsFactory(
            docket=DocketFactory(
                court=self.court,
                case_name="Blocker v. Test",
            ),
            case_name="Blocker v. Test",
            date_filed=datetime.date.today(),
        )

    def test_docket_relations_block_docket_deletion(self):
        """Each model pointing at Docket keeps the docket out of the seal."""
        blocker_builders = {
            "search.BankruptcyInformation": lambda docket: BankruptcyInformationFactory(
                docket=docket
            ),
            "search.SCOTUSDocketEntry": lambda docket: SCOTUSDocketEntryFactory(
                docket=docket
            ),
            "search.ScotusDocketMetadata": lambda docket: ScotusDocketMetadata.objects.create(
                docket=docket
            ),
            "search.TexasDocketEntry": lambda docket: TexasDocketEntryFactory(
                docket=docket
            ),
            "search.FloridaDocketEntry": lambda docket: FloridaDocketEntryFactory(
                docket=docket
            ),
            "search.TrialCourtData": lambda docket: TrialCourtDataFactory(
                docket=docket
            ),
            "search.CaseTransfer": lambda docket: CaseTransferFactory(
                origin_docket=docket
            ),
        }
        clusters_admin = OpinionClusterAdmin(OpinionCluster, admin.site)
        for key, build_blocker in blocker_builders.items():
            with self.subTest(blocker=key):
                cluster = self.make_cluster()
                docket = cluster.docket
                build_blocker(docket)

                blockers = clusters_admin.check_blocking_relations(cluster)
                self.assertTrue(
                    blockers[key], f"{key} should block docket deletion."
                )
                cluster_blocked, docket_blocked = (
                    clusters_admin.get_deletion_blockers(cluster)
                )
                self.assertFalse(
                    cluster_blocked, f"{key} should not block the cluster."
                )
                self.assertTrue(
                    docket_blocked, f"{key} should block the docket."
                )

                clusters_admin.seal_cluster(
                    cluster, delete_docket=not docket_blocked
                )
                self.assertFalse(
                    OpinionCluster.objects.filter(pk=cluster.pk).exists(),
                    "Cluster should have been deleted.",
                )
                self.assertTrue(
                    Docket.objects.filter(pk=docket.pk).exists(),
                    f"Docket should have survived a {key} blocker.",
                )


class OpinionClusterSealActionPermissionTest(TestCase):
    """The bulk seal action must require the delete permission."""

    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="ca7")
        cls.staff_user = UserFactory(is_staff=True, is_superuser=False)
        cls.cluster = OpinionClusterWithParentsFactory(
            docket=DocketFactory(court=cls.court, case_name="Bulk v. Test"),
            case_name="Bulk v. Test",
            date_filed=datetime.date.today(),
        )

    def test_seal_clusters_requires_delete_permission(self):
        """A staff user without delete permission can't run the action."""
        clusters_admin = OpinionClusterAdmin(OpinionCluster, admin.site)
        request = RequestFactory().post(
            reverse("admin:search_opinioncluster_changelist")
        )
        request.user = self.staff_user
        queryset = OpinionCluster.objects.filter(pk=self.cluster.pk)

        with self.assertRaises(PermissionDenied):
            clusters_admin.seal_clusters(request, queryset)

        self.assertTrue(
            OpinionCluster.objects.filter(pk=self.cluster.pk).exists(),
            "Cluster should not have been deleted.",
        )


class OpinionClusterSealFileCleanupTest(TestCase):
    """Sealing a cluster must scrub its files from storage and the CDN."""

    @classmethod
    def setUpTestData(cls):
        cls.court = CourtFactory(id="ca10")

    @mock.patch("cl.search.utils.invalidate_cloudfront")
    def test_seal_cluster_deletes_files_and_invalidates_cdn(
        self, mock_invalidate_cloudfront
    ):
        """Sealing removes every FileField the cluster, its sub-opinions,
        and its docket point at, and invalidates the CDN cache for each."""
        docket = DocketFactory(
            court=self.court,
            case_name="Seal Files v. Test",
            filepath_local="recap/docket.xml",
        )
        cluster = OpinionClusterFactory(
            docket=docket,
            case_name="Seal Files v. Test",
            date_filed=datetime.date.today(),
            filepath_json_harvard="harvard/cluster.json",
            filepath_pdf_harvard="harvard/cluster.pdf",
            filepath_xml_scan="scan/cluster.xml",
            filepath_pdf_scan="scan/cluster.pdf",
        )
        OpinionFactory(cluster=cluster, local_path="opinions/opinion.pdf")

        clusters_admin = OpinionClusterAdmin(OpinionCluster, admin.site)
        clusters_admin.seal_cluster(cluster, delete_docket=True)

        self.assertFalse(
            OpinionCluster.objects.filter(pk=cluster.pk).exists(),
            "Cluster should have been deleted.",
        )
        self.assertFalse(
            Docket.objects.filter(pk=docket.pk).exists(),
            "Docket should have been deleted.",
        )

        mock_invalidate_cloudfront.assert_called_once()
        (invalidated_paths,), _ = mock_invalidate_cloudfront.call_args
        self.assertCountEqual(
            invalidated_paths,
            [
                "/opinions/opinion.pdf",
                "/harvard/cluster.json",
                "/harvard/cluster.pdf",
                "/scan/cluster.xml",
                "/scan/cluster.pdf",
                "/recap/docket.xml",
            ],
        )

    @mock.patch("cl.search.utils.invalidate_cloudfront")
    def test_seal_cluster_with_no_files_invalidates_nothing(
        self, mock_invalidate_cloudfront
    ):
        """Sealing a cluster with no files attached is a no-op for storage
        and the CDN, but still succeeds."""
        cluster = OpinionClusterWithParentsFactory(
            docket=DocketFactory(
                court=self.court, case_name="No Files v. Test"
            ),
            case_name="No Files v. Test",
            date_filed=datetime.date.today(),
        )
        clusters_admin = OpinionClusterAdmin(OpinionCluster, admin.site)
        clusters_admin.seal_cluster(cluster, delete_docket=True)
        mock_invalidate_cloudfront.assert_not_called()

    @mock.patch("cl.search.utils.invalidate_cloudfront")
    def test_seal_cluster_leaves_docket_file_when_docket_kept(
        self, mock_invalidate_cloudfront
    ):
        """When the docket survives sealing, its file must be left alone."""
        docket = DocketFactory(
            court=self.court,
            case_name="Keep Docket v. Test",
            filepath_local="recap/docket.xml",
        )
        cluster = OpinionClusterFactory(
            docket=docket,
            case_name="Keep Docket v. Test",
            date_filed=datetime.date.today(),
        )
        clusters_admin = OpinionClusterAdmin(OpinionCluster, admin.site)
        clusters_admin.seal_cluster(cluster, delete_docket=False)

        docket.refresh_from_db()
        self.assertEqual(docket.filepath_local, "recap/docket.xml")
        mock_invalidate_cloudfront.assert_not_called()


class RECAPDocumentSealActionESTest(
    CountESTasksTestCase, ESIndexTestCase, TransactionTestCase
):
    """Sealing a RECAPDocument through the admin action must scrub its
    fields and propagate the change into Elasticsearch."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rebuild_index("people_db.Person")
        cls.rebuild_index("search.Docket")

    def setUp(self):
        self.court = CourtFactory(id="canb", jurisdiction="FB")
        self.factory = RequestFactory()
        self.site = admin.site
        super().setUp()

    @mock.patch("cl.search.utils.time.sleep")
    @mock.patch("cl.search.utils.delete_from_ia")
    @mock.patch("cl.search.utils.invalidate_cloudfront")
    def test_seal_documents_action(
        self, mock_invalidate_cloudfront, mock_delete_from_ia, mock_sleep
    ):
        """Confirm that seal_documents admin action updates related RDs in ES"""

        docket = DocketFactory(
            court=self.court,
            pacer_case_id="asdf",
            docket_number="12-cv-02354",
            case_name="Vargas v. Wilkins",
            source=Docket.RECAP,
        )
        de_1 = DocketEntryFactory(
            docket=docket,
            date_filed=datetime.date(2015, 8, 19),
            description="MOTION for Leave to File Amicus Curiae Lorem",
            entry_number=None,
        )
        rd_1 = RECAPDocumentFactory(
            docket_entry=de_1,
            document_number="1",
            is_available=True,
            page_count=5,
            filepath_local="test.pdf",
            plain_text="Lorem ipsum dolor text.",
        )
        rd_2 = RECAPDocumentFactory(
            docket_entry=de_1,
            document_number="2",
            is_available=True,
            page_count=10,
            filepath_local="test.pdf",
            plain_text="Lorem ipsum dolor text 2.",
        )

        # Confirm initial indexing:
        rd_1_doc = DocketDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertEqual(rd_1_doc.is_available, True)
        self.assertEqual(rd_1_doc.plain_text, rd_1.plain_text)
        self.assertEqual(rd_1_doc.page_count, rd_1.page_count)
        self.assertEqual(rd_1_doc.filepath_local, rd_1.filepath_local)

        rd_2_doc = DocketDocument.get(id=ES_CHILD_ID(rd_2.pk).RECAP)
        self.assertEqual(rd_2_doc.is_available, True)
        self.assertEqual(rd_2_doc.plain_text, rd_2.plain_text)
        self.assertEqual(rd_2_doc.page_count, rd_2.page_count)
        self.assertEqual(rd_2_doc.filepath_local, rd_2.filepath_local)

        # Call seal_documents action.
        recap_admin = RECAPDocumentAdmin(RECAPDocument, self.site)
        recap_admin.message_user = mock.Mock()
        url = reverse("admin:search_recapdocument_changelist")
        request = self.factory.post(url)

        queryset = RECAPDocument.objects.filter(pk__in=[rd_1.pk, rd_2.pk])
        recap_admin.seal_documents(request, queryset)

        recap_admin.message_user.assert_called_once_with(
            request,
            "Successfully sealed and removed 2 document(s).",
            messages.SUCCESS,
        )
        # The throttle sleep only runs between documents, so sealing two
        # documents should trigger it exactly once.
        mock_sleep.assert_called_once_with(1)

        # Confirm DB update:
        rd_1.refresh_from_db()
        self.assertEqual(rd_1.is_available, False)
        self.assertEqual(rd_1.is_sealed, True)
        self.assertEqual(rd_1.filepath_local, "")
        self.assertIsNone(rd_1.page_count)
        self.assertEqual(rd_1.sha1, "")
        self.assertEqual(rd_1.plain_text, "")

        rd_2.refresh_from_db()
        self.assertEqual(rd_2.is_available, False)
        self.assertEqual(rd_2.is_sealed, True)
        self.assertEqual(rd_2.filepath_local, "")
        self.assertIsNone(rd_2.page_count)
        self.assertEqual(rd_2.sha1, "")
        self.assertEqual(rd_2.plain_text, "")

        # Confirm ES indexing:
        rd_1_doc = DocketDocument.get(id=ES_CHILD_ID(rd_1.pk).RECAP)
        self.assertEqual(rd_1_doc.is_available, False)
        self.assertEqual(rd_1_doc.plain_text, "")
        self.assertEqual(rd_1_doc.page_count, None)
        self.assertEqual(rd_1_doc.filepath_local, None)

        rd_2_doc = DocketDocument.get(id=ES_CHILD_ID(rd_2.pk).RECAP)
        self.assertEqual(rd_2_doc.is_available, False)
        self.assertEqual(rd_2_doc.plain_text, "")
        self.assertEqual(rd_2_doc.page_count, None)
        self.assertEqual(rd_2_doc.filepath_local, None)

        # Clean up index.
        docket.delete()
