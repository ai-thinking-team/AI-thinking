from django.core.mail.backends.base import BaseEmailBackend


class DisabledEmailBackend(BaseEmailBackend):
    """Discard email while an environment explicitly disables email delivery."""

    def send_messages(self, email_messages):
        return 0
