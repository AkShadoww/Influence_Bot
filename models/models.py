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
    Text,
    DateTime,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

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
    email_sent = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "creator_username", "reminder_type",
            name="uq_deadline_reminder",
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


class ReviewSubmission(Base):
    """
    One row per review_submitted webhook. Stores context needed to respond to
    Approve / Request Changes button clicks, plus the Slack message coordinates
    so thread replies can be matched back to the review.
    """
    __tablename__ = "review_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_slug = Column(String(255), nullable=True)
    campaign_name = Column(String(255), nullable=True)
    brand_name = Column(String(255), nullable=True)
    creator_username = Column(String(255), nullable=False)
    creator_email = Column(String(255), nullable=True)
    video_link = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    slack_channel = Column(String(255), nullable=True)
    slack_ts = Column(String(255), nullable=True)

    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Decision state: NULL until the brand clicks a button.
    decision = Column(String(50), nullable=True)  # "approved" | "changes_requested"
    decision_feedback = Column(Text, nullable=True)
    decided_by_id = Column(String(255), nullable=True)
    decided_by_name = Column(String(255), nullable=True)
    decided_at = Column(DateTime, nullable=True)

    comments = relationship("ReviewComment", back_populates="review", cascade="all, delete-orphan")


class ReviewComment(Base):
    """Thread reply on a review message, captured so the creator can be looped in."""
    __tablename__ = "review_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    review_id = Column(Integer, ForeignKey("review_submissions.id"), nullable=False)
    slack_user_id = Column(String(255), nullable=True)
    slack_user_name = Column(String(255), nullable=True)
    slack_ts = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)
    emailed_to_creator = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    review = relationship("ReviewSubmission", back_populates="comments")

    __table_args__ = (
        UniqueConstraint("slack_ts", name="uq_review_comment_ts"),
    )


class PaymentRecord(Base):
    """Persistent record of 'Mark as Paid' clicks."""
    __tablename__ = "payment_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(255), nullable=True)
    creator_username = Column(String(255), nullable=False)
    marked_by_id = Column(String(255), nullable=True)
    marked_by_name = Column(String(255), nullable=True)
    marked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "creator_username",
            name="uq_payment_record",
        ),
    )
