from asgiref.sync import async_to_sync

from cl.search.factories import (
    CitationWithParentsFactory,
    OpinionClusterWithParentsFactory,
    OpinionFactory,
    OpinionsCitedWithParentsFactory,
)
from cl.search.models import OpinionCluster
from cl.tests.cases import TestCase


class OpinionClusterAuthoritiesTest(TestCase):
    citing_cluster: OpinionCluster
    authority_1: OpinionCluster
    authority_2: OpinionCluster

    @classmethod
    def setUpTestData(cls) -> None:
        cls.citing_cluster = OpinionClusterWithParentsFactory.create()
        citing_opinion_1 = OpinionFactory.create(cluster=cls.citing_cluster)
        citing_opinion_2 = OpinionFactory.create(cluster=cls.citing_cluster)

        cls.authority_1 = OpinionClusterWithParentsFactory.create()
        authority_1_opinion_1 = OpinionFactory.create(cluster=cls.authority_1)
        authority_1_opinion_2 = OpinionFactory.create(cluster=cls.authority_1)
        CitationWithParentsFactory.create(cluster=cls.authority_1)

        cls.authority_2 = OpinionClusterWithParentsFactory.create()
        authority_2_opinion = OpinionFactory.create(cluster=cls.authority_2)
        CitationWithParentsFactory.create(cluster=cls.authority_2)

        OpinionsCitedWithParentsFactory.create(
            citing_opinion=citing_opinion_1,
            cited_opinion=authority_1_opinion_1,
            depth=2,
        )
        OpinionsCitedWithParentsFactory.create(
            citing_opinion=citing_opinion_2,
            cited_opinion=authority_1_opinion_2,
            depth=3,
        )
        OpinionsCitedWithParentsFactory.create(
            citing_opinion=citing_opinion_1,
            cited_opinion=authority_2_opinion,
            depth=7,
        )

        # A citation within the same cluster must not make the cluster its own
        # authority.
        OpinionsCitedWithParentsFactory.create(
            citing_opinion=citing_opinion_1,
            cited_opinion=citing_opinion_2,
            depth=100,
        )

        # Citations from other clusters must not contribute to this cluster's
        # aggregate depth.
        unrelated_cluster = OpinionClusterWithParentsFactory.create()
        unrelated_opinion = OpinionFactory.create(cluster=unrelated_cluster)
        OpinionsCitedWithParentsFactory.create(
            citing_opinion=unrelated_opinion,
            cited_opinion=authority_2_opinion,
            depth=200,
        )

    def test_authorities_are_aggregated_by_cluster(self) -> None:
        authorities = list(
            self.citing_cluster.authorities.order_by("-citation_depth")
        )

        self.assertEqual(
            [authority.pk for authority in authorities],
            [self.authority_2.pk, self.authority_1.pk],
        )
        self.assertEqual(
            [authority.citation_depth for authority in authorities],
            [7, 5],
        )

    def test_authorities_with_data_uses_constant_queries(self) -> None:
        with self.assertNumQueries(2):
            authorities = list(self.citing_cluster.authorities_with_data)

        with self.assertNumQueries(0):
            display_data = [
                (
                    authority.docket.court.full_name,
                    authority.citation_string,
                    authority.citation_depth,
                )
                for authority in authorities
            ]

        self.assertEqual(
            [authority.pk for authority in authorities],
            [self.authority_2.pk, self.authority_1.pk],
        )
        self.assertEqual([data[2] for data in display_data], [7, 5])

    def test_async_authorities_with_data_matches_sync_queryset(self) -> None:
        authorities = async_to_sync(
            self.citing_cluster.aauthorities_with_data
        )()

        self.assertEqual(
            [authority.pk for authority in authorities],
            [self.authority_2.pk, self.authority_1.pk],
        )
