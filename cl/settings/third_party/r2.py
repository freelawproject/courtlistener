import environ

env = environ.FileAwareEnv()

CAP_R2_ENDPOINT_URL = env("CAP_R2_ENDPOINT_URL", default="")
CAP_R2_ACCESS_KEY_ID = env("CAP_R2_ACCESS_KEY_ID", default="")
CAP_R2_SECRET_ACCESS_KEY = env("CAP_R2_SECRET_ACCESS_KEY", default="")
CAP_R2_BUCKET_NAME = env("CAP_R2_BUCKET_NAME", default="cap-static")
