"""
Tally webhook integration for INFLUENCE Bot.
Processes form submissions from Tally (https://tally.so/dashboard) containing:
- Creator information (name, email, Instagram handle)
- Brand partnership details
- Video submissions for review
- Posting status updates (whether creator posted before deadline)
"""

import logging
from datetime import datetime, timezone

from models.models import SessionLocal, Creator, Brand, Campaign, VideoSubmission

logger = logging.getLogger(__name__)

# Map Tally field labels to our internal field names.
# Update these if you rename fields on the Tally form.
FIELD_MAP = {
    "creator_name": ["Creator Name", "creator_name", "Name"],
    "creator_email": ["Creator Email", "creator_email", "Email"],
    "instagram_handle": ["Instagram Handle", "instagram_handle", "Instagram"],
    "brand_name": ["Brand Name", "brand_name", "Brand"],
    "deadline": ["Deadline", "deadline", "Posting Deadline"],
    "video_url": ["Video URL", "video_url", "Video Link", "Draft Video"],
    "post_type": ["Post Type", "post_type", "Content Type"],
    "has_posted": ["Has Posted", "has_posted", "Posted?"],
    "brand_poc_name": ["Brand POC Name", "brand_poc_name", "POC Name"],
    "brand_poc_email": ["Brand POC Email", "brand_poc_email", "POC Email"],
}


def _extract_field(fields: list[dict], target_labels: list[str]) -> str | None:
    """Extract a field value from Tally's webhook payload by matching labels."""
    for field in fields:
        label = field.get("label", "")
        key = field.get("key", "")
        if label in target_labels or key in target_labels:
            value = field.get("value")
            if isinstance(value, list) and len(value) > 0:
                # File uploads come as a list of dicts with "url"
                if isinstance(value[0], dict) and "url" in value[0]:
                    return value[0]["url"]
                return value[0]
            return value
    return None


class TallyService:
    def process_webhook(self, payload: dict) -> dict:
        """
        Process an incoming Tally webhook payload.
        Returns a dict with extracted data and the action to take.
        """
        event_type = payload.get("eventType", "")
        data = payload.get("data", {})
        fields = data.get("fields", [])
        submission_id = data.get("submissionId", "")

        logger.info(f"Tally webhook received: event={event_type}, submission={submission_id}")

        extracted = {}
        for internal_name, labels in FIELD_MAP.items():
            extracted[internal_name] = _extract_field(fields, labels)

        # Determine the type of submission
        if extracted.get("video_url"):
            return self._handle_video_submission(extracted, submission_id)
        elif extracted.get("has_posted") is not None:
            return self._handle_posting_status(extracted, submission_id)
        else:
            return self._handle_new_campaign(extracted, submission_id)

    def _handle_video_submission(self, data: dict, submission_id: str) -> dict:
        """Handle a video submission from Tally for brand review."""
        db = SessionLocal()
        try:
            creator = self._get_or_create_creator(db, data)
            brand = self._get_or_create_brand(db, data)
            campaign = self._get_active_campaign(db, creator.id, brand.id)

            if not campaign:
                logger.warning(
                    f"No active campaign for creator={creator.name}, brand={brand.name}"
                )
                return {
                    "action": "error",
                    "message": f"No active campaign found for {creator.name} x {brand.name}",
                }

            video = VideoSubmission(
                campaign_id=campaign.id,
                video_url=data["video_url"],
                tally_submission_id=submission_id,
                review_status="pending",
            )
            db.add(video)
            campaign.status = "video_submitted"
            db.commit()
            db.refresh(video)

            logger.info(
                f"Video submission saved: id={video.id}, campaign={campaign.id}"
            )

            return {
                "action": "video_review",
                "video_id": video.id,
                "video_url": data["video_url"],
                "campaign_id": campaign.id,
                "creator_name": creator.name,
                "creator_email": creator.email,
                "creator_handle": creator.instagram_handle,
                "brand_name": brand.name,
                "brand_poc_name": brand.poc_name,
                "brand_poc_email": brand.poc_email,
                "brand_slack_channel": brand.slack_channel_id,
            }
        finally:
            db.close()

    def _handle_posting_status(self, data: dict, submission_id: str) -> dict:
        """Handle a posting status update (creator confirms they posted)."""
        db = SessionLocal()
        try:
            creator = self._get_or_create_creator(db, data)
            brand = self._get_or_create_brand(db, data)
            campaign = self._get_active_campaign(db, creator.id, brand.id)

            if not campaign:
                return {"action": "error", "message": "No active campaign found"}

            posted = str(data.get("has_posted", "")).lower() in (
                "yes", "true", "1", "posted",
            )
            campaign.has_posted = posted
            if posted:
                campaign.status = "posted"
            db.commit()

            return {
                "action": "posting_status",
                "posted": posted,
                "creator_name": creator.name,
                "brand_name": brand.name,
                "campaign_id": campaign.id,
            }
        finally:
            db.close()

    def _handle_new_campaign(self, data: dict, submission_id: str) -> dict:
        """Handle a new campaign setup from the Influence website via Tally."""
        db = SessionLocal()
        try:
            creator = self._get_or_create_creator(db, data)
            brand = self._get_or_create_brand(db, data)

            deadline_str = data.get("deadline", "")
            try:
                deadline = datetime.fromisoformat(deadline_str)
            except (ValueError, TypeError):
                deadline = datetime.now(timezone.utc)
                logger.warning(
                    f"Could not parse deadline '{deadline_str}', using current time"
                )

            campaign = Campaign(
                creator_id=creator.id,
                brand_id=brand.id,
                deadline=deadline,
                post_type=data.get("post_type", "reel"),
                status="pending",
            )
            db.add(campaign)
            db.commit()
            db.refresh(campaign)

            logger.info(f"New campaign created: id={campaign.id}")

            return {
                "action": "new_campaign",
                "campaign_id": campaign.id,
                "creator_name": creator.name,
                "creator_email": creator.email,
                "brand_name": brand.name,
                "deadline": deadline.strftime("%B %d, %Y"),
                "post_type": data.get("post_type", "reel"),
            }
        finally:
            db.close()

    def _get_or_create_creator(self, db, data: dict) -> Creator:
        email = data.get("creator_email", "")
        creator = db.query(Creator).filter_by(email=email).first()
        if not creator:
            creator = Creator(
                name=data.get("creator_name", "Creator"),
                email=email,
                instagram_handle=data.get("instagram_handle", ""),
            )
            db.add(creator)
            db.commit()
            db.refresh(creator)
        return creator

    def _get_or_create_brand(self, db, data: dict) -> Brand:
        name = data.get("brand_name", "")
        brand = db.query(Brand).filter_by(name=name).first()
        if not brand:
            brand = Brand(
                name=name,
                poc_name=data.get("brand_poc_name", ""),
                poc_email=data.get("brand_poc_email", ""),
            )
            db.add(brand)
            db.commit()
            db.refresh(brand)
        return brand

    def _get_active_campaign(self, db, creator_id: int, brand_id: int) -> Campaign | None:
        return (
            db.query(Campaign)
            .filter_by(creator_id=creator_id, brand_id=brand_id)
            .filter(Campaign.status.notin_(["posted"]))
            .order_by(Campaign.created_at.desc())
            .first()
        )
