import os
import tempfile

import environ
from zohocrmsdk.src.com.zoho.api.authenticator.store import FileStore
from zohocrmsdk.src.com.zoho.crm.api.dc import USDataCenter
from zohocrmsdk.src.com.zoho.crm.api.sdk_config import SDKConfig
from zohocrmsdk.src.com.zoho.crm.api.util.constants import Constants

env = environ.FileAwareEnv()
ZOHO_CLIENT_ID = env("ZOHO_CLIENT_ID", default="")
ZOHO_CLIENT_SECRET = env("ZOHO_CLIENT_SECRET", default="")
ZOHO_CRM_API_USER_EMAIL = env("ZOHO_CRM_API_USER_EMAIL", default="")
ZOHO_STORE = FileStore(
    file_path=os.path.join(tempfile.gettempdir(), Constants.TOKEN_FILE)
)
ZOHO_RESOURCE_PATH = tempfile.gettempdir()
ZOHO_ENV = USDataCenter.PRODUCTION()
ZOHO_CONFIG = SDKConfig(
    auto_refresh_fields=True,
    pick_list_validation=False,
    connect_timeout=env.int("ZOHO_CONNECT_TIMEOUT", default=30),
    read_timeout=env.int("ZOHO_READ_TIMEOUT", default=60),
)
