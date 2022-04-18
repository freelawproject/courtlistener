import environ

env = environ.FileAwareEnv()

from ..django import TESTING

if TESTING:
    HCAPTCHA_SITEKEY = "10000000-ffff-ffff-ffff-000000000001"
    HCAPTCHA_SECRET = "0x0000000000000000000000000000000000000000"
else:
    HCAPTCHA_SITEKEY = env("HCAPTCHA_SITEKEY", default="")
    HCAPTCHA_SECRET = env("HCAPTCHA_SECRET", default="")
