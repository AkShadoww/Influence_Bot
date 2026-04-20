"""
Database models for INFLUENCE Bot.
Tracks state to avoid duplicate notifications (milestones, alerts, reminders).
The ReelStats API is the source of truth for campaign data — these models
only persist notification state that the API doesn't track.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from config import Config

Base = declarative_base()
engine = create_engine(Config.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


class MilestoneAlert(Base):
    """Tracks which view milestones have been notified to avoid duplicates."""
    __tablename__ = "milestone_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(255), nullable=False)
    creator_username = Column(String(255), nullable=False)
    milestone_value = Column(Integer, nullable=False)  # e.g. 250000, 500000
    notified_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "creator_username", "milestone_value",
            name="uq_milestone_alert",
        ),
    )


class DeliverableAlert(Base):
    """Tracks which deliverable-complete alerts have been sent."""
    __tablename__ = "deliverable_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(255), nullable=False)
    creator_username = Column(String(255), nullable=False)
    notified_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "creator_username",
            name="uq_deliverable_alert",
        ),
    )


class DeadlineReminder(Base):
    """Tracks which deadline reminders have been sent (3 days, 1 day, overdue)."""
    __tablename__ = "deadline_reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(255), nullable=False)
    creator_username = Column(String(255), nullable=False)
    reminder_type = Column(String(50), nullable=False)  # "3_days", "1_day", "overdue"
    notified_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # Deprecated: email dedup now lives in the EmailLog table.
    email_sent = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "creator_username", "reminder_type",
            name="uq_deadline_reminder",
        ),
    )


class EmailLog(Base):
    """Tracks which follow-up emails have been successfully sent (dedup)."""
    __tablename__ = "email_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recipient_email = Column(String(320), nullable=False)
    template_type = Column(String(64), nullable=False)
    campaign_id = Column(String(255), nullable=False)
    creator_username = Column(String(255), nullable=False)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint(
            "recipient_email", "template_type",
            "campaign_id", "creator_username",
            name="uq_email_log",
        ),
    )


class UploadFollowup(Base):
    """Tracks upload follow-up reminders sent within the 5-day window."""
    __tablename__ = "upload_followups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(255), nullable=False)
    creator_username = Column(String(255), nullable=False)
    notified_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "creator_username",
            name="uq_upload_followup",
        ),
    )
