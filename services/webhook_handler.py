"""
Webhook handler for ReelStats server events.
Processes review_submitted and video_links_submitted events.
"""

import logging

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

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
        if not self.channel:
            logger.error(
                "SLACK_CHANNEL_ID is not set — webhook notifications will fail. "
                "Set the SLACK_CHANNEL_ID environment variable to a valid channel ID."
            )
        if not Config.SLACK_BOT_TOKEN:
            logger.error(
                "SLACK_BOT_TOKEN is not set — webhook notifications will fail. "
                "Set the SLACK_BOT_TOKEN environment variable."
            )

    def _post_to_slack(self, text: str, blocks: list[dict], event_label: str) -> bool:
        """Post a message to Slack, distinguishing config vs. API errors."""
        if not self.channel:
            logger.error(
                f"Cannot post {event_label}: SLACK_CHANNEL_ID is not configured."
            )
            return False

        try:
            response = self.client.chat_postMessage(
                channel=self.channel,
                text=text,
                blocks=blocks,
            )
            if not response.get("ok"):
                logger.error(
                    f"Slack API returned non-ok for {event_label}: {response.data}"
                )
                return False
            return True
        except SlackApiError as e:
            err = e.response.get("error") if e.response else str(e)
            logger.error(
                f"Slack API error posting {event_label} to channel "
                f"{self.channel}: {err}"
            )
            return False

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

            username = creator.get("username") or "Unknown"
            campaign_name = campaign.get("name") or "Unknown Campaign"
            # ReelStats sends videoLink (camelCase); fall back to video_link.
            video_link = review.get("videoLink") or review.get("video_link") or ""

            if not video_link:
                logger.warning(
                    f"review_submitted payload for @{username} on "
                    f"{campaign_name} has no videoLink field"
                )

            blocks = build_review_submitted_blocks(
                creator_username=username,
                campaign_name=campaign_name,
                brand_name=campaign.get("brandName") or campaign.get("brand_name") or "",
                video_link=video_link,
                notes=review.get("notes", ""),
            )

            posted = self._post_to_slack(
                text=f"New review submitted by @{username} for {campaign_name}",
                blocks=blocks,
                event_label="review_submitted",
            )
            if posted:
                logger.info(
                    f"Review submitted notification sent: "
                    f"@{username} for {campaign_name} (link={video_link or 'none'})"
                )
            return posted

        except Exception as e:
            logger.exception(f"Failed to handle review_submitted: {e}")
            return False

    def _handle_video_links_submitted(self, payload: dict) -> bool:
        """Handle when a creator submits video links (posted content)."""
        try:
            campaign = payload.get("campaign", {})
            creator = payload.get("creator", {})
            video = payload.get("video", {})

            username = creator.get("username") or "Unknown"
            campaign_name = campaign.get("name") or "Unknown Campaign"

            links = []
            for platform in ("instagram", "tiktok", "youtube"):
                url = video.get(platform)
                if url:
                    links.append({"platform": platform.capitalize(), "url": url})

            if not links:
                logger.warning(
                    f"video_links_submitted payload for @{username} on "
                    f"{campaign_name} contains no platform URLs"
                )

            blocks = build_video_links_submitted_blocks(
                creator_username=username,
                campaign_name=campaign_name,
                brand_name=campaign.get("brandName") or campaign.get("brand_name") or "",
                video_title=video.get("title", ""),
                links=links,
            )

            posted = self._post_to_slack(
                text=f"Video links submitted by @{username} for {campaign_name}",
                blocks=blocks,
                event_label="video_links_submitted",
            )
            if posted:
                logger.info(
                    f"Video links submitted notification sent: "
                    f"@{username} for {campaign_name} "
                    f"(platforms={[l['platform'] for l in links]})"
                )
            return posted

        except Exception as e:
            logger.exception(f"Failed to handle video_links_submitted: {e}")
            return False
