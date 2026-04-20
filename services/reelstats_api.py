"""
ReelStats API client for INFLUENCE Bot.
Polls GET /api/bot/campaigns for campaign data.
"""

import logging

import requests

from config import Config

logger = logging.getLogger(__name__)


class ReelStatsAPI:
    def __init__(self):
        self.base_url = Config.REELSTATS_API_URL.rstrip("/")
        self.token = Config.BOT_TOKEN
        self.session = requests.Session()
        self.session.headers.update({
            "x-bot-token": self.token,
            "Content-Type": "application/json",
        })

    def get_campaigns(self, campaign_id: str = None, creator: str = None) -> list[dict]:
        """
        Fetch all campaigns from the ReelStats API.
        Optionally filter by campaign_id or creator username.

        If Config.TEST_CAMPAIGN_NAME is set, the returned list is also
        filtered to only that campaign by exact name match.
        """
        try:
            url = f"{self.base_url}/api/bot/campaigns"
            params = {}
            if campaign_id:
                params["campaign"] = campaign_id
            if creator:
                params["creator"] = creator

            resp = self.session.get(url, params=params, timeout=30)

            if resp.status_code == 401:
                logger.error("ReelStats API: Invalid or missing BOT_TOKEN")
                return []
            if resp.status_code == 503:
                logger.error("ReelStats API: BOT_TOKEN not configured on server")
                return []

            resp.raise_for_status()
            data = resp.json()
            campaigns = data.get("campaigns", [])
            logger.info(f"Fetched {len(campaigns)} campaigns from ReelStats API")

            test_campaign_name = Config.TEST_CAMPAIGN_NAME
            if test_campaign_name:
                before = len(campaigns)
                campaigns = [
                    c for c in campaigns if c.get("name") == test_campaign_name
                ]
                logger.info(
                    f"TEST_CAMPAIGN_NAME='{test_campaign_name}' set: "
                    f"filtered {before} -> {len(campaigns)} campaign(s)"
                )

            return campaigns

        except requests.RequestException as e:
            logger.error(f"Failed to fetch campaigns from ReelStats API: {e}")
            return []

    def get_all_creators(self) -> list[dict]:
        """
        Fetch all campaigns and flatten into a list of creator dicts,
        each enriched with campaign info. Respects Config.TEST_CAMPAIGN_NAME
        via get_campaigns().
        """
        campaigns = self.get_campaigns()
        creators = []
        for campaign in campaigns:
            for creator in campaign.get("creators", []):
                creators.append({
                    **creator,
                    "campaign_id": campaign["id"],
                    "campaign_name": campaign["name"],
                    "brand_name": campaign.get("brandName", ""),
                    "campaign_slug": campaign.get("slug", ""),
                })
        return creators
