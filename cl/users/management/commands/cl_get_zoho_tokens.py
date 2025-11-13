from django.conf import settings
from django.core.cache import cache
from zohocrmsdk.src.com.zoho.api.authenticator.oauth_token import OAuthToken
from zohocrmsdk.src.com.zoho.crm.api.initializer import Initializer

from cl.lib.command_utils import VerboseCommand
from cl.lib.zoho import get_zoho_cache_key


class Command(VerboseCommand):
    help = "Command to manually get the ZOHO refresh token"

    def add_arguments(self, parser):
        parser.add_argument(
            "--grant-token",
            type=str,
            help="Notify users with unconfirmed accounts older than five days, "
            "and delete orphaned profiles.",
        )

    def handle(self, *args, **options):
        super().handle(*args, **options)
        self.options = options
        grant_token = options["grant_token"]
        Initializer.initialize(
            environment=settings.ZOHO_ENV,
            token=OAuthToken(
                client_id=settings.ZOHO_CLIENT_ID,
                client_secret=settings.ZOHO_CLIENT_SECRET,
                grant_token=grant_token,
            ),
            sdk_config=settings.ZOHO_CONFIG,
            store=settings.ZOHO_STORE,
            resource_path=settings.ZOHO_RESOURCE_PATH,
        )
        init = Initializer.get_initializer()
        token = init.token.get_refresh_token()
        cache.set(f"{get_zoho_cache_key()}:refresh", token, timeout=None)
