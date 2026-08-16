import os

from django.core.exceptions import ImproperlyConfigured


TRUE_VALUES = {'1', 'true', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'no', 'off'}


def env_bool(name, default=False):
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    value = raw_value.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ImproperlyConfigured(
        f'{name} must be one of: 1, 0, true, false, yes, no, on, off.'
    )


def env_csv(name, default=()):
    raw_value = os.environ.get(name)
    if raw_value is None:
        return list(default)
    return [item.strip() for item in raw_value.split(',') if item.strip()]


def require_env(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise ImproperlyConfigured(f'{name} is required in production.')
    return value
