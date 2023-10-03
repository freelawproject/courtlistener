import requests
from django.conf import settings
from scorched import SolrInterface
from scorched.exc import SolrError
from scorched.search import Options, SolrSearch


class ExtraSolrInterface(SolrInterface):
    """Extends the SolrInterface class so that it uses the ExtraSolrSearch
    class.
    """

    hl_fields = None

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

    def mlt_query(self, hl_fields, *args, **kwargs):
        """
        :returns: MoreLikeThisHighlightsSolrSearch -- A MoreLikeThis search with highlights.

        Build a solr MLT query
        """
        self.hl_fields = hl_fields
        q = MoreLikeThisHighlightsSolrSearch(self)

        if len(args) + len(kwargs) > 0:
            res = q.query(*args, **kwargs)
        else:
            res = q

        return res

    @classmethod
    def health_check(self) -> bool:
        try:
            response = requests.get(settings.SOLR_HOST)
            return response.status_code == 200
        except Exception as e:
            # print(f"Solr health check failed with error: {e}")
            # TODO: add logging
            return False


class ExtraSolrSearch(SolrSearch):
    """Base class for common search options management"""

    option_modules = (
        "query_obj",
        "filter_obj",
        "paginator",
        "more_like_this",
        "highlighter",
        "postings_highlighter",
        "faceter",
        "grouper",
        "sorter",
        "facet_querier",
        "debugger",
        "spellchecker",
        "requesthandler",
        "field_limiter",
        "parser",
        "pivoter",
        "facet_ranger",
        "term_vectors",
        "stat",
        "extra",
    )

    def _init_common_modules(self):
        super(ExtraSolrSearch, self)._init_common_modules()
        self.extra = ExtraOptions()

    def add_extra(self, **kwargs):
        newself = self.clone()
        newself.extra.update(kwargs)
        return newself

    _count = None

    def count(self):
        if self._count is None:
            # We haven't gotten the count yet. Get it. Clone self for this
            # query or else we'll set rows=0 for remainder.
            newself = self.clone()
            r = newself.add_extra(rows=0).execute()
            if r.groups:
                total = getattr(r.groups, r.group_field)["ngroups"]
            else:
                total = r.result.numFound

            # Set the cache
            self._count = total
        return self._count


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


class MoreLikeThisHighlightsSolrSearch(ExtraSolrSearch):
    """
    By default Solr MoreLikeThis queries do not support highlighting. Thus, we need to produce the highlights in Python.

    A MoreLikeThis search with highlight fields that are taken directly from search results
    """

    # Limit length of text field
    text_max_length = 500

    def execute(self, constructor=None):
        """
        Execute MLT-query and add highlighting to MLT search results.
        """

        try:
            ret = self.interface.mlt_search(**self.options())
        except TypeError:
            # Catch exception when seed is not available
            raise SolrError(
                "Seed documents for MoreLikeThis query do not exist"
            )

        # Add solr_highlighting to MLT results
        for doc in ret:
            # Initialize empty highlights dict
            doc["solr_highlights"] = {}

            # Copy each highlight field
            for field_name in self.interface.hl_fields:
                if field_name in doc:
                    if field_name == "text":  # max text length
                        doc[field_name] = doc[field_name][
                            : self.text_max_length
                        ]

                    doc["solr_highlights"][field_name] = [doc[field_name]]

        if constructor:
            ret = self.constructor(ret, constructor)

        return ret
