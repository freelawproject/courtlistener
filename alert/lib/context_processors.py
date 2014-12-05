from django.conf import settings


def inject_settings(request):
    return {
        'DEBUG': settings.DEBUG
    }
