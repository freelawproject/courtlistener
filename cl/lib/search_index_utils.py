from datetime import date

from cl.lib.date_time import midnight_pt


def solr_list(m2m_list, field):
    new_list = []
    for obj in m2m_list:
        obj = getattr(obj, field)
        if obj is None:
            continue
        if isinstance(obj, date):
            obj = midnight_pt(obj)
        new_list.append(obj)
    return new_list


class InvalidDocumentError(Exception):
    """The document could not be formed"""

    def __init__(self, message):
        Exception.__init__(self, message)


# Used to nuke null and control characters.
null_map = dict.fromkeys(
    list(range(0, 10)) + list(range(11, 13)) + list(range(14, 32))
)


def normalize_search_dicts(d):
    """Prepare search dicts for indexing by solr.

    1. Remove any kv from a dictionary if v is None

       This is needed to send dictionaries to Scorched, instead of
       sending objects, and should provide a performance improvement. If you try
       to send None values to integer fields (for example), things break, b/c
       integer fields shouldn't be getting None values. Fair 'nuf.

    2. Convert any sets to lists.

       This is needed because sets aren't JSON serializable, but they're
       convenient to use when building up a search object.
    """
    new_dict = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, set):
            new_dict[k] = list(v)
        else:
            new_dict[k] = v
    return new_dict
