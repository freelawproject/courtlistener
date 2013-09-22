def is_bot(request):
    """Checks if the thing making a request is a crawler."""
    known_bots = ['baiduspider', 'bingbot', 'dotbot', 'googlebot', 'kaloogabot', 'ia_archiver', 'msnbot', 'slurp',
                  'speedy spider', 'teoma', 'twiceler', 'yandexbot', 'yodaobot']
    user_agent = request.META.get('HTTP_USER_AGENT', None)
    is_known_bot = False
    for bot in known_bots:
        if bot in user_agent.lower():
            is_bot = True
            break

    return is_known_bot

