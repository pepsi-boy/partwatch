"""Deal alerts.

EmailSender sends over SMTP with Python's built-in smtplib (Gmail: port 587 with
STARTTLS and an app password). LogSender writes the alert to the logs instead.
It's used when SMTP isn't configured, e.g. on Render's free tier, which blocks
outbound SMTP ports.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.config import Settings, get_settings
from app.models import Deal, Part
from app.services import deals

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 15


def format_alert(part: Part, deal: Deal) -> tuple[str, str]:
    summary = deals.describe(deal.reason, deal.price, deal.percent_below, part.target_price)
    subject = f"{part.name} is {summary}"
    body = "\n".join(
        [
            f"{part.name} ({part.category.upper()}, Best Buy SKU {part.sku})",
            "",
            f"Current price:   ${deal.price}",
            f"30-day average:  ${deal.baseline_avg}",
            f"Below average:   {deal.percent_below}%",
            f"Your target:     ${part.target_price}" if part.target_price else "",
            "",
            f"https://www.bestbuy.com/site/{part.sku}.p?skuId={part.sku}",
        ]
    )
    return subject, body


class LogSender:
    channel = "log"

    def send(self, subject: str, body: str) -> None:
        logger.info("DEAL ALERT: %s", subject, extra={"alert_body": body})


class EmailSender:
    channel = "email"

    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, subject: str, body: str) -> None:
        s = self.settings
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = s.smtp_user
        msg["To"] = s.alert_email_to
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.starttls()
            smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)


def get_sender(settings: Settings | None = None) -> EmailSender | LogSender:
    settings = settings or get_settings()
    if settings.smtp_user and settings.smtp_password and settings.alert_email_to:
        return EmailSender(settings)
    return LogSender()
