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
            return campaigns

        except requests.RequestException as e:
            logger.error(f"Failed to fetch campaigns from ReelStats API: {e}")
            return []

    def get_all_creators(self) -> list[dict]:
        """
        Fetch all campaigns and flatten into a list of creator dicts,
        each enriched with campaign info.
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
