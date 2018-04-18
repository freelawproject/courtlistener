from cl import settings
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.sunburnt.search import MltSolrSearch
from cl.lib.sunburnt.sunburnt import SolrInterface
from cl.recommendations.models import OpinionRecommendation
from cl.search.models import Opinion


ALGORITHMS = (
    ('mlt', 'MoreLikeThis')
)


class Command(VerboseCommand):
    help = 'Generates recommendations based on different algorithms (for now only MoreLikeThis is supported).'
    solr_conn = None  # type: SolrInterface
    solr_url = settings.SOLR_OPINION_URL
    recommendation_model = OpinionRecommendation
    seed_model = Opinion

    def add_arguments(self, parser):
        parser.add_argument(
            '--algorithm',
            type=str,
            default='mlt',
            help='Specify recommendation algorithm (available: mlt).'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Number of objects for that recommendations are generated.'
        )
        parser.add_argument(
            '--start',
            type=int,
            default=0,
            help='Paginate seed objects'
        )
        parser.add_argument(
            '--recommendations',
            type=int,
            default=10,
            help='Number of recommendations generated per seed object.'
        )
        parser.add_argument(
            '--delete',
            action='store_true',
            default=False,
            help='Delete all recommendations before saving new ones'
        )
        parser.add_argument(
            '--simulate',
            action='store_true',
            default=False,
            help='Simulate the recommendations. Do not save any recommendations in db.'
        )

    def get_solr_conn(self):
        """Get connection of Solr interface"""
        if self.solr_conn is None:
            self.solr_conn = SolrInterface(self.solr_url, mode='r')
        return self.solr_conn

    def get_recommendations(self, seed, fields=None, limit=10, start=1):
        """Perform MoreLikeThis query based on seed id and return results (in the future other algorithms
        can be used as well)"""

        if fields is None:
            fields = ['id']

        return MltSolrSearch(self.get_solr_conn(), url=self.solr_url + '/get?ids=%i' % seed.pk) \
            .mlt(fields=['text']) \
            .field_limit(fields=fields, score=True) \
            .paginate(start, limit) \
            .execute()

    def handle(self, *args, **options):
        logger.debug('Solr Interface: %s' % self.solr_url)

        if options['algorithm'] not in ALGORITHMS:
            raise ValueError('Selected recommendation algorithm is not supported: %s' % options['algorithm'])

        if options['delete']:
            logger.debug('Deleting all existing recommendations')
            self.recommendation_model.objects.all().delete()

        # Select seeds from db
        seeds = self.seed_model.objects.order_by('id')[options['start']:]

        if options['limit'] > 0:
            seeds = seeds[:options['limit']]

        for seed in seeds:
            logger.info('Seed is: %s' % seed)

            # Generate and save recommendations for each seed
            recommendations = self.get_recommendations(seed, limit=options['recommendations'])

            if len(recommendations) < 1:
                logger.warning('Could not generate recommendations for %s' % seed)
                continue

            for rec in recommendations:
                if rec['id'] != seed.pk:  # Seed cannot be recommendation

                    # Initialize recommendation instance
                    rec = self.recommendation_model(seed_id=seed.pk,
                                                    recommendation_id=rec['id'],
                                                    score=rec['score'])

                    if options['simulate']:
                        logger.debug('Generated (but not saved): %s' % rec)
                    else:
                        rec.save()
                        logger.debug('Saved: %s' % rec)

        logger.info('Recommendations generated.')
