"""
Video review and approval workflow for INFLUENCE Bot.

Flow:
1. Creator submits video via Tally form
2. Bot sends video to brand's Slack channel with Approve/Request Changes buttons
3. Brand POC clicks Approve or Request Changes
4. If Approved: Bot emails creator the good news + notifies team
5. If Changes Requested: Bot emails creator with feedback + notifies team
6. All status updates go to the Triage System and team channel
"""

import logging
from datetime import datetime, timezone

from slack_sdk import WebClient

from config import Config
from models.models import SessionLocal, VideoSubmission, Campaign
from services.email_service import EmailService
from templates.email_templates import (
    video_approved,
    video_changes_requested,
    video_submitted_for_review_brand,
)
from templates.slack_blocks import (
    build_video_review_blocks,
    build_approval_notification_blocks,
    build_changes_requested_blocks,
)

logger = logging.getLogger(__name__)


class ApprovalWorkflow:
    def __init__(self, slack_client: WebClient, email_service: EmailService):
        self.client = slack_client
        self.email_service = email_service

    def send_video_for_review(self, review_data: dict) -> bool:
        """
        Send a video to the brand's Slack channel for review.
        Called when Tally webhook delivers a video submission.
        """
        try:
            blocks = build_video_review_blocks(
                creator_name=review_data["creator_name"],
                creator_handle=review_data.get("creator_handle", ""),
                brand_name=review_data["brand_name"],
                video_url=review_data["video_url"],
                video_id=review_data["video_id"],
                campaign_id=review_data["campaign_id"],
            )

            # Send to brand's dedicated Slack channel (or team channel as fallback)
            channel = (
                review_data.get("brand_slack_channel") or Config.SLACK_TEAM_CHANNEL_ID
            )

            result = self.client.chat_postMessage(
                channel=channel,
                text=f"New video from {review_data['creator_name']} for {review_data['brand_name']} — ready for review!",
                blocks=blocks,
            )

            # Save the Slack message timestamp so we can update it later
            db = SessionLocal()
            try:
                video = db.query(VideoSubmission).get(review_data["video_id"])
                if video:
                    video.slack_message_ts = result["ts"]
                    video.slack_channel_id = channel
                    video.review_status = "sent_to_brand"
                    campaign = db.query(Campaign).get(review_data["campaign_id"])
                    if campaign:
                        campaign.status = "under_review"
                    db.commit()
            finally:
                db.close()

            # Notify the INFLUENCE team
            self.client.chat_postMessage(
                channel=Config.SLACK_TEAM_CHANNEL_ID,
                text=(
                    f":film_frames: *Video submitted for review*\n"
                    f"Creator: {review_data['creator_name']} "
                    f"(@{review_data.get('creator_handle', 'N/A')})\n"
                    f"Brand: {review_data['brand_name']}\n"
                    f"Video sent to brand channel for approval."
                ),
            )

            # Email the brand POC
            if review_data.get("brand_poc_email"):
                template = video_submitted_for_review_brand(
                    brand_poc_name=review_data.get("brand_poc_name", "Team"),
                    creator_name=review_data["creator_name"],
                    creator_handle=review_data.get("creator_handle", ""),
                    video_url=review_data["video_url"],
                )
                self.email_service.send_email(
                    to_email=review_data["brand_poc_email"],
                    subject=template["subject"],
                    body=template["body"],
                )

            logger.info(
                f"Video {review_data['video_id']} sent for review to channel {channel}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send video for review: {e}")
            return False

    def handle_approval(self, video_id: int, approver_user_id: str) -> dict:
        """Handle when a brand POC approves a video in Slack."""
        db = SessionLocal()
        try:
            video = db.query(VideoSubmission).get(video_id)
            if not video:
                return {"success": False, "message": "Video submission not found"}

            video.review_status = "approved"
            video.reviewed_at = datetime.now(timezone.utc)

            campaign = db.query(Campaign).get(video.campaign_id)
            if campaign:
                campaign.status = "approved"

            db.commit()

            creator = campaign.creator
            brand = campaign.brand

            # Email the creator the good news
            template = video_approved(
                creator_name=creator.name, brand_name=brand.name
            )
            self.email_service.send_email(
                to_email=creator.email,
                subject=template["subject"],
                body=template["body"],
            )

            # Notify the INFLUENCE team on Slack
            blocks = build_approval_notification_blocks(
                creator_name=creator.name,
                brand_name=brand.name,
                approver_user_id=approver_user_id,
            )
            self.client.chat_postMessage(
                channel=Config.SLACK_TEAM_CHANNEL_ID,
                text=f"Video approved! {creator.name} x {brand.name}",
                blocks=blocks,
            )

            # Update the original review message
            if video.slack_message_ts and video.slack_channel_id:
                self.client.chat_update(
                    channel=video.slack_channel_id,
                    ts=video.slack_message_ts,
                    text=f"APPROVED: Video from {creator.name} for {brand.name}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f":white_check_mark: *APPROVED* by <@{approver_user_id}>\n\n"
                                    f"*Creator:* {creator.name} (@{creator.instagram_handle})\n"
                                    f"*Brand:* {brand.name}\n"
                                    f"*Video:* {video.video_url}"
                                ),
                            },
                        }
                    ],
                )

            logger.info(f"Video {video_id} approved by {approver_user_id}")
            return {
                "success": True,
                "message": f"Video approved! Email sent to {creator.email}",
                "creator_email": creator.email,
            }

        finally:
            db.close()

    def handle_changes_requested(
        self, video_id: int, reviewer_user_id: str, feedback: str
    ) -> dict:
        """Handle when a brand POC requests changes to a video."""
        db = SessionLocal()
        try:
            video = db.query(VideoSubmission).get(video_id)
            if not video:
                return {"success": False, "message": "Video submission not found"}

            video.review_status = "changes_requested"
            video.reviewer_notes = feedback
            video.reviewed_at = datetime.now(timezone.utc)

            campaign = db.query(Campaign).get(video.campaign_id)
            if campaign:
                campaign.status = "changes_requested"

            db.commit()

            creator = campaign.creator
            brand = campaign.brand

            # Email the creator with feedback
            template = video_changes_requested(
                creator_name=creator.name,
                brand_name=brand.name,
                feedback=feedback,
            )
            self.email_service.send_email(
                to_email=creator.email,
                subject=template["subject"],
                body=template["body"],
            )

            # Notify the INFLUENCE team
            blocks = build_changes_requested_blocks(
                creator_name=creator.name,
                brand_name=brand.name,
                reviewer_user_id=reviewer_user_id,
                feedback=feedback,
            )
            self.client.chat_postMessage(
                channel=Config.SLACK_TEAM_CHANNEL_ID,
                text=f"Changes requested: {creator.name} x {brand.name}",
                blocks=blocks,
            )

            # Update the original review message
            if video.slack_message_ts and video.slack_channel_id:
                self.client.chat_update(
                    channel=video.slack_channel_id,
                    ts=video.slack_message_ts,
                    text=f"CHANGES REQUESTED: Video from {creator.name} for {brand.name}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f":pencil2: *CHANGES REQUESTED* by <@{reviewer_user_id}>\n\n"
                                    f"*Creator:* {creator.name} (@{creator.instagram_handle})\n"
                                    f"*Brand:* {brand.name}\n"
                                    f"*Feedback:* {feedback}"
                                ),
                            },
                        }
                    ],
                )

            logger.info(f"Changes requested for video {video_id}")
            return {
                "success": True,
                "message": f"Feedback sent to {creator.email}",
                "creator_email": creator.email,
            }

        finally:
            db.close()
