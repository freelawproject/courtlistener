import logging
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from haystack.backends import log_query
from haystack.backends.solr_backend import SearchBackend
from haystack.constants import DJANGO_CT
from pysolr import Solr, SolrError

BACKEND_NAME = 'custom_solr'

class SearchBackend(SearchBackend):
    def __init__(self, site=None):
        super(SearchBackend, self).__init__(site)

        if not hasattr(settings, 'HAYSTACK_SOLR_URL'):
            raise ImproperlyConfigured('You must specify a HAYSTACK_SOLR_URL in your settings.')

        timeout = getattr(settings, 'HAYSTACK_SOLR_TIMEOUT', 10)
        self.conn = Solr(settings.HAYSTACK_SOLR_URL)

    @log_query
    def search(self, query_string, sort_by=None, start_offset=0, end_offset=None,
               fields='', highlight=False, facets=None, date_facets=None, query_facets=None,
               narrow_queries=None, spelling_query=None,
               limit_to_registered_models=None, result_class=None, **kwargs):
        if len(query_string) == 0:
            return {
                'results': [],
                'hits': 0,
            }

        kwargs = {
            'fl': '* score',
        }

        if fields:
            kwargs['fl'] = fields

        if sort_by is not None:
            kwargs['sort'] = sort_by

        if start_offset is not None:
            kwargs['start'] = start_offset

        if end_offset is not None:
            kwargs['rows'] = end_offset - start_offset

        if highlight is True:
            kwargs['hl'] = 'true'
            kwargs['hl.fragsize'] = '200'

        if getattr(settings, 'HAYSTACK_INCLUDE_SPELLING', False) is True:
            kwargs['spellcheck'] = 'true'
            kwargs['spellcheck.collate'] = 'true'
            kwargs['spellcheck.count'] = 1

            if spelling_query:
                kwargs['spellcheck.q'] = spelling_query

        if facets is not None:
            kwargs['facet'] = 'on'
            kwargs['facet.field'] = facets

        if date_facets is not None:
            kwargs['facet'] = 'on'
            kwargs['facet.date'] = date_facets.keys()
            kwargs['facet.date.other'] = 'none'

            for key, value in date_facets.items():
                kwargs["f.%s.facet.date.start" % key] = self.conn._from_python(value.get('start_date'))
                kwargs["f.%s.facet.date.end" % key] = self.conn._from_python(value.get('end_date'))
                gap_by_string = value.get('gap_by').upper()
                gap_string = "%d%s" % (value.get('gap_amount'), gap_by_string)

                if value.get('gap_amount') != 1:
                    gap_string += "S"

                kwargs["f.%s.facet.date.gap" % key] = '+%s/%s' % (gap_string, gap_by_string)

        if query_facets is not None:
            kwargs['facet'] = 'on'
            kwargs['facet.query'] = ["%s:%s" % (field, value) for field, value in query_facets]

        if limit_to_registered_models is None:
            limit_to_registered_models = getattr(settings, 'HAYSTACK_LIMIT_TO_REGISTERED_MODELS', True)

        if limit_to_registered_models:
            # Using narrow queries, limit the results to only models registered
            # with the current site.
            if narrow_queries is None:
                narrow_queries = set()

            registered_models = self.build_registered_models_list()

            if len(registered_models) > 0:
                narrow_queries.add('%s:(%s)' % (DJANGO_CT, ' OR '.join(registered_models)))

        if narrow_queries is not None:
            kwargs['fq'] = list(narrow_queries)

        try:
            raw_results = self.conn.search(query_string, **kwargs)
        except (IOError, SolrError), e:
            if not self.silently_fail:
                raise

            self.log.error("Failed to query Solr using '%s': %s", query_string, e)
            raw_results = EmptyResults()

        return self._process_results(raw_results, highlight=highlight, result_class=result_class)
