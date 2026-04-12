"""
Slack event handlers for INFLUENCE Bot.
Handles messages, app mentions, and team join events.
"""

import logging

logger = logging.getLogger(__name__)


def register_event_handlers(app, approval_workflow, scheduler_service):
    """Register all Slack event listeners on the Bolt app."""

    @app.event("app_mention")
    def handle_app_mention(event, say):
        """When the bot is @mentioned, respond with a helpful message."""
        user = event.get("user")
        say(
            f"Hey <@{user}>! :wave: I'm the *INFLUENCE Bot*.\n\n"
            f"Here's what I can do:\n"
            f"- `/influence-status` — View all campaign statuses\n"
            f"- `/influence-followup` — Trigger a manual follow-up check\n"
            f"- `/influence-stats <instagram_handle>` — Check creator Instagram stats\n"
            f"- `/influence-help` — See all available commands\n\n"
            f"I also automatically:\n"
            f"- Send videos to brands for review when submitted via Tally\n"
            f"- Send follow-up emails for overdue posts\n"
            f"- Notify the team on approvals and feedback"
        )

    @app.event("message")
    def handle_message(event, say):
        """
        Handle incoming messages. Filter out bot messages to avoid loops.
        This handler captures general messages; specific workflows
        are triggered via webhooks and slash commands.
        """
        # Ignore bot messages and message changes/deletions
        if event.get("bot_id") or event.get("subtype"):
            return

        text = (event.get("text") or "").lower()

        # Respond to common keywords with helpful guidance
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
                    f"I'm the *INFLUENCE Bot* — I help manage creator campaigns, "
                    f"video approvals, and automated follow-ups.\n\n"
                    f"Type `/influence-help` in any channel to see what I can do!"
                ),
            )
