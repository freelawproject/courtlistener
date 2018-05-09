

"""

models:
- add / update
- get in order

commands:
- read from file
(- generate with mlt)

search:
- combine with other queries
- filter
- ...

"""
from django.test import TransactionTestCase, TestCase

from cl.recommendations.models import OpinionRecommendation


class TestRecommendationModels(TestCase):
    def test_get_recommendations(self):
        print('x')
        recs = OpinionRecommendation().get_recommendations(seed_id=1, n=10)

        self.assertEqual(len(recs), 10, 'Invalid number of recommendations returned')
