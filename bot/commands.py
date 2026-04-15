"""
Slack slash command handlers for INFLUENCE Bot.

Commands:
  /influence-status  — View active campaign statuses from the ReelStats API
  /influence-check   — Manually trigger all notification checks
  /influence-help    — Show all available commands
"""

import logging

logger = logging.getLogger(__name__)


def register_commands(app, scheduler_service, reelstats_api):
    """Register all slash commands on the Bolt app."""

    @app.command("/influence-status")
    def handle_status(ack, respond):
        """Show the status of active campaigns from the ReelStats API."""
        ack()
        respond(
            text=":hourglass_flowing_sand: Fetching campaigns from ReelStats...",
            response_type="ephemeral",
        )

        campaigns = reelstats_api.get_campaigns()
        if not campaigns:
            respond(
                text=":information_source: No active campaigns found.",
                response_type="ephemeral",
            )
            return

        lines = [":bar_chart: *Active Campaigns*\n"]
        for campaign in campaigns:
            name = campaign.get("name", "Unknown")
            brand = campaign.get("brandName", "")
            creator_count = len(campaign.get("creators", []))
            lines.append(
                f"• *{name}* ({brand}) — {creator_count} creator(s)"
            )

        respond(text="\n".join(lines), response_type="ephemeral")

    @app.command("/influence-check")
    def handle_check(ack, respond):
        """Manually trigger all notification checks."""
        ack()
        respond(
            text=":mag: Running all checks now (milestones, deliverables, deadlines, uploads)...",
            response_type="ephemeral",
        )
        scheduler_service.run_all_checks()
        respond(
            text=":white_check_mark: All checks complete. Notifications sent for any new items.",
            response_type="ephemeral",
        )

    @app.command("/influence-help")
    def handle_help(ack, respond):
        """Show all available bot commands."""
        ack()
        respond(
            text=(
                ":robot_face: *INFLUENCE Bot Commands*\n\n"
                "`/influence-status` — View active campaigns from the ReelStats API\n"
                "`/influence-check` — Manually run all notification checks\n"
                "`/influence-help` — Show this help message\n\n"
                "*Automatic Features:*\n"
                "- :trophy: View milestone alerts (250K, 500K, 1M, ...)\n"
                "- :white_check_mark: Payment flags when deliverables are complete\n"
                "- :calendar: Deadline reminders (3 days, 1 day, overdue) via Slack + email\n"
                "- :film_frames: Upload follow-ups when creators are behind schedule\n"
                "- :sunrise: Daily payment summary at 9 AM\n"
                "- :link: Real-time webhook notifications for reviews and video links"
            ),
            response_type="ephemeral",
        )
