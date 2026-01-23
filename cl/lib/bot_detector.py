from django.http import HttpRequest


def base_bot_matcher(
    request: HttpRequest,
    known_bots: list[str],
) -> bool:
    """Detect if a request's user agent is in a list of user agents

    Matching is done by seeing if any of the items in the list of known_bots
    is in the user agent for the request provided.
    """
    ua = request.headers.get("user-agent", "Testing U-A")
    for bot in known_bots:
        if bot in ua.lower():
            return True
    return False


def is_bot(request: HttpRequest) -> bool:
    """Checks if the thing making a request is a crawler."""
    known_bots = [
        "baiduspider",
        "bingbot",
        "dotbot",
        "googlebot",
        "kaloogabot",
        "ia_archiver",
        "msnbot",
        "slurp",
        "speedy spider",
        "teoma",
        "twiceler",
        "yandexbot",
        "yodaobot",
    ]
    return base_bot_matcher(request, known_bots)
