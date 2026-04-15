"""
Slack event handlers for INFLUENCE Bot.
Handles messages, app mentions, and team join events.
"""

import logging

logger = logging.getLogger(__name__)


def register_event_handlers(app):
    """Register all Slack event listeners on the Bolt app."""

    @app.event("app_mention")
    def handle_app_mention(event, say):
        """When the bot is @mentioned, respond with a helpful message."""
        user = event.get("user")
        say(
            f"Hey <@{user}>! :wave: I'm the *INFLUENCE Bot*.\n\n"
            f"Here's what I can do:\n"
            f"- `/influence-status` — View active campaign statuses\n"
            f"- `/influence-check` — Manually run all notification checks\n"
            f"- `/influence-help` — See all available commands\n\n"
            f"I also automatically:\n"
            f"- Send milestone alerts when creators hit view targets\n"
            f"- Flag creators for payment when deliverables are complete\n"
            f"- Send deadline reminders (3 days, 1 day, overdue)\n"
            f"- Post a daily payment summary at 9 AM"
        )

    @app.event("message")
    def handle_message(event, say):
        """
        Handle incoming messages. Filter out bot messages to avoid loops.
        """
        if event.get("bot_id") or event.get("subtype"):
            return

        text = (event.get("text") or "").lower()

        if "help" in text and "influence" in text:
            say(
                "Need help? Try one of these commands:\n"
                "- `/influence-status` — Campaign overview\n"
                "- `/influence-help` — Full command list"
            )

    @app.event("team_join")
    def handle_team_join(event, say):
        """Welcome new team members."""
        user_id = event.get("user", {}).get("id", "")
        if user_id:
            app.client.chat_postMessage(
                channel=user_id,
                text=(
                    f"Welcome to the INFLUENCE team! :tada:\n\n"
                    f"I'm the *INFLUENCE Bot* — I help track creator campaigns, "
                    f"view milestones, deadlines, and payment readiness.\n\n"
                    f"Type `/influence-help` in any channel to see what I can do!"
                ),
            )
