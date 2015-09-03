def reverse_endpoints_if_needed(start, end):
    """Make sure start date < end date, and flip if needed.

    The front end allows the user to put in the endpoints in whatever
    chronological order they prefer. This sorts them.
    """
    if start.date_filed < end.date_filed:
        return start, end
    else:
        return end, start
