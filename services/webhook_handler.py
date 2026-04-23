"""
Webhook handler for ReelStats server events.

Existing events (immediate Slack messages):
- review_submitted
- video_links_submitted

Live-data events (drive scheduler checks with zero polling delay):
- views_updated
- deliverables_updated
- deadline_check
- creator_updated
"""

import logging

from slack_sdk import WebClient

from config import Config
from templates.slack_blocks import (
    build_review_submitted_blocks,
    build_video_links_submitted_blocks,
)

logger = logging.getLogger(__name__)


class WebhookHandler:
    def __init__(self, slack_client: WebClient, scheduler_service=None):
        self.client = slack_client
        self.scheduler = scheduler_service

    def handle_event(self, payload: dict) -> bool:
        """Route an incoming webhook event to the appropriate handler."""
        event_type = payload.get("event")

        # Respect TEST_CAMPAIGN_NAME: drop webhooks for other campaigns.
        test_campaign_name = Config.TEST_CAMPAIGN_NAME
        if test_campaign_name:
            campaign_name = payload.get("campaign", {}).get("name")
            if campaign_name != test_campaign_name:
                logger.info(
                    f"Dropping webhook '{event_type}' for '{campaign_name}' "
                    f"(TEST_CAMPAIGN_NAME='{test_campaign_name}')"
                )
                return True

        if event_type == "review_submitted":
            return self._handle_review_submitted(payload)
        elif event_type == "video_links_submitted":
            return self._handle_video_links_submitted(payload)
        elif event_type == "views_updated":
            return self._run_checks(payload, ["milestones"])
        elif event_type == "deliverables_updated":
            return self._run_checks(payload, ["deliverables", "upload_followup"])
        elif event_type == "deadline_check":
            return self._run_checks(payload, ["deadline", "upload_followup"])
        elif event_type == "creator_updated":
            return self._run_checks(
                payload,
                ["milestones", "deliverables", "deadline", "upload_followup"],
            )
        else:
            logger.warning(f"Unknown webhook event type: {event_type}")
            return False

    # ------------------------------------------------------------------
    # Existing handlers
    # ------------------------------------------------------------------
    def _handle_review_submitted(self, payload: dict) -> bool:
        """Handle when a creator submits a video for review."""
        try:
            campaign = payload.get("campaign", {})
            creator = payload.get("creator", {})
            review = payload.get("review", {})

            blocks = build_review_submitted_blocks(
                creator_username=creator.get("username", "Unknown"),
                campaign_name=campaign.get("name", "Unknown Campaign"),
                brand_name=campaign.get("brandName", ""),
                video_link=review.get("videoLink", ""),
                notes=review.get("notes", ""),
            )

            self.client.chat_postMessage(
                channel=Config.SLACK_CHANNEL_REVIEWS,
                text=f"New review submitted by @{creator.get('username')} for {campaign.get('name')}",
                blocks=blocks,
            )

            logger.info(
                f"Review submitted notification sent: "
                f"@{creator.get('username')} for {campaign.get('name')}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to handle review_submitted: {e}")
            return False

    def _handle_video_links_submitted(self, payload: dict) -> bool:
        """Handle when a creator submits video links (posted content)."""
        try:
            campaign = payload.get("campaign", {})
            creator = payload.get("creator", {})
            video = payload.get("video", {})

            links = []
            for platform in ("instagram", "tiktok", "youtube"):
                url = video.get(platform)
                if url:
                    links.append({"platform": platform.capitalize(), "url": url})

            blocks = build_video_links_submitted_blocks(
                creator_username=creator.get("username", "Unknown"),
                campaign_name=campaign.get("name", "Unknown Campaign"),
                brand_name=campaign.get("brandName", ""),
                video_title=video.get("title", ""),
                links=links,
            )

            self.client.chat_postMessage(
                channel=Config.SLACK_CHANNEL_UPLOADS,
                text=f"Video links submitted by @{creator.get('username')} for {campaign.get('name')}",
                blocks=blocks,
            )

            logger.info(
                f"Video links submitted notification sent: "
                f"@{creator.get('username')} for {campaign.get('name')}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to handle video_links_submitted: {e}")
            return False

    # ------------------------------------------------------------------
    # Live-data handlers
    # ------------------------------------------------------------------
    def _run_checks(self, payload: dict, checks: list[str]) -> bool:
        """Run the named per-creator scheduler checks against the payload."""
        if self.scheduler is None:
            logger.error("No scheduler wired into WebhookHandler; cannot run checks")
            return False

        creator = self._flatten_creator(payload)
        if not creator.get("username") or not creator.get("campaign_id"):
            logger.warning(
                f"Live-data webhook missing username/campaign_id: {payload!r}"
            )
            return False

        try:
            if "milestones" in checks:
                self.scheduler.check_milestones_for(creator)
            if "deliverables" in checks:
                self.scheduler.check_deliverables_complete_for(creator)
            if "deadline" in checks:
                self.scheduler.check_deadline_reminder_for(creator)
            if "upload_followup" in checks:
                self.scheduler.check_upload_followup_for(creator)
            return True
        except Exception as e:
            logger.error(
                f"Failed running {checks} for @{creator.get('username')}: {e}"
            )
            return False

    @staticmethod
    def _flatten_creator(payload: dict) -> dict:
        """Normalize a webhook payload into the scheduler's flat creator dict."""
        campaign = payload.get("campaign", {}) or {}
        creator = payload.get("creator", {}) or {}
        return {
            **creator,
            "campaign_id": campaign.get("id", ""),
            "campaign_name": campaign.get("name", ""),
            "brand_name": campaign.get("brandName", ""),
            "campaign_slug": campaign.get("slug", ""),
        }
