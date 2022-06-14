import environ

env = environ.FileAwareEnv()

MOOSEND_API_KEY = env("MOOSEND_API_KEY", default="")
MOOSEND_API_URL = env("MOOSEND_API_URL", default="http://api.moosend.com/")
MOOSEND_DEFAULT_LIST_ID = env(
    "MOOSEND_DEFAULT_LIST_ID", default="1736771c-5457-4948-8b64-c44ba48c0b7e"
)
