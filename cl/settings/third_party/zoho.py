import environ
from zohocrmsdk.src.com.zoho.crm.api.dc import USDataCenter
from zohocrmsdk.src.com.zoho.crm.api.sdk_config import SDKConfig

env = environ.FileAwareEnv()
ZOHO_CLIENT_ID = env("ZOHO_CLIENT_ID", default="")
ZOHO_CLIENT_SECRET = env("ZOHO_CLIENT_SECRET", default="")
ZOHO_CRM_API_USER_EMAIL = env("ZOHO_CRM_API_USER_EMAIL", default="")
ZOHO_ENV = USDataCenter.PRODUCTION()
ZOHO_CONFIG = SDKConfig(
    auto_refresh_fields=True,
    pick_list_validation=False,
    connect_timeout=None,
    read_timeout=None,
)
