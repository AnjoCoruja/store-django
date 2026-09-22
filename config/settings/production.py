from .base import *  # noqa: F401,F403

DEBUG = False

# Security hardening (validated when real domain is configured).
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "1") == "1"  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
