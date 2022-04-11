import environ

env = environ.FileAwareEnv()
DEVELOPMENT = env.bool("DEVELOPMENT", default=True)


#######
# AWS #
#######
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")

AWS_STORAGE_BUCKET_NAME = env(
    "AWS_STORAGE_BUCKET_NAME", default="com-courtlistener-storage"
)
AWS_S3_CUSTOM_DOMAIN = "storage.courtlistener.com"
AWS_DEFAULT_ACL = "public-read"
AWS_QUERYSTRING_AUTH = False

if DEVELOPMENT:
    AWS_STORAGE_BUCKET_NAME = "dev-com-courtlistener-storage"
    AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"

CLOUDFRONT_DOMAIN = ""
