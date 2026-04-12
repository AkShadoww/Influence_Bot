"""
Instagram Graph API integration for INFLUENCE Bot.
Tracks creator stats (followers, recent post views/engagement).
Uses the Instagram Graph API via Meta's access token.
"""

import logging

import requests

from config import Config

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.instagram.com/v21.0"


class InstagramService:
    def __init__(self):
        self.access_token = Config.INSTAGRAM_ACCESS_TOKEN

    def get_user_profile(self, instagram_user_id: str) -> dict | None:
        """Fetch basic profile info for an Instagram user."""
        try:
            url = f"{GRAPH_API_BASE}/{instagram_user_id}"
            params = {
                "fields": "id,username,name,followers_count,media_count",
                "access_token": self.access_token,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Instagram profile fetched: @{data.get('username')}")
            return data
        except requests.RequestException as e:
            logger.error(f"Failed to fetch Instagram profile {instagram_user_id}: {e}")
            return None

    def get_recent_media(self, instagram_user_id: str, limit: int = 10) -> list[dict]:
        """Fetch recent media posts for a creator."""
        try:
            url = f"{GRAPH_API_BASE}/{instagram_user_id}/media"
            params = {
                "fields": "id,caption,media_type,timestamp,like_count,comments_count,"
                          "permalink",
                "limit": limit,
                "access_token": self.access_token,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except requests.RequestException as e:
            logger.error(f"Failed to fetch media for {instagram_user_id}: {e}")
            return []

    def get_media_insights(self, media_id: str) -> dict | None:
        """Fetch insights (views, reach, engagement) for a specific media post."""
        try:
            url = f"{GRAPH_API_BASE}/{media_id}/insights"
            params = {
                "metric": "impressions,reach,engagement,video_views",
                "access_token": self.access_token,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            insights = {}
            for item in data.get("data", []):
                insights[item["name"]] = item["values"][0]["value"]
            return insights
        except requests.RequestException as e:
            logger.error(f"Failed to fetch insights for media {media_id}: {e}")
            return None

    def check_creator_stats(self, instagram_user_id: str) -> dict:
        """
        Get a summary of a creator's current Instagram performance.
        Returns follower count, recent post count, and avg engagement.
        """
        profile = self.get_user_profile(instagram_user_id)
        if not profile:
            return {"error": "Could not fetch profile"}

        recent_media = self.get_recent_media(instagram_user_id, limit=5)

        total_likes = 0
        total_comments = 0
        for media in recent_media:
            total_likes += media.get("like_count", 0)
            total_comments += media.get("comments_count", 0)

        post_count = len(recent_media)
        avg_likes = total_likes / post_count if post_count > 0 else 0
        avg_comments = total_comments / post_count if post_count > 0 else 0

        return {
            "username": profile.get("username"),
            "name": profile.get("name"),
            "followers": profile.get("followers_count", 0),
            "total_posts": profile.get("media_count", 0),
            "recent_avg_likes": round(avg_likes, 1),
            "recent_avg_comments": round(avg_comments, 1),
            "recent_posts_analyzed": post_count,
        }
