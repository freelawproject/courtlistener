from django.db import models

from cl.audio.models import Audio
from cl.people_db.models import Person
from cl.search.models import Opinion, Docket


class BaseRecommendation(models.Model):
    """Abstract model class for recommendations (when recommendations are used not only for opinions"""
    seed = None
    recommendation = None
    score = models.DecimalField(max_digits=12, decimal_places=8)
    available_models = ['opinion', 'audio', 'person', 'docket']

    class Meta:
        abstract = True
        unique_together = ('seed', 'recommendation',)

    def set_relation(self, seed_id, recommendation_id):
        self.seed_id = seed_id
        self.recommendation_id = recommendation_id

    def set_score(self, score):
        self.score = score

    def get_recommendations(self, seed=None, seed_id=None, n=10):
        if seed is not None:
            seed_id = seed.pk
        elif seed is None and seed_id is None:
            raise ValueError('At least "seed" or "seed_id" must be set.')

        recs = []
        for r in self._default_manager.filter(seed_id=seed_id).order_by('-score')[:n]:
            recs.append(r.recommendation)
        return recs

    @staticmethod
    def get_model_class(name):
        if name == 'opinion':
            return OpinionRecommendation
        elif name == 'audio':
            return AudioRecommendation
        elif name == 'person':
            return PersonRecommendation
        elif name == 'docket':
            return DocketRecommendation
        else:
            raise ValueError('Unsupported model name: %s' % name)

    def __str__(self):
        return 'Recommendation(seed=%s, recommendation=%s, score=%s)' % (self.seed, self.recommendation, self.score)


class OpinionRecommendation(BaseRecommendation):
    seed = models.ForeignKey(Opinion, related_name='seed_id', on_delete=models.CASCADE)
    recommendation = models.ForeignKey(Opinion, related_name='recommendation_id', on_delete=models.CASCADE)


class AudioRecommendation(BaseRecommendation):
    seed = models.ForeignKey(Audio, related_name='seed_id', on_delete=models.CASCADE)
    recommendation = models.ForeignKey(Audio, related_name='recommendation_id', on_delete=models.CASCADE)


class PersonRecommendation(BaseRecommendation):
    seed = models.ForeignKey(Person, related_name='seed_id', on_delete=models.CASCADE)
    recommendation = models.ForeignKey(Person, related_name='recommendation_id', on_delete=models.CASCADE)


class DocketRecommendation(BaseRecommendation):
    seed = models.ForeignKey(Docket, related_name='seed_id', on_delete=models.CASCADE)
    recommendation = models.ForeignKey(Docket, related_name='recommendation_id', on_delete=models.CASCADE)


