from django.http import HttpRequest


def is_ajax(request: HttpRequest) -> bool:
    """Return whether the request was made with Ajax

    Django 3.1 deprecated this function because browser fetch() requests don't
    always send it. It was a jQuery thing, apparently, but then it just kind of
    became a de facto standard, but now it's being slowly purged.

    :param request: The HttpRequest from the user.
    :return: True if ajax, else False
    """
    return request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
