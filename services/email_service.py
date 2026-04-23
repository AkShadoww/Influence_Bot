"""
Email service for INFLUENCE Bot.
Sends professional emails from jennifer@useinfluence.xyz via SMTP.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum

from sqlalchemy.exc import IntegrityError

from config import Config
from models.models import SessionLocal, EmailLog

logger = logging.getLogger(__name__)


class EmailSendResult(str, Enum):
    SENT = "sent"
    ALREADY_SENT = "already_sent"
    FAILED = "failed"


class EmailService:
    def __init__(self):
        self.host = Config.SMTP_HOST
        self.port = Config.SMTP_PORT
        self.username = Config.SMTP_USERNAME
        self.password = Config.SMTP_PASSWORD
        self.from_name = Config.EMAIL_FROM_NAME

    def send_email(self, to_email: str, subject: str, body: str, cc: str = None) -> bool:
        """Send an email via SMTP."""
        try:
            msg = MIMEMultipart()
            msg["From"] = f"{self.from_name} <{self.username}>"
            msg["To"] = to_email
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc

            msg.attach(MIMEText(body, "plain"))

            recipients = [to_email]
            if cc:
                recipients.append(cc)

            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.username, recipients, msg.as_string())

            logger.info(f"Email sent to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def send_followup(self, to_email: str, template_data: dict) -> bool:
        """Send a follow-up email using a template dict with 'subject' and 'body'."""
        return self.send_email(to_email, template_data["subject"], template_data["body"])

    def send_approval_notification(self, to_email: str, template_data: dict) -> bool:
        """Send an approval/changes-requested email."""
        return self.send_email(to_email, template_data["subject"], template_data["body"])

    def send_followup_if_not_sent(
        self,
        to_email: str,
        template_data: dict,
        template_type: str,
        campaign_id: str,
        creator_username: str,
    ) -> EmailSendResult:
        """
        Idempotent follow-up send. Checks EmailLog first; only attempts SMTP
        if no row exists for (recipient, template_type, campaign, creator).
        On SMTP failure, no row is written — the next call will retry.
        """
        db = SessionLocal()
        try:
            existing = (
                db.query(EmailLog)
                .filter_by(
                    recipient_email=to_email,
                    template_type=template_type,
                    campaign_id=campaign_id,
                    creator_username=creator_username,
                )
                .first()
            )
            if existing:
                return EmailSendResult.ALREADY_SENT

            sent = self.send_followup(to_email, template_data)
            if not sent:
                return EmailSendResult.FAILED

            log = EmailLog(
                recipient_email=to_email,
                template_type=template_type,
                campaign_id=campaign_id,
                creator_username=creator_username,
            )
            db.add(log)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
            return EmailSendResult.SENT
        finally:
            db.close()
