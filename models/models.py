from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from config import Config

Base = declarative_base()
engine = create_engine(Config.DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    poc_name = Column(String(255))
    poc_email = Column(String(255))
    slack_channel_id = Column(String(50))
    slack_user_id = Column(String(50))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    campaigns = relationship("Campaign", back_populates="brand")

    def __repr__(self):
        return f"<Brand {self.name}>"


class Creator(Base):
    __tablename__ = "creators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    instagram_handle = Column(String(255))
    instagram_id = Column(String(100))
    phone = Column(String(50))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    campaigns = relationship("Campaign", back_populates="creator")

    def __repr__(self):
        return f"<Creator {self.name} (@{self.instagram_handle})>"


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(Integer, ForeignKey("creators.id"), nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    deadline = Column(DateTime, nullable=False)
    post_type = Column(String(50), default="reel")  # reel, story, post
    status = Column(String(50), default="pending")
    # pending, video_submitted, under_review, approved, changes_requested,
    # posted, overdue
    has_posted = Column(Boolean, default=False)
    followup_count = Column(Integer, default=0)
    last_followup_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))

    creator = relationship("Creator", back_populates="campaigns")
    brand = relationship("Brand", back_populates="campaigns")
    video_submissions = relationship("VideoSubmission", back_populates="campaign")

    def __repr__(self):
        return f"<Campaign {self.creator.name} x {self.brand.name}>"


class VideoSubmission(Base):
    __tablename__ = "video_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    video_url = Column(Text, nullable=False)
    tally_submission_id = Column(String(255))
    review_status = Column(String(50), default="pending")
    # pending, sent_to_brand, approved, changes_requested
    reviewer_notes = Column(Text)
    slack_message_ts = Column(String(50))
    slack_channel_id = Column(String(50))
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = Column(DateTime)

    campaign = relationship("Campaign", back_populates="video_submissions")

    def __repr__(self):
        return f"<VideoSubmission campaign={self.campaign_id} status={self.review_status}>"
