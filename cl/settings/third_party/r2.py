import environ

env = environ.FileAwareEnv()

R2_ENDPOINT_URL = env(
    "R2_ENDPOINT_URL", default="https://your-default-endpoint.com"
)
R2_ACCESS_KEY_ID = env("R2_ACCESS_KEY_ID", default="")
R2_SECRET_ACCESS_KEY = env("R2_SECRET_ACCESS_KEY", default="")
R2_BUCKET_NAME = env("R2_BUCKET_NAME", default="your-default-bucket-name")
