import sys

import environ

env = environ.FileAwareEnv()


DOCKER_SELENIUM_HOST = env(
    "DOCKER_SELENIUM_HOST", default="http://cl-selenium:4444/wd/hub"
)
SELENIUM_HEADLESS = env.bool("SELENIUM_HEADLESS", default=False)

TESTING = "test" in sys.argv
TEST_RUNNER = "cl.tests.runner.TestRunner"
if TESTING:
    PAGINATION_COUNT = 10
    DEBUG = env.bool("TESTING_DEBUG", default=False)
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]
    CELERY_BROKER = "memory://"
