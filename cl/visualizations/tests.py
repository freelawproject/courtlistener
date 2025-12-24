"""
Unit tests for Visualizations
"""

from http import HTTPStatus

from asgiref.sync import sync_to_async
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.response import Response

from cl.search.models import OpinionCluster
from cl.tests.cases import APITestCase, SimpleTestCase, TestCase
from cl.tests.utils import make_client
from cl.users.factories import UserProfileWithParentsFactory
from cl.visualizations.factories import VisualizationFactory
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


class TestVisualizationRedirects(SimpleTestCase):
    """Test that deprecated visualization URLs redirect properly."""

    def test_deprecated_urls_redirect_to_api_docs(self) -> None:
        """Test all deprecated visualization URLs redirect to API docs."""
        expected_redirect = reverse("visualization_api_help")
        # Raw URLs for visualization paths (catch-all handles these)
        urls = [
            "/visualizations/scotus-mapper/",
            "/visualizations/scotus-mapper/new/",
            "/visualizations/gallery/",
            "/visualizations/scotus-mapper/1/test/",
            "/visualizations/scotus-mapper/1/edit/",
            "/visualizations/anything/else/",
            # Named URLs still defined in users/urls.py
            reverse("view_visualizations"),
            reverse("view_deleted_visualizations"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    HTTPStatus.MOVED_PERMANENTLY,
                    msg=f"{url} should return 301",
                )
                self.assertEqual(
                    response.url,
                    f"{expected_redirect}#deprecation-notice",
                    msg=f"{url} should redirect to API docs",
                )


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

    async def make_good_visualization(self, title: str) -> "Response":
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
            "http://testserver{}".format(
                reverse(
                    "opinioncluster-detail", kwargs={"version": "v3", "pk": 2}
                )
            ),
        )
        self.assertEqual(
            res["cluster_end"],
            f"http://testserver{
                reverse(
                    'opinioncluster-detail', kwargs={'version': 'v3', 'pk': 1}
                )
            }",
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
