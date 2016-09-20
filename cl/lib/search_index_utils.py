from datetime import date, datetime, time


def solr_list(m2m_list, field):
    new_list = []
    for obj in m2m_list:
        obj = getattr(obj, field)
        if obj is None:
            continue
        if isinstance(obj, date):
            obj = datetime.combine(obj, time())
        new_list.append(obj)
    return new_list


class InvalidDocumentError(Exception):
    """The document could not be formed"""
    def __init__(self, message):
        Exception.__init__(self, message)


# Used to nuke null and control characters.
null_map = dict.fromkeys(range(0, 10) + range(11, 13) + range(14, 32))
