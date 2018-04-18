from django.db import models

from cl.search.models import Opinion


class BaseRecommendation(models.Model):
    """Abstract model class for recommendations (when recommendations are used not only for opinions"""
    seed = None
    recommendation = None
    score = models.DecimalField(max_digits=12, decimal_places=8)

    class Meta:
        abstract = True
        unique_together = ('seed', 'recommendation',)

    def set_relation(self, seed_id, recommendation_id):
        self.seed_id = seed_id
        self.recommendation_id = recommendation_id

    def set_score(self, score):
        self.score = score

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return 'Recommendation(seed=%s, recommendation=%s, score=%s)' % (self.seed, self.recommendation, self.score)


class OpinionRecommendation(BaseRecommendation):
    seed = models.ForeignKey(Opinion, related_name='seed_id', on_delete=models.CASCADE)
    recommendation = models.ForeignKey(Opinion, related_name='recommendation_id', on_delete=models.CASCADE)

    @staticmethod
    def get_recommendations(seed=None, seed_id=None, n=10):

        if seed is not None:
            seed_id = seed.pk
        elif seed is None and seed_id is None:
            raise ValueError('At least "seed" or "seed_id" must be set.')

        recs = []
        for r in OpinionRecommendation.objects.filter(seed_id=seed_id).order_by('-score')[:n]:
            recs.append(r.recommendation)
        return recs
