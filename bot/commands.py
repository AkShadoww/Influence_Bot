"""
Slack slash command handlers for INFLUENCE Bot.

Commands:
  /influence-status   — View active campaign statuses
  /influence-followup — Manually trigger overdue campaign checks
  /influence-stats    — Check a creator's Instagram stats
  /influence-help     — Show all available commands
"""

import logging

from models.models import SessionLocal, Campaign
from templates.slack_blocks import build_campaign_status_blocks, build_creator_stats_blocks

logger = logging.getLogger(__name__)


def register_commands(app, scheduler_service, instagram_service):
    """Register all slash commands on the Bolt app."""

    @app.command("/influence-status")
    def handle_status(ack, respond):
        """Show the status of all active campaigns."""
        ack()
        db = SessionLocal()
        try:
            campaigns = (
                db.query(Campaign)
                .filter(Campaign.status != "posted")
                .order_by(Campaign.deadline.asc())
                .all()
            )

            campaign_data = []
            for c in campaigns:
                campaign_data.append(
                    {
                        "creator_name": c.creator.name,
                        "brand_name": c.brand.name,
                        "deadline": c.deadline.strftime("%b %d, %Y"),
                        "status": c.status,
                    }
                )

            blocks = build_campaign_status_blocks(campaign_data)
            respond(blocks=blocks, response_type="ephemeral")
        finally:
            db.close()

    @app.command("/influence-followup")
    def handle_followup(ack, respond):
        """Manually trigger the overdue campaign check."""
        ack()
        respond(
            text=":mag: Checking for overdue campaigns now...",
            response_type="ephemeral",
        )
        scheduler_service.check_overdue_campaigns()
        respond(
            text=":white_check_mark: Overdue campaign check complete. "
            "Any follow-up emails have been sent.",
            response_type="ephemeral",
        )

    @app.command("/influence-stats")
    def handle_stats(ack, respond, command):
        """Check a creator's Instagram stats."""
        ack()
        handle_text = (command.get("text") or "").strip().lstrip("@")

        if not handle_text:
            respond(
                text="Please provide an Instagram handle: `/influence-stats username`",
                response_type="ephemeral",
            )
            return

        respond(
            text=f":hourglass_flowing_sand: Fetching stats for @{handle_text}...",
            response_type="ephemeral",
        )

        stats = instagram_service.check_creator_stats(handle_text)
        blocks = build_creator_stats_blocks(stats)
        respond(blocks=blocks, response_type="ephemeral")

    @app.command("/influence-help")
    def handle_help(ack, respond):
        """Show all available bot commands."""
        ack()
        respond(
            text=(
                ":robot_face: *INFLUENCE Bot Commands*\n\n"
                "`/influence-status` — View all active campaign statuses\n"
                "`/influence-followup` — Manually check for overdue campaigns and send follow-ups\n"
                "`/influence-stats <handle>` — Check a creator's Instagram stats\n"
                "`/influence-help` — Show this help message\n\n"
                "*Automatic Features:*\n"
                "- Videos submitted via Tally are automatically sent to brand channels for review\n"
                "- Overdue posting deadlines trigger automatic follow-up emails\n"
                "- Brand approvals/feedback are emailed to creators automatically\n"
                "- Daily campaign summaries are posted every morning at 9 AM"
            ),
            response_type="ephemeral",
        )
