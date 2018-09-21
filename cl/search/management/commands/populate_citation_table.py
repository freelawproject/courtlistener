from django.db import transaction

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
            citations = []
            for field in cluster.citation_fields:
                citation_str = getattr(cluster, field)
                if citation_str:
                    # Split the citation and add it to the DB.
                    citation_obj = get_citations(citation_str)[0]
                    citations.append(Citation(
                        cluster=cluster,
                        volume=citation_obj.volume,
                        reporter=citation_obj.reporter,
                        page=citation_obj.page,
                        type=map_model_field_to_citation_type(field)
                    ))
            if citations:
                with transaction.atomic():
                    Citation.objects.bulk_create(citations)

            if i % 1000 == 0:
                logger.info("Completed %s items", i)

