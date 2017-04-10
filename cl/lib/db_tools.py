from datetime import timedelta

from django.conf import settings


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
    def get_attr_or_value(obj, key):
        """Get an attr of an object that's either a dict or a Django object"""
        try:
            return getattr(obj, key)
        except AttributeError:
            try:
                return obj.get(key)
            except KeyError:
                raise Exception("Unable to lookup key '%s' of item. Did you "
                                "forget to include it in a values query?" % key)

    # Make a query that doesn't do related fetching for optimization
    queryset = queryset.order_by('pk').prefetch_related(None)
    count = queryset.count()
    if count == 0:
        return

    lowest_pk = get_attr_or_value(queryset.order_by('pk')[0], 'id')
    highest_pk = get_attr_or_value(queryset.order_by('-pk')[0], 'id')
    lookup = 'pk__gte'
    while lowest_pk <= highest_pk:
        for row in queryset.filter(**{lookup: lowest_pk})[:chunksize]:
            yield row
            row_id = get_attr_or_value(row, 'id')
            if row_id == highest_pk:
                raise StopIteration
            else:
                # After first loop, tweak lookup to be a gt query. This allows
                # the loop to support single results, which require gte, and
                # n > 1 results, which require gte for subsequent iterations.
                lookup = 'pk__gt'
                lowest_pk = row_id


def queryset_generator_by_date(queryset, date_field, start_date, end_date,
                               chunksize=7):
    """
    Takes a queryset and chunks it by date. Useful if sorting by pk isn't
    needed. For large querysets, such sorting can be very expensive.

    date_field is the name of the date field that should be used for chunking.
    This field should have db_index=True in your model.

    Chunksize should be given in days, and start and end dates should be provided
    as dates.
    """
    chunksize = timedelta(days=chunksize)
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
