from .base import *  # noqa: F401,F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "agent": "10000/minute",
}
