"""
Webhook handler for ReelStats server events.
Processes review_submitted and video_links_submitted events.
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
    def __init__(self, slack_client: WebClient):
        self.client = slack_client
        self.channel = Config.SLACK_CHANNEL_ID

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
        else:
            logger.warning(f"Unknown webhook event type: {event_type}")
            return False

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
                channel=self.channel,
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
                channel=self.channel,
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
