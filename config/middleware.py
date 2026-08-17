from django.conf import settings


class IgnoreBrowserLanguageMiddleware:
    """Placed right before LocaleMiddleware in MIDDLEWARE.

    LocaleMiddleware (see django.utils.translation.get_language_from_request)
    picks a language in this order: the django_language cookie (set by the
    set_language view when a learner explicitly switches), then the
    browser's Accept-Language header, then LANGUAGE_CODE as a last resort.
    That means a browser sending "Accept-Language: ja" gets Japanese even
    for a first-time visitor who never chose anything — LANGUAGE_CODE='en'
    only kicks in when Accept-Language has no usable match at all, so it
    isn't really "the default" in practice.

    This strips Accept-Language before LocaleMiddleware sees it, but only
    when there's no django_language cookie yet — an explicit past
    selection must still win, so switching languages keeps working exactly
    as before.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.LANGUAGE_COOKIE_NAME not in request.COOKIES:
            request.META.pop('HTTP_ACCEPT_LANGUAGE', None)
        return self.get_response(request)
