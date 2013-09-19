from datetime import datetime, timedelta
from alert import settings


def queryset_generator(queryset, chunksize=1000):
    """
    from: http://djangosnippets.org/snippets/1949/
    Iterate over a Django Queryset ordered by the primary key

    This method loads a maximum of chunksize (default: 1000) rows in its
    memory at the same time while django normally would load all rows in its
    memory. Using the iterator() method only causes it to not preload all the
    classes.

    Note that the implementation of the iterator does not support ordered query
    sets.
    """
    if queryset.count() == 0:
        return
    if settings.DEVELOPMENT:
        chunksize = 5

    documentUUID = queryset.order_by('pk')[0].documentUUID
    # Decrement document ID for use with 'greater than' filter
    if documentUUID > 0:
        documentUUID -= 1
    last_pk = queryset.order_by('-pk')[0].documentUUID
    queryset = queryset.order_by('pk')
    while documentUUID < last_pk:
        for row in queryset.filter(documentUUID__gt=documentUUID)[:chunksize]:
            documentUUID = row.documentUUID
            yield row


def queryset_generator_by_date(queryset, date_field, start_date, end_date, chunksize=7):
    """
    Takes a queryset and chunks it by date. Useful if sorting by pk isn't
    needed. For large querysets, such sorting can be very expensive.

    date_field is the name of the date field that should be used for chunking.
    This field should have db_index=True in your model.

    Chunksize should be given in days, and start and end dates should be provided
    as dates.
    """
    chunksize = timedelta(chunksize)
    bottom_date = start_date
    top_date = bottom_date + chunksize - timedelta(1)
    while bottom_date <= end_date:
        if top_date > end_date:
            # Last iteration
            top_date = end_date
        keywords = {'%s__gte' % date_field: bottom_date,
                    '%s__lte' % date_field: top_date}
        bottom_date = bottom_date + chunksize
        top_date = top_date + chunksize
        for row in queryset.filter(**keywords):
            yield row
