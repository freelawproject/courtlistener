def fetchall_as_dict(cursor):
    """Return all rows from a cursor as a dict.

    From: https://docs.djangoproject.com/en/3.0/topics/db/sql/#executing-custom-sql-directly

    :param cursor: The cursor that you wish to query
    """
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
