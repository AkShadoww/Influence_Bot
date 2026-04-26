"""
Per-brand Slack post routing.

When a brand has completed the OAuth install flow (see services/slack_oauth.py),
notifications about that brand's campaigns should go to that workspace + the
channel they picked, not to the team's internal channels. This module looks up
the right (token, channel) for a given brand name.

Match key: a slugified brand name. Both the install link slug
(`/slack/install/<slug>`) and the campaign's `brandName` field are passed
through `slugify_brand()` before lookup, so e.g. "Acme Inc" matches an install
link minted as `/slack/install/acme`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from slack_sdk import WebClient

from models.models import SessionLocal, SlackInstallation

logger = logging.getLogger(__name__)


@dataclass
class BrandRoute:
    client: WebClient
    channel: str
    is_brand_install: bool  # True if routed to a brand's installed workspace


def slugify_brand(name: Optional[str]) -> str:
    """Lowercase, drop everything that isn't a-z0-9. Empty string for None."""
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


class BrandRouter:
    """
    Resolves (Slack client, channel) for a brand name.

    `default_client` is the team's shared bot client and is used as the
    fallback whenever a brand has not installed the bot in their workspace.
    """

    def __init__(self, default_client: WebClient):
        self.default_client = default_client

    def resolve(self, brand_name: Optional[str], fallback_channel: str) -> BrandRoute:
        slug = slugify_brand(brand_name)
        if slug:
            session = SessionLocal()
            try:
                install = (
                    session.query(SlackInstallation)
                    .filter_by(brand=slug)
                    .order_by(SlackInstallation.installed_at.desc())
                    .first()
                )
            finally:
                session.close()
            if install and install.bot_token and install.channel_id:
                logger.info(
                    "Routing brand=%s to installed workspace team=%s channel=%s",
                    slug, install.team_id, install.channel_id,
                )
                return BrandRoute(
                    client=WebClient(token=install.bot_token),
                    channel=install.channel_id,
                    is_brand_install=True,
                )

        return BrandRoute(
            client=self.default_client,
            channel=fallback_channel,
            is_brand_install=False,
        )
