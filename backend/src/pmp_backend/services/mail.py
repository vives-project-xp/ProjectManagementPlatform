"""The only place that sends email (spec #68). The app keeps one mailer in
`app.state.mailer`; tests put `testing.FakeMailer` there instead."""

import smtplib
from email.message import EmailMessage
from typing import Protocol

from pmp_backend.settings import Settings


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None:
        """Send one plain-text email; raises when it can't be sent."""
        ...


def is_configured(settings: Settings) -> bool:
    return bool(settings.smtp_host)


class SmtpMailer:
    """SMTP with STARTTLS, e.g. Gmail with an app password."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(self, to: str, subject: str, body: str) -> None:
        settings = self._settings
        message = EmailMessage()
        message["From"] = settings.mail_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(message)
