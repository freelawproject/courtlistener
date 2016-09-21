from scorched import SolrInterface
from scorched.search import Options, SolrSearch


class ExtraSolrInterface(SolrInterface):
    """Extends the SolrInterface class so that it uses the ExtraSolrSearch
    class.
    """

    def __init__(self, *args, **kwargs):
        super(ExtraSolrInterface, self).__init__(*args, **kwargs)

    def query(self, *args, **kwargs):
        """
        :returns: SolrSearch -- A solrsearch.

        Build a solr query
        """
        # Change this line to hit our class instead of SolrSearch. All the rest
        # of this class is the same.
        q = ExtraSolrSearch(self)
        if len(args) + len(kwargs) > 0:
            return q.query(*args, **kwargs)
        else:
            return q


class ExtraSolrSearch(SolrSearch):
    """Base class for common search options management"""
    option_modules = ('query_obj', 'filter_obj', 'paginator',
                      'more_like_this', 'highlighter', 'faceter',
                      'sorter', 'facet_querier', 'field_limiter',
                      'extra')

    def _init_common_modules(self):
        super(ExtraSolrSearch, self)._init_common_modules()
        self.extra = ExtraOptions()

    def add_extra(self, **kwargs):
        newself = self.clone()
        newself.extra.update(kwargs)
        return newself

    def count(self):
        return self.add_extra(rows=0).execute().result.numFound


class ExtraOptions(Options):
    def __init__(self, original=None):
        if original is None:
            self.option_dict = {}
        else:
            self.option_dict = original.option_dict.copy()

    def update(self, extra_options):
        self.option_dict.update(extra_options)

    def options(self):
        return self.option_dict
