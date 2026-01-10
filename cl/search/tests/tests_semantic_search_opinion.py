import json
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest import mock
from unittest.mock import MagicMock

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from elasticsearch.dsl import Document
from waffle.testutils import override_flag

from cl.lib.search_index_utils import index_documents_in_bulk
from cl.search.documents import ES_CHILD_ID, OpinionDocument
from cl.search.factories import (
    CourtFactory,
    DocketFactory,
    EmbeddingsDataFactory,
    OpinionClusterFactory,
    OpinionFactory,
)
from cl.search.models import PRECEDENTIAL_STATUS, Docket, Opinion, SearchQuery
from cl.tests.cases import ESIndexTestCase, TestCase


def mock_read_from_s3(file_path, r):
    """Mock bucket.open() to return fake embeddings JSON content for
    a given opinion ID."""
    opinion_id_str = Path(file_path).stem.split("_")[-1]
    opinion_id = int(opinion_id_str)
    fake_embedding_data = EmbeddingsDataFactory.build(id=opinion_id)
    fake_json = json.dumps(fake_embedding_data).encode("utf-8")
    return BytesIO(fake_json)


class OpinionEmbeddingIndexingTests(ESIndexTestCase, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("search.OpinionCluster")
        cls.court = CourtFactory(
            id="canb",
            jurisdiction="FB",
        )
        with cls.captureOnCommitCallbacks(execute=True) as callbacks:
            cls.opinion_cluster_2 = OpinionClusterFactory(
                docket=DocketFactory(
                    court=cls.court,
                    docket_number="1:21-cv-1235",
                    source=Docket.HARVARD,
                ),
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            )

    def test_opinion_embeddings_field(self) -> None:
        """Test index embeddings into an opinion document."""
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            opinion_cluster_1 = OpinionClusterFactory(
                docket=DocketFactory(
                    court=self.court,
                    docket_number="1:21-cv-1234",
                    source=Docket.HARVARD,
                ),
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
            )
            opinion_1 = OpinionFactory(
                cluster=opinion_cluster_1,
                html_columbia=(
                    "<p>Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
                    "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa "
                    "quae ab illo inventore veritatis et quasi architecto beatae vitae dicta "
                    "sunt explicabo. Sed ut perspiciatis unde omnis iste natus error sit voluptatem "
                    "accusantium doloremque laudantium, totam rem aperiam, eaque ipsa unde omnis iste</p>"
                ),
            )

        es_opinion_1 = OpinionDocument.get(
            id=ES_CHILD_ID(opinion_1.pk).OPINION
        )
        self.assertEqual(es_opinion_1.embeddings, [])

        test_dir = (
            Path(settings.INSTALL_ROOT) / "cl" / "search" / "test_assets"
        )
        with open(
            test_dir / "opinion_1_embeddings.json",
            encoding="utf-8",
        ) as embeddings_file:
            opinion_1_embeddings = json.load(embeddings_file)
            Document.update(
                es_opinion_1,
                **{"embeddings": opinion_1_embeddings["embeddings"]},
                refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
            )

        # Opinion embedding should be now indexed into the document.
        es_opinion_1 = OpinionDocument.get(
            id=ES_CHILD_ID(opinion_1.pk).OPINION
        )
        self.assertEqual(
            es_opinion_1.embeddings, opinion_1_embeddings["embeddings"]
        )

    def test_cl_index_embeddings(self) -> None:
        """Test cl_index_embeddings command"""
        with self.captureOnCommitCallbacks(execute=True):
            opinion_2 = OpinionFactory(
                cluster=self.opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )
            opinion_3 = OpinionFactory(
                cluster=self.opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )

        for opinion in (opinion_2, opinion_3):
            self.assertEqual(
                OpinionDocument.get(
                    id=ES_CHILD_ID(opinion.pk).OPINION
                ).embeddings,
                [],
            )

        with mock.patch(
            "cl.search.tasks.AWSMediaStorage.open",
            side_effect=mock_read_from_s3,
        ):
            call_command(
                "cl_index_embeddings",
                batch_size=2,
                indexing_queue="celery",
                start_id=0,
            )

        for opinion in (opinion_2, opinion_3):
            self.assertTrue(
                OpinionDocument.get(
                    id=ES_CHILD_ID(opinion.pk).OPINION
                ).embeddings
            )

    @mock.patch(
        "cl.search.tasks.index_documents_in_bulk",
        wraps=index_documents_in_bulk,
    )
    def test_cl_index_embeddings_skip_versioned_opinion(
        self, bulk_index_mock
    ) -> None:
        """Ensure versioned opinions are skipped during embeddings indexing."""
        # Create two opinions: one main and one versioned
        with self.captureOnCommitCallbacks(execute=True):
            opinion_2 = OpinionFactory(
                cluster=self.opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )
            opinion_3 = OpinionFactory(
                cluster=self.opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
                main_version=opinion_2,
            )

        # Assert initial state
        self.assertEqual(
            OpinionDocument.get(
                id=ES_CHILD_ID(opinion_2.pk).OPINION
            ).embeddings,
            [],
        )
        # Versioned opinion should not exist in Elasticsearch
        self.assertFalse(
            OpinionDocument.exists(id=ES_CHILD_ID(opinion_3.pk).OPINION)
        )

        # Single opinion processing: versioned opinion should NOT trigger bulk
        # indexing
        with mock.patch(
            "cl.search.tasks.AWSMediaStorage.open",
            side_effect=mock_read_from_s3,
        ):
            call_command(
                "cl_index_embeddings",
                batch_size=1,
                indexing_queue="celery",
                start_id=opinion_3.id,
            )

        bulk_index_mock.assert_not_called()

        # processing a batch including a versioned opinion should trigger bulk
        # indexing but the versioned opinion itself should not be added to
        # Elasticsearch
        with mock.patch(
            "cl.search.tasks.AWSMediaStorage.open",
            side_effect=mock_read_from_s3,
        ):
            call_command(
                "cl_index_embeddings",
                batch_size=2,
                indexing_queue="celery",
                start_id=0,
            )

        # Assert main opinion now has embeddings
        self.assertTrue(
            OpinionDocument.get(
                id=ES_CHILD_ID(opinion_2.pk).OPINION
            ).embeddings,
        )

        # Assert versioned opinion is still not indexed
        self.assertFalse(
            OpinionDocument.exists(id=ES_CHILD_ID(opinion_3.pk).OPINION)
        )

    def test_cl_index_embeddings_from_inventory(self):
        """Test cl_index_embeddings command using an S3 inventory file."""
        with self.captureOnCommitCallbacks(execute=True):
            opinion_4 = OpinionFactory(
                cluster=self.opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )
            opinion_5 = OpinionFactory(
                cluster=self.opinion_cluster_2,
                html_columbia=("<p>Sed ut perspiciatis</p>"),
            )
        for opinion in (opinion_4, opinion_5):
            self.assertEqual(
                OpinionDocument.get(
                    id=ES_CHILD_ID(opinion.pk).OPINION
                ).embeddings,
                [],
            )

        csv_lines = [
            f'"com-courtlistener-storage","embeddings/opinions/freelawproject/'
            f'modernbert-embed-base_finetune_512/{opinion_4.pk}.json","2025-06-24T00:00:00.000Z"',
            f'"com-courtlistener-storage","embeddings/opinions/freelawproject/'
            f'modernbert-embed-base_finetune_512/{opinion_5.pk}.json","2025-06-24T00:00:00.000Z"',
        ]
        mock_csv_content = "\n".join(csv_lines) + "\n"
        with (
            mock.patch(
                "cl.search.tasks.AWSMediaStorage.open",
                side_effect=mock_read_from_s3,
            ),
            mock.patch("pathlib.Path.exists", return_value=True),
            mock.patch(
                "pathlib.Path.open", mock.mock_open(read_data=mock_csv_content)
            ),
        ):
            call_command(
                "cl_index_embeddings",
                batch_size=2,
                inventory_file="test_inventory.csv",
                inventory_rows=len(csv_lines),
            )

        # Confirm embeddings are indexed.
        for opinion in (opinion_4, opinion_5):
            self.assertTrue(
                OpinionDocument.get(
                    id=ES_CHILD_ID(opinion.pk).OPINION
                ).embeddings
            )


@override_settings(KNN_SIMILARITY=0.3)
@override_settings(KNN_SEARCH_ENABLED=True)
@mock.patch("cl.lib.elasticsearch_utils.microservice")
class SemanticSearchTests(ESIndexTestCase, TestCase):
    @classmethod
    def setUpTestData(cls):
        """Set up test index and test data."""
        cls.rebuild_index("search.OpinionCluster")
        cls.ohio_court = CourtFactory(
            id="ohioctapp",
            jurisdiction="SA",
            full_name="Ohio Court of Appeals",
        )
        cls.vermont_court = CourtFactory(
            id="vt", jurisdiction="S", full_name="Supreme Court of Vermont"
        )
        cls.situational_query = (
            "Can a tenant break a lease due to uninhabitable conditions?"
        )
        cls.hybrid_query = (
            'Can a tenant break a lease due to "uninhabitable conditions"?'
        )

        # Create opinions and clusters
        with cls.captureOnCommitCallbacks(execute=True) as callbacks:
            cls.opinion_2 = OpinionFactory(
                cluster=OpinionClusterFactory(
                    docket=DocketFactory(
                        court=cls.ohio_court,
                        docket_number="30274",
                        source=Docket.SCRAPER,
                    ),
                    precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                    citation_count=5,
                )
            )

            cls.opinion_3 = OpinionFactory(
                cluster=OpinionClusterFactory(
                    docket=DocketFactory(
                        court=cls.vermont_court,
                        docket_number="24-AP-118",
                        source=Docket.SCRAPER,
                    ),
                    precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                    citation_count=1,
                )
            )
            cls.opinion_4 = OpinionFactory(
                cluster=OpinionClusterFactory(
                    docket=DocketFactory(),
                    precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                )
            )
            # Opinion without embeddings; should match keyword-only queries.
            cls.opinion_5 = OpinionFactory(
                plain_text="...which the then owner maintained in an uninhabitable conditions",
                cluster=OpinionClusterFactory(
                    docket=DocketFactory(),
                    precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                ),
            )
            # Cluster with no opinions; should not match any queries.
            cls.cluster = OpinionClusterFactory(
                docket=DocketFactory(
                    source=Docket.SCRAPER,
                ),
                precedential_status=PRECEDENTIAL_STATUS.PUBLISHED,
                case_name="Uninhabitable Conditions Corp v. Washington.",
                case_name_full="Uninhabitable Conditions Corp v. Washington.",
            )

        # Fetch Elasticsearch document representations
        es_opinions = {
            "opinion_2": OpinionDocument.get(
                id=ES_CHILD_ID(cls.opinion_2.pk).OPINION
            ),
            "opinion_3": OpinionDocument.get(
                id=ES_CHILD_ID(cls.opinion_3.pk).OPINION
            ),
            "opinion_4": OpinionDocument.get(
                id=ES_CHILD_ID(cls.opinion_4.pk).OPINION
            ),
            "opinion_5": OpinionDocument.get(
                id=ES_CHILD_ID(cls.opinion_5.pk).OPINION
            ),
        }

        cls.test_dir = (
            Path(settings.INSTALL_ROOT) / "cl" / "search" / "test_assets"
        )
        # Load embeddings for query
        with open(
            cls.test_dir / "situational_query_embeddings.json",
            encoding="utf-8",
        ) as f:
            cls.situational_query_vectors = json.load(f)

        # Update documents with precomputed embeddings
        for key, opinion in es_opinions.items():
            filename = f"{key}_embeddings.json"
            with open(cls.test_dir / filename, encoding="utf-8") as f:
                embeddings = json.load(f)
                Document.update(
                    opinion,
                    **{"embeddings": embeddings["embeddings"]},
                    refresh=settings.ELASTICSEARCH_DSL_AUTO_REFRESH,
                )

    def _get_mock_for_inception(self, vectors: dict[str, Any] | None = None):
        """Return a mocked Inception response with the given vectors."""
        inception_response = MagicMock()
        inception_response.json.return_value = vectors
        return inception_response

    def _test_api_results_count(self, params, expected_count, field_name):
        """Get the result count in a API query response"""
        r = self.client.get(
            reverse("search-list", kwargs={"version": "v4"}), params
        )
        got = len(r.data["results"])
        self.assertEqual(
            got,
            expected_count,
            msg=f"Did not get the right number of search results in API with {field_name} "
            "filter applied.\n"
            f"Expected: {expected_count}\n"
            f"     Got: {got}\n\n"
            f"Params were: {params}",
        )
        return r

    @override_flag("store-search-api-queries", active=True)
    @override_settings(WAFFLE_CACHE_PREFIX="test_semantic_search_opinion")
    def test_can_perform_a_regular_semantic_query(
        self, inception_mock
    ) -> None:
        """Can we perform a semantic search using the API?"""

        inception_mock.return_value = self._get_mock_for_inception(
            self.situational_query_vectors
        )

        # Perform search and check that exactly two results are returned
        search_params = {"q": self.situational_query, "semantic": True}
        r = self._test_api_results_count(search_params, 2, "semantic query")

        # Ensure a SearchQuery row was logged with SEMANTIC querymode
        last_query = SearchQuery.objects.last()
        self.assertEqual(last_query.query_mode, SearchQuery.SEMANTIC)

        content = r.content.decode()
        # Check that the expected clusters appear in the results
        self.assertIn(f'"cluster_id":{self.opinion_2.cluster.id}', content)
        self.assertIn(f'"cluster_id":{self.opinion_3.cluster.id}', content)

        # Check that the snippet does not default to the start of the plain
        # text, but instead uses the semantically relevant chunk
        for cluster in r.data["results"]:
            with self.subTest(
                cluster_id=cluster["cluster_id"], msg="Snippet content test."
            ):
                for opinion in cluster["opinions"]:
                    record = Opinion.objects.get(id=opinion["id"])
                    self.assertNotEqual(
                        opinion["snippet"],
                        record.plain_text[: settings.NO_MATCH_HL_SIZE],
                    )

        # Ensure that other clusters are not erroneously included
        self.assertNotIn(f'"cluster_id":{self.opinion_4.cluster.id}', content)
        self.assertNotIn(f'"cluster_id":{self.opinion_5.cluster.id}', content)

    def test_can_apply_filter_to_semantic_query(self, inception_mock) -> None:
        """Can we apply filtering to semantic search results?"""
        inception_mock.return_value = self._get_mock_for_inception(
            self.situational_query_vectors
        )

        # Filter by court ID
        search_params = {
            "q": self.situational_query,
            "semantic": True,
            "court": self.ohio_court.id,
        }

        # Should return only the opinion from the Ohio court
        r = self._test_api_results_count(
            search_params, 1, "semantic query with court filter"
        )
        content = r.content.decode()
        self.assertIn(f'"cluster_id":{self.opinion_2.cluster.id}', content)
        self.assertNotIn(f'"cluster_id":{self.opinion_3.cluster.id}', content)

        # Filter by docket number
        search_params = {
            "q": self.situational_query,
            "semantic": True,
            "docket_number": "24-AP-118",
        }

        # Should return only the result matching the docket number
        r = self._test_api_results_count(
            search_params, 1, "semantic query with docket number filter"
        )
        content = r.content.decode()
        self.assertNotIn(f'"cluster_id":{self.opinion_2.cluster.id}', content)
        self.assertIn(f'"cluster_id":{self.opinion_3.cluster.id}', content)

    def test_can_sort_semantic_search_results(self, inception_mock) -> None:
        """Can we sort semantic search results by cite count?"""
        inception_mock.return_value = self._get_mock_for_inception(
            self.situational_query_vectors
        )

        # Sort by citation count descending
        search_params = {
            "q": self.situational_query,
            "semantic": True,
            "order_by": "citeCount desc",
        }
        r = self._test_api_results_count(search_params, 2, "citeCount desc")
        content = r.content.decode()

        # Opinion with higher cite count should appear first
        self.assertTrue(
            content.index(f'"cluster_id":{self.opinion_2.cluster_id}')
            < content.index(f'"cluster_id":{self.opinion_3.cluster_id}'),
            msg=f"'{self.opinion_2}' should come BEFORE '{self.opinion_3}' when"
            " ordered by descending citeCount.",
        )

        # Sort by citation count ascending
        search_params = {
            "q": self.situational_query,
            "semantic": True,
            "order_by": "citeCount asc",
        }
        r = self._test_api_results_count(search_params, 2, "citeCount asc")
        content = r.content.decode()

        # Opinion with lower cite count should appear first
        self.assertTrue(
            content.index(f'"cluster_id":{self.opinion_3.cluster_id}')
            < content.index(f'"cluster_id":{self.opinion_2.cluster_id}'),
            msg=f"'{self.opinion_3}' should come BEFORE '{self.opinion_2}' when"
            " ordered by ascending citeCount.",
        )

    def test_is_semantic_score_standarized(self, inception_mock) -> None:
        """Ensure that semantic scores are consistently returned as floats"""
        inception_mock.return_value = self._get_mock_for_inception(
            self.situational_query_vectors
        )

        search_params = {"q": self.hybrid_query, "semantic": True}
        r = self._test_api_results_count(
            search_params, 3, "hybrid semantic search query"
        )

        # Validate semantic scores:
        # - Should be 0.0 for keyword-only matches
        # - Should be > 0.0 for clusters matched semantically
        for cluster in r.data["results"]:
            with self.subTest(
                cluster_id=cluster["cluster_id"], msg="Semantic score test."
            ):
                semantic_score = cluster["meta"]["score"]["semantic"]
                if cluster["cluster_id"] in [
                    self.opinion_2.cluster_id,
                    self.opinion_3.cluster_id,
                ]:
                    self.assertNotEqual(semantic_score, 0.0)
                else:
                    self.assertEqual(semantic_score, 0.0)

    def test_can_do_hybrid_search_query(self, inception_mock) -> None:
        """Can we combine semantic and keyword matches in hybrid search?"""
        inception_mock.return_value = self._get_mock_for_inception(
            self.situational_query_vectors
        )

        # Hybrid query should return semantic and keyword matches (3 total)
        search_params = {"q": self.hybrid_query, "semantic": True}
        r = self._test_api_results_count(
            search_params, 3, "hybrid semantic search query"
        )
        content = r.content.decode()

        # Should include the two opinions with embeddings
        self.assertIn(f'"cluster_id":{self.opinion_2.cluster.id}', content)
        self.assertIn(f'"cluster_id":{self.opinion_3.cluster.id}', content)

        # Should also include the keyword-only match (no embeddings)
        self.assertIn(f'"cluster_id":{self.opinion_5.cluster.id}', content)

        # Verify the cluster with no opinion is not included.
        self.assertNotIn(f'"cluster_id":{self.cluster.id}', content)

        # Verify snippet behavior:
        # - For keyword-only matches, snippet should default to plain text
        # - For semantic matches, snippet should come from the relevant chunk
        for cluster in r.data["results"]:
            with self.subTest(
                cluster_id=cluster["cluster_id"], msg="Snippet content test."
            ):
                for opinion in cluster["opinions"]:
                    record = Opinion.objects.get(id=opinion["id"])
                    if record.id == self.opinion_5.id:
                        self.assertEqual(
                            opinion["snippet"],
                            record.plain_text[: settings.NO_MATCH_HL_SIZE],
                        )
                    else:
                        self.assertNotEqual(
                            opinion["snippet"],
                            record.plain_text[: settings.NO_MATCH_HL_SIZE],
                        )

    def test_can_reject_post_request_when_semantic_flag_missing(
        self, inception_mock
    ) -> None:
        """Should reject POST request if `semantic=true` is not in query params."""
        r = self.client.post(
            reverse("search-list", kwargs={"version": "v4"}),
            data=self.situational_query_vectors,
            format="json",
        )
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
        data = r.json()
        self.assertIn("semantic", data)
        self.assertEqual(
            data["semantic"][0],
            "Semantic search requires `semantic=true` in the query string.",
        )

    def test_can_reject_post_request_when_embedding_missing(
        self, inception_mock
    ):
        """Should reject request if semantic search is requested without an embedding."""
        api_url = reverse("search-list", kwargs={"version": "v4"})
        r = self.client.post(
            f"{api_url}",
            data={},
            format="json",
            query_params={"semantic": True},
        )
        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
        data = r.json()
        self.assertIn("embedding", data)
        self.assertEqual(
            data["embedding"][0],
            "You must provide an embedding vector in the request body when using semantic search.",
        )

    def test_rejects_request_with_unsupported_type(self, inception_mock):
        """Should return an error if semantic search is requested with an unsupported type."""
        api_url = reverse("search-list", kwargs={"version": "v4"})

        # Send a valid vector but with an unsupported type
        r = self.client.post(
            f"{api_url}",
            data=self.situational_query_vectors,
            format="json",
            query_params={"semantic": True, "type": "r"},
        )

        self.assertEqual(r.status_code, HTTPStatus.BAD_REQUEST)
        data = r.json()
        self.assertIn("type", data)
        error_message = data["type"][0]
        self.assertIn("Unsupported search type 'r'", error_message)
        self.assertIn(
            "Semantic search is only supported for type", error_message
        )

    def test_valid_post_request_skips_computing_embeddings(
        self, inception_mock
    ):
        """Should pass query params and embedding to Elasticsearch query runner."""
        api_url = reverse("search-list", kwargs={"version": "v4"})
        r = self.client.post(
            f"{api_url}",
            data=self.situational_query_vectors,
            format="json",
            query_params={"semantic": True},
        )

        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertEqual(len(r.data["results"]), 2)

        content = r.content.decode()
        # Check that the expected clusters appear in the results
        self.assertIn(f'"cluster_id":{self.opinion_2.cluster.id}', content)
        self.assertIn(f'"cluster_id":{self.opinion_3.cluster.id}', content)

        # Check the inception microservice was not called
        inception_mock.assert_not_called()

        # mock a hybrid search query
        r = self.client.post(
            f"{api_url}",
            data=self.situational_query_vectors,
            format="json",
            query_params={"semantic": True, "q": self.hybrid_query},
        )
        self.assertEqual(r.status_code, HTTPStatus.OK)
        self.assertEqual(len(r.data["results"]), 3)

        content = r.content.decode()
        # Should include the two opinions with embeddings
        self.assertIn(f'"cluster_id":{self.opinion_2.cluster.id}', content)
        self.assertIn(f'"cluster_id":{self.opinion_3.cluster.id}', content)

        # Should also include the keyword-only match (no embeddings)
        self.assertIn(f'"cluster_id":{self.opinion_5.cluster.id}', content)
