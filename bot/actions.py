"""
Slack interactive action handlers for INFLUENCE Bot.
Handles button clicks on notification messages.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def register_actions(app):
    """Register interactive component handlers on the Bolt app."""

    @app.action("mark_as_paid")
    def handle_mark_as_paid(ack, body, client, respond):
        """Update the original message to show the creator was marked paid."""
        ack()

        user = body.get("user", {})
        actor = user.get("username") or user.get("name") or user.get("id", "someone")

        action = (body.get("actions") or [{}])[0]
        value = action.get("value", "")
        try:
            campaign_id, creator_username = value.split("|", 1)
        except ValueError:
            campaign_id, creator_username = "", value

        channel_id = (body.get("channel") or {}).get("id")
        message = body.get("message") or {}
        ts = message.get("ts")
        original_blocks = message.get("blocks") or []

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Remove any actions blocks and any accessory buttons matching this creator,
        # then append a confirmation line.
        updated_blocks = []
        target_value = f"{campaign_id}|{creator_username}"
        for block in original_blocks:
            if block.get("type") == "actions":
                elements = block.get("elements") or []
                if any(
                    el.get("action_id") == "mark_as_paid"
                    and el.get("value") == target_value
                    for el in elements
                ):
                    continue
            if block.get("type") == "section" and "accessory" in block:
                accessory = block.get("accessory") or {}
                if (
                    accessory.get("action_id") == "mark_as_paid"
                    and accessory.get("value") == target_value
                ):
                    block = {k: v for k, v in block.items() if k != "accessory"}
            updated_blocks.append(block)

        updated_blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f":white_check_mark: *Marked as paid* by "
                            f"<@{user.get('id', '')}> — @{creator_username} "
                            f"({timestamp})"
                        ),
                    }
                ],
            }
        )

        if channel_id and ts:
            try:
                client.chat_update(
                    channel=channel_id,
                    ts=ts,
                    text=f"@{creator_username} marked as paid by @{actor}",
                    blocks=updated_blocks,
                )
            except Exception as e:
                logger.error(f"Failed to update message after mark_as_paid: {e}")
                respond(
                    text=(
                        f":white_check_mark: Marked @{creator_username} as paid "
                        f"(couldn't update the original message)."
                    ),
                    response_type="ephemeral",
                )

        logger.info(
            f"mark_as_paid: creator=@{creator_username} "
            f"campaign_id={campaign_id} actor=@{actor}"
        )
