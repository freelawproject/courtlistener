import environ

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)

# S3
AWS_STORAGE_BUCKET_NAME = env(
    "AWS_STORAGE_BUCKET_NAME", default="com-courtlistener-storage"
)
AWS_S3_CUSTOM_DOMAIN = "storage.courtlistener.com"
AWS_DEFAULT_ACL = "public-read"
AWS_QUERYSTRING_AUTH = False
AWS_S3_MAX_MEMORY_SIZE = 16 * 1024 * 1024

if DEVELOPMENT:
    AWS_STORAGE_BUCKET_NAME = "dev-com-courtlistener-storage"
    AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"


# Cloudfront
CLOUDFRONT_DOMAIN = env("CLOUDFRONT_DOMAIN", default="")
CLOUDFRONT_DISTRIBUTION_ID = env(
    "CLOUDFRONT_DISTRIBUTION_ID", default="E1ZASFI222UR2O"
)

AWS_LAMBDA_PROXY_URL = env("AWS_LAMBDA_PROXY_URL", default="")


# SES
AWS_SES_ACCESS_KEY_ID = env("AWS_SES_ACCESS_KEY_ID", default="")
AWS_SES_SECRET_ACCESS_KEY = env("AWS_SES_SECRET_ACCESS_KEY", default="")
