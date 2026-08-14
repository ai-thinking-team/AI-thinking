from .settings import *  # noqa: F403


DEBUG = False
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
MIDDLEWARE = [
    middleware
    for middleware in MIDDLEWARE  # noqa: F405
    if middleware != 'whitenoise.middleware.WhiteNoiseMiddleware'
]
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.locmem.EmailBackend',
    }
}
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0

# Keep the test suite deterministic and offline.  The base settings module
# loads .env for local development, so explicitly clear every external AI and
# code-runner integration here instead of inheriting machine-specific values.
AI_PROVIDER_CLASS = ''
DEEPSEEK_API_KEY = ''
GEMINI_API_KEY = ''
CODE_RUNNER_URL = ''
CODE_RUNNER_GATEWAY_CLASS = ''
CODE_RUNNER_AUTH_TOKEN = ''
CODE_RUNNER_AUTOSTART = False
CODE_RUNNER_AUTOSTART_TIMEOUT_SECONDS = 0
