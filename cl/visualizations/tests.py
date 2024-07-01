"""
Unit tests for Visualizations
"""

from http import HTTPStatus
from typing import Any, Callable, Dict

from asgiref.sync import sync_to_async
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Permission, User
from django.core.handlers.asgi import ASGIRequest
from django.test import AsyncRequestFactory
from django.urls import reverse
from httplib2 import Response

from cl.search.models import OpinionCluster
from cl.tests.cases import APITestCase, TestCase
from cl.tests.utils import make_client
from cl.users.factories import (
    UserProfileWithParentsFactory,
    UserWithChildProfileFactory,
)
from cl.visualizations import views
from cl.visualizations.factories import VisualizationFactory
from cl.visualizations.forms import VizForm
from cl.visualizations.models import JSONVersion, SCOTUSMap
from cl.visualizations.network_utils import reverse_endpoints_if_needed


class TestVizUtils(TestCase):
    """Tests for Visualization app utils"""

    fixtures = ["scotus_map_data.json"]

    async def test_reverse_endpoints_does_not_reverse_good_inputs(
        self,
    ) -> None:
        """
        Test the utility function does not change the order of endpoints that
        are already in correct order
        """
        start = await OpinionCluster.objects.aget(
            case_name="Marsh v. Chambers"
        )
        end = await OpinionCluster.objects.aget(
            case_name="Town of Greece v. Galloway"
        )
        new_start, new_end = reverse_endpoints_if_needed(start, end)
        self.assertEqual(new_start, start)
        self.assertEqual(new_end, end)

    async def test_reverse_endpoints_reverses_backwards_inputs(self) -> None:
        """
        Test the utility function for properly ordering visualization
        endpoints.
        """
        real_end = await OpinionCluster.objects.aget(
            case_name="Town of Greece v. Galloway"
        )
        real_start = await OpinionCluster.objects.aget(
            case_name="Marsh v. Chambers"
        )
        reversed_start, reversed_end = reverse_endpoints_if_needed(
            real_end, real_start
        )
        self.assertEqual(real_start, reversed_start)
        self.assertEqual(real_end, reversed_end)


class TestVizModels(TestCase):
    """Tests for Visualization models"""

    fixtures = ["scotus_map_data.json"]

    async def test_SCOTUSMap_builds_nx_digraph(self) -> None:
        """Tests build_nx_digraph method to see how it works"""
        start = await OpinionCluster.objects.aget(
            case_name="Marsh v. Chambers"
        )
        end = await OpinionCluster.objects.aget(
            case_name="Town of Greece v. Galloway"
        )
        viz = await sync_to_async(VisualizationFactory.create)(
            cluster_start=start,
            cluster_end=end,
            title="Test SCOTUSMap",
            notes="Test Notes",
        )

        build_kwargs = {
            "parent_authority": end,
            "visited_nodes": {},
            "good_nodes": {},
            "max_hops": 3,
        }

        g = await viz.build_nx_digraph(**build_kwargs)
        self.assertTrue(len(g.edges()) > 0)

    def test_SCOTUSMap_deletes_cascade(self) -> None:
        """
        Make sure we delete JSONVersion instances when deleted SCOTUSMaps
        """
        viz = VisualizationFactory.create(
            title="Test SCOTUSMap",
            notes="Test Notes",
        )
        self.assertGreater(viz.json_versions.all().count(), 0)
        self.assertIsNotNone(viz.pk, None)
        viz.delete()
        self.assertIsNone(viz.pk, None)


class TestViews(TestCase):
    """Tests for Visualization views"""

    view = "new_visualization"

    fixtures = ["scotus_map_data.json"]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.regular_user = UserWithChildProfileFactory.create(
            first_name="Userio",
            username="regular_user",
            password=make_password("password"),
            profile__email_confirmed=True,
        )
        cls.viz = VisualizationFactory.create(
            user=cls.regular_user,
            notes="FREE KESHA",
            published=True,
            deleted=False,
        )

        cls.admin_user = UserWithChildProfileFactory.create(
            username="admin",
            password=make_password("password"),
        )
        cls.admin_user.is_superuser = True
        cls.admin_user.is_staff = True
        cls.admin_user.save()

    async def test_new_visualization_view_provides_form(self) -> None:
        """Test a GET to the Visualization view provides a VizForm"""
        self.assertTrue(
            await self.async_client.alogin(
                username=self.regular_user.username, password="password"
            )
        )
        response = await self.async_client.get(reverse(self.view))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], VizForm)

    async def test_new_visualization_view_creates_map_on_post(self) -> None:
        """Test a valid POST creates a new ScotusMap object"""
        count_before = await SCOTUSMap.objects.all().acount()

        self.assertTrue(
            await self.async_client.alogin(
                username="regular_user", password="password"
            )
        )
        data = {
            "cluster_start": 2674862,
            "cluster_end": 111014,
            "title": "Test Map Title",
            "notes": "Just some notes",
        }
        response = await self.async_client.post(reverse(self.view), data=data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(count_before + 1, await SCOTUSMap.objects.acount())

        # Should not raise DoesNotExist exception.
        await SCOTUSMap.objects.aget(title="Test Map Title")

    async def test_published_visualizations_show_in_gallery(self) -> None:
        """Test that a user can see published visualizations from others"""
        self.assertTrue(
            await self.async_client.alogin(
                username="regular_user", password="password"
            )
        )
        response = await self.async_client.get(reverse("viz_gallery"))
        html = response.content.decode()
        html = " ".join(html.split())
        self.assertIn("Shared by Userio", html)
        self.assertIn("FREE KESHA", html)

    async def test_cannot_view_anothers_private_visualization(self) -> None:
        """Test unpublished visualizations cannot be seen by others"""
        viz = await sync_to_async(VisualizationFactory.create)(
            user=self.regular_user,
            title="My Private Visualization",
            published=False,
            deleted=False,
        )

        self.assertFalse(viz.published, "Test SCOTUSMap should be unpublished")
        url = reverse(
            "view_visualization", kwargs={"pk": viz.pk, "slug": viz.slug}
        )

        # Created by regular user, so *can* see unpublished viz.
        self.assertTrue(
            await self.async_client.alogin(
                username="regular_user", password="password"
            )
        )
        response = await self.async_client.get(url)
        self.assertEqual(
            response.status_code,
            HTTPStatus.OK,
            msg=f"Didn't get {HTTPStatus.OK}, got {response.status_code}, with HTML:\n{response.content.decode()}",
        )
        self.assertIn("My Private Visualization", response.content.decode())

        # Not created by admin and we don't have special code to allow admins,
        # so don't show viz.
        self.assertTrue(
            await self.async_client.alogin(
                username="admin", password="password"
            )
        )
        response = await self.async_client.get(url)
        self.assertNotEqual(response.status_code, HTTPStatus.OK)
        self.assertNotIn("My Private Visualization", response.content.decode())

    async def test_view_counts_increment_by_one(self) -> None:
        """Test the view count for a Visualization increments on page view

        Ensure that the date_modified does not change.
        """
        viz = await sync_to_async(VisualizationFactory.create)(
            user=self.regular_user,
            published=True,
            deleted=False,
            view_count=10,
        )
        old_view_count = viz.view_count
        old_date_modified = viz.date_modified

        self.assertTrue(
            await self.async_client.alogin(
                username="regular_user", password="password"
            )
        )
        response = await self.async_client.get(viz.get_absolute_url())

        await viz.arefresh_from_db(fields=["view_count", "date_modified"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(old_view_count + 1, viz.view_count)

        self.assertEqual(
            old_date_modified,
            viz.date_modified,
            msg="date_modified changed when the page was loaded!",
        )


class TestVizAjaxCrud(TestCase):
    """
    Test the CRUD operations for Visualizations that the javascript client
    code relies on currently.
    """

    fixtures = ["scotus_map_data.json", "visualizations.json"]

    def setUp(self) -> None:
        self.live_viz = SCOTUSMap.objects.get(pk=1)
        self.private_viz = SCOTUSMap.objects.get(pk=2)
        self.deleted_viz = SCOTUSMap.objects.get(pk=3)
        self.factory = AsyncRequestFactory()

    def tearDown(self) -> None:
        SCOTUSMap.objects.all().delete()
        JSONVersion.objects.all().delete()

    async def _build_post(
        self,
        url: str,
        username: str = None,
        data: Dict[str, Any] = None,
    ) -> ASGIRequest:
        """Helper method to build authenticated AJAX POST
        Args:
            url: url pattern to request
            username: username for User to attach
            **data: dictionary of POST data

        Returns: HttpRequest configured as an AJAX POST
        """
        if data is None:
            data = {}
        post = self.factory.post(url, data=data)
        if username:
            post.user = await User.objects.aget(username=username)
        post.META["HTTP_X_REQUESTED_WITH"] = "XMLHttpRequest"
        return post

    async def post_ajax_view(
        self,
        view: Callable,
        pk: int,
        username: str = "admin",
    ) -> SCOTUSMap:
        """
        Generates a simple POST for the given view with the given
        private key as the POST data.

        Args:
            view: reference to Django View
            pk: private key of target SCOTUSMap
            username: username of User to POST as

        Returns: new reference to updated SCOTUSMap

        """
        post = await self._build_post(
            reverse(view), username=username, data={"pk": pk}
        )
        response = await view(post)
        self.assertEqual(response.status_code, 200)
        return await SCOTUSMap.objects.aget(pk=pk)

    async def test_deletion_via_ajax_view(self) -> None:
        """
        Test deletion of visualization via view only sets deleted flag and
        doesn't actually delete the object yet
        """
        self.assertFalse(self.live_viz.deleted)
        self.assertIsNone(self.live_viz.date_deleted)

        viz = await self.post_ajax_view(
            views.delete_visualization, self.live_viz.pk
        )

        self.assertTrue(viz.deleted)
        self.assertIsNotNone(viz.date_deleted)

    async def test_restore_via_ajax_view(self) -> None:
        """
        Tests restoration of deleted visualization from teh trash via a
        ajax POST
        """
        self.assertTrue(self.deleted_viz.deleted)
        self.assertIsNotNone(self.deleted_viz.date_deleted)

        viz = await self.post_ajax_view(
            views.restore_visualization, self.deleted_viz.pk
        )

        self.assertFalse(viz.deleted)
        self.assertIsNone(viz.date_deleted)

    async def test_privatizing_via_ajax_view(self) -> None:
        """
        Tests setting a public visualization to private via an AJAX POST
        """
        self.assertTrue(self.live_viz.published)
        self.assertIsNotNone(self.live_viz.date_published)

        viz = await self.post_ajax_view(
            views.privatize_visualization, self.live_viz.pk
        )

        self.assertFalse(viz.published)

    async def test_sharing_via_ajax_view(self) -> None:
        """
        Tests sharing a public visualization via an AJAX POST
        """
        self.assertFalse(self.private_viz.published)
        self.assertIsNone(self.private_viz.date_published)

        viz = await self.post_ajax_view(
            views.share_visualization, self.private_viz.pk
        )

        self.assertTrue(viz.published)
        self.assertIsNotNone(viz.date_published)


class APIVisualizationTestCase(APITestCase):
    """Check that visualizations are created properly through the API."""

    fixtures = ["api_scotus_map_data.json"]

    @classmethod
    def setUpTestData(cls) -> None:
        # Add the permissions to the user.
        cls.up = UserProfileWithParentsFactory.create(
            user__username="recap-user",
            user__password=make_password("password"),
        )
        cls.ps = Permission.objects.filter(codename="has_recap_api_access")
        cls.up.user.user_permissions.add(*cls.ps)

        cls.pandora = UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )

    def setUp(self) -> None:
        self.path = reverse("scotusmap-list", kwargs={"version": "v3"})
        self.client = make_client(self.up.user.pk)
        self.rando_client = make_client(self.pandora.user.pk)

    def tearDown(self) -> None:
        SCOTUSMap.objects.all().delete()
        JSONVersion.objects.all().delete()

    async def make_good_visualization(self, title: str) -> Response:
        data = {
            "title": title,
            "cluster_start": reverse(
                "opinioncluster-detail", kwargs={"version": "v3", "pk": 1}
            ),
            "cluster_end": reverse(
                "opinioncluster-detail", kwargs={"version": "v3", "pk": 2}
            ),
        }
        response = await self.client.post(self.path, data, format="json")
        return response

    async def test_no_title_visualization_post(self) -> None:
        data = {
            "title": "",
            "cluster_start": reverse(
                "opinioncluster-detail", kwargs={"version": "v3", "pk": 1}
            ),
            "cluster_end": reverse(
                "opinioncluster-detail", kwargs={"version": "v3", "pk": 2}
            ),
        }
        response = await self.client.post(self.path, data, format="json")
        res = response.json()
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(res["title"][0], "This field may not be blank.")

    async def test_no_cluster_start_visualization_post(self) -> None:
        data = {
            "title": "My Invalid Visualization - No Cluster Start Provided",
            "cluster_start": "",
            "cluster_end": reverse(
                "opinioncluster-detail", kwargs={"version": "v3", "pk": 2}
            ),
        }
        response = await self.client.post(self.path, data, format="json")
        res = response.json()
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            res["cluster_start"][0], "This field may not be null."
        )

    async def test_no_cluster_end_visualization_post(self) -> None:
        data = {
            "title": "My Invalid Visualization - No Cluster End Provided",
            "cluster_start": reverse(
                "opinioncluster-detail", kwargs={"version": "v3", "pk": 1}
            ),
            "cluster_end": "",
        }
        response = await self.client.post(self.path, data, format="json")
        res = response.json()
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(res["cluster_end"][0], "This field may not be null.")

    async def test_invalid_cluster_start_visualization_post(self) -> None:
        data = {
            "title": "My Invalid Visualization - No Cluster Exists",
            "cluster_start": reverse(
                "opinioncluster-detail", kwargs={"version": "v3", "pk": 999}
            ),
            "cluster_end": reverse(
                "opinioncluster-detail", kwargs={"version": "v3", "pk": 2}
            ),
        }
        response = await self.client.post(self.path, data, format="json")
        res = response.json()
        self.assertEqual(
            response.status_code,
            HTTPStatus.BAD_REQUEST,
            msg=f"Got {response.status_code} instead of {HTTPStatus.BAD_REQUEST}. JSON was:\n{res}",
        )
        self.assertEqual(
            res["cluster_start"][0],
            "Invalid hyperlink - Object does not exist.",
        )

    async def test_valid_visualization_post(self) -> None:
        title = "My Valid Visualization"
        response = await self.make_good_visualization(title)
        self.assertEqual(response.status_code, HTTPStatus.CREATED)
        res = response.json()
        self.assertEqual(res["title"], title)

        # cluster_start and cluster_end are reversed
        self.assertEqual(
            res["cluster_start"],
            "http://testserver%s"
            % reverse(
                "opinioncluster-detail", kwargs={"version": "v3", "pk": 2}
            ),
        )
        self.assertEqual(
            res["cluster_end"],
            "http://testserver%s"
            % reverse(
                "opinioncluster-detail", kwargs={"version": "v3", "pk": 1}
            ),
        )

    async def test_visualization_permissions(self) -> None:
        """Are some non-owners rejected from editing visualizations?"""
        response = await self.make_good_visualization("Some title")

        # Try to edit it as the current user; should work
        j = response.json()
        path = j["resource_uri"]
        response = await self.client.patch(
            path, {"published": True}, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

        # Try to edit it as a different user; should fail
        response = await self.rando_client.patch(
            path, {"published": True}, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

    async def test_json_data_permissions(self) -> None:
        """Are non-owners rejected from editing JSON data?"""
        response = await self.make_good_visualization("some title")

        # Try to edit the JSON as current user; should work
        j = response.json()
        vis_path = j["resource_uri"]
        json_path = j["json_versions"][0]["resource_uri"]
        response = await self.client.patch(
            json_path, {"json_data": "immaterial"}, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

        # Try to edit the JSON as different user, while private; should fail;
        # user shouldn't know it exists.
        response = await self.rando_client.patch(
            json_path, {"json_data": "immaterial"}, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)

        # Try to edit the JSON as different user, while public; should fail
        # Make it public
        response = await self.client.patch(
            vis_path, {"published": True}, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        # Try to patch it as a random user
        response = await self.rando_client.patch(
            json_path, {"json_data": "immaterial"}, format="json"
        )
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)
