from django.conf import settings

from cl.lib import search_utils
from cl.lib.sunburnt import sunburnt
from cl.search import forms


def get_object_list(request=None, **kwargs):
    """Perform the Solr work"""
    # Set the offset value
    paginator = kwargs['paginator']
    page_number = int(request.GET.get(paginator.page_query_param, 1))
    # Assume page_size = 20, then: 1 --> 0, 2 --> 19, 3 --> 39
    offset = max(0, (page_number - 1) * paginator.page_size - 1)
    limit = 20
    main_query = {'caller': 'api_search'}
    try:
        main_query.update(search_utils.build_main_query(
                kwargs['cd'],
                highlight='text'
        ))
        sl = SolrList(
                main_query=main_query,
                offset=offset,
                limit=limit,
                type=kwargs['cd']['type'],
        )
    except KeyError:
        sf = forms.SearchForm({'q': '*:*'})
        if sf.is_valid():
            main_query.update(search_utils.build_main_query(
                    sf.cleaned_data,
                    highlight='text',
            ))
        sl = SolrList(
                main_query=main_query,
                offset=offset,
                limit=limit,
        )
    return sl


class SolrList(object):
    """This implements a yielding list object that fetches items as they are
    queried.
    """

    def __init__(self, main_query, offset, limit, type=None, length=None):
        super(SolrList, self).__init__()
        self.main_query = main_query
        self.offset = offset
        self.limit = limit
        self.type = type
        self._item_cache = []
        if self.type == 'o':
            self.conn = sunburnt.SolrInterface(
                    settings.SOLR_OPINION_URL, mode='r')
        elif self.type == 'oa':
            self.conn = sunburnt.SolrInterface(
                    settings.SOLR_AUDIO_URL, mode='r')
        self._length = length

    def __len__(self):
        if self._length is None:
            mq = self.main_query.copy()  # local copy for manipulation
            mq['rows'] = 0  # For performance, we just want the count
            mq['caller'] = 'api_search_count'
            r = self.conn.raw_query(**mq).execute()
            self._length = r.result.numFound
        return self._length

    def __iter__(self):
        for item in range(0, len(self)):
            try:
                yield self._item_cache[item]
            except IndexError:
                yield self.__getitem__(item)

    def __getitem__(self, item):
        self.main_query['start'] = self.offset
        results_si = self.conn.raw_query(**self.main_query).execute()

        # Pull the text snippet up a level
        for result in results_si.result.docs:
            result['snippet'] = '&hellip;'.join(
                    result['solr_highlights']['text'])

        # Return the results as objects, not dicts.
        for result in results_si.result.docs:
            self._item_cache.append(SolrObject(initial=result))

        # Now, assuming our _item_cache is all set, we just get the item.
        if isinstance(item, slice):
            s = slice(item.start - int(self.offset),
                      item.stop - int(self.offset),
                      item.step)
            return self._item_cache[s]
        else:
            # Not slicing.
            try:
                return self._item_cache[item]
            except IndexError:
                # No results!
                return []

    def append(self, p_object):
        """Lightly override the append method so we get items duplicated in
        our cache.
        """
        self._item_cache.append(p_object)


class SolrObject(object):
    def __init__(self, initial=None):
        self.__dict__['_data'] = initial or {}

    def __getattr__(self, key):
        return self._data.get(key, None)

    def to_dict(self):
        return self._data
