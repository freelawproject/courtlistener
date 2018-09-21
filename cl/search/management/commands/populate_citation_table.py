from django.db.utils import IntegrityError

from cl.citations.find_citations import get_citations
from cl.lib.command_utils import VerboseCommand, logger
from cl.lib.db_tools import queryset_generator
from cl.search.models import OpinionCluster, Citation


def map_model_field_to_citation_type(field_name):
    if field_name.startswith('federal_cite'):
        return Citation.FEDERAL
    if field_name == 'state_cite_regional':
        return Citation.STATE_REGIONAL
    if field_name.startswith('state_cite_'):
        return Citation.STATE
    if field_name.startswith('specialty_cite_'):
        return Citation.SPECIALTY
    if field_name == 'scotus_early_cite':
        return Citation.SCOTUS_EARLY
    if field_name == 'lexis_cite':
        return Citation.LEXIS
    if field_name == 'westlaw_cite':
        return Citation.WEST
    if field_name == 'neutral_cite':
        return Citation.NEUTRAL


class Command(VerboseCommand):
    help = 'Copy the citations from the old cluster fields to the new table'

    def handle(self, *args, **options):
        super(Command, self).handle(*args, **options)
        qs = OpinionCluster.objects.all()
        for i, cluster in enumerate(queryset_generator(qs)):
            for field in cluster.citation_fields:
                citation_str = getattr(cluster, field)
                if citation_str:
                    # Split the citation and add it to the DB.
                    try:
                        citation_obj = get_citations(
                            citation_str,
                            html=False,
                            do_post_citation=False,
                            do_defendant=False,
                            disambiguate=False,
                        )[0]
                    except IndexError:
                        print("Errored out on: %s" % citation_str)
                        exit(1)
                    try:
                        Citation.objects.create(
                            cluster=cluster,
                            volume=citation_obj.volume,
                            reporter=citation_obj.reporter,
                            page=citation_obj.page,
                            type=map_model_field_to_citation_type(field)
                        )
                    except IntegrityError:
                        # Violated unique_together constraint. Fine.
                        pass

            if i % 1000 == 0:
                msg = "Completed %s items (last: %s)"
                print(msg % (i, cluster.pk))
                logger.info(msg, i, cluster.pk)

