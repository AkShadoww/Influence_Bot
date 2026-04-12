"""
Slack Block Kit message templates for INFLUENCE Bot.
These build rich, interactive messages for the Slack workspace.
"""

import json


def build_video_review_blocks(
    creator_name: str,
    creator_handle: str,
    brand_name: str,
    video_url: str,
    video_id: int,
    campaign_id: int,
) -> list[dict]:
    """Build the video review message with Approve / Request Changes buttons."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":film_frames: New Video Ready for Review",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Creator:*\n{creator_name} (@{creator_handle})",
                },
                {"type": "mrkdwn", "text": f"*Brand:*\n{brand_name}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":link: *Video Link:* <{video_url}|Click to watch the video>",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Please review the video and take action below:",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve Video"},
                    "style": "primary",
                    "action_id": "approve_video",
                    "value": json.dumps(
                        {"video_id": video_id, "campaign_id": campaign_id}
                    ),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Request Changes"},
                    "style": "danger",
                    "action_id": "request_changes",
                    "value": json.dumps(
                        {"video_id": video_id, "campaign_id": campaign_id}
                    ),
                },
            ],
        },
    ]


def build_approval_notification_blocks(
    creator_name: str, brand_name: str, approver_user_id: str
) -> list[dict]:
    """Notification block for when a video is approved."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":white_check_mark: *Video Approved!*\n\n"
                    f"*Creator:* {creator_name}\n"
                    f"*Brand:* {brand_name}\n"
                    f"*Approved by:* <@{approver_user_id}>\n\n"
                    f"Approval email has been sent to the creator. "
                    f"They are clear to post!"
                ),
            },
        },
    ]


def build_changes_requested_blocks(
    creator_name: str,
    brand_name: str,
    reviewer_user_id: str,
    feedback: str,
) -> list[dict]:
    """Notification block for when changes are requested on a video."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":pencil2: *Changes Requested*\n\n"
                    f"*Creator:* {creator_name}\n"
                    f"*Brand:* {brand_name}\n"
                    f"*Requested by:* <@{reviewer_user_id}>\n"
                    f"*Feedback:* {feedback}\n\n"
                    f"Feedback email has been sent to the creator."
                ),
            },
        },
    ]


def build_campaign_status_blocks(campaigns: list[dict]) -> list[dict]:
    """Build a campaign status overview for slash commands."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":bar_chart: Campaign Status"},
        },
        {"type": "divider"},
    ]

    status_emojis = {
        "pending": ":large_blue_circle:",
        "video_submitted": ":film_frames:",
        "under_review": ":large_yellow_circle:",
        "approved": ":white_check_mark:",
        "changes_requested": ":pencil2:",
        "posted": ":tada:",
        "overdue": ":red_circle:",
    }

    for c in campaigns:
        emoji = status_emojis.get(c["status"], ":grey_question:")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{emoji} *{c['creator_name']}* x *{c['brand_name']}*\n"
                        f"Deadline: {c['deadline']} | Status: `{c['status']}`"
                    ),
                },
            }
        )

    if not campaigns:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "No active campaigns found.",
                },
            }
        )

    return blocks


def build_creator_stats_blocks(stats: dict) -> list[dict]:
    """Build a creator's Instagram stats summary."""
    if "error" in stats:
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":x: Could not fetch stats: {stats['error']}",
                },
            }
        ]

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":chart_with_upwards_trend: Stats for @{stats['username']}",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Followers:*\n{stats['followers']:,}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Total Posts:*\n{stats['total_posts']:,}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Avg Likes (recent):*\n{stats['recent_avg_likes']:,}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Avg Comments (recent):*\n{stats['recent_avg_comments']:,}",
                },
            ],
        },
    ]
