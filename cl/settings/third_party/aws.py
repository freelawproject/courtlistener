import environ

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)


# S3
if DEVELOPMENT:
    AWS_ACCESS_KEY_ID = env("AWS_DEV_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_DEV_SECRET_ACCESS_KEY", default="")
else:
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")

AWS_STORAGE_BUCKET_NAME = env(
    "AWS_STORAGE_BUCKET_NAME", default="com-courtlistener-storage"
)
AWS_PRIVATE_STORAGE_BUCKET_NAME = env(
    "AWS_PRIVATE_STORAGE_BUCKET_NAME",
    default="com-courtlistener-private-storage",
)

AWS_S3_CUSTOM_DOMAIN = "storage.courtlistener.com"
AWS_DEFAULT_ACL = "public-read"
AWS_QUERYSTRING_AUTH = False
AWS_S3_MAX_MEMORY_SIZE = 16 * 1024 * 1024

if DEVELOPMENT:
    AWS_STORAGE_BUCKET_NAME = "dev-com-courtlistener-storage"
    AWS_PRIVATE_STORAGE_BUCKET_NAME = "dev-com-courtlistener-private-storage"
    AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"

# The scanning portal's private bucket. import_scanned_opinions reads the
# final XML of each approved opinion from it, with a read-only user of its
# own when the keys are set, else with the keys above.
SCANNING_BUCKET_NAME = env(
    "SCANNING_BUCKET_NAME",
    default=(
        "dev-com-courtlistener-scanning-private-storage"
        if DEVELOPMENT
        else "com-courtlistener-scanning-private-storage"
    ),
)
SCANNING_BUCKET_REGION = env("SCANNING_BUCKET_REGION", default="us-west-2")
SCANNING_AWS_ACCESS_KEY_ID = env("SCANNING_AWS_ACCESS_KEY_ID", default="")
SCANNING_AWS_SECRET_ACCESS_KEY = env(
    "SCANNING_AWS_SECRET_ACCESS_KEY", default=""
)


# Cloudfront
CLOUDFRONT_DOMAIN = env("CLOUDFRONT_DOMAIN", default="")
CLOUDFRONT_DISTRIBUTION_ID = env(
    "CLOUDFRONT_DISTRIBUTION_ID", default="E1ZASFI222UR2O"
)

AWS_LAMBDA_PROXY_URL = env("AWS_LAMBDA_PROXY_URL", default="")


# SES
AWS_SES_ACCESS_KEY_ID = env("AWS_SES_ACCESS_KEY_ID", default="")
AWS_SES_SECRET_ACCESS_KEY = env("AWS_SES_SECRET_ACCESS_KEY", default="")
