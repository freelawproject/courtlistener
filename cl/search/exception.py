from elasticsearch.exceptions import SerializationError


class UnbalancedQuery(SerializationError):
    """Data passed in has unbalanced parenthesis"""
