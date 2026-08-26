"""
Slack Block Kit message templates for INFLUENCE Bot.
Rich notifications for milestones, deliverables, deadlines, uploads,
payment summaries, and webhook events (review/video links).
"""

import re
from datetime import date


def _format_upload_date(iso_date: str) -> str:
    """Render an ISO date string (YYYY-MM-DD) as 'Month D, YYYY'."""
    if not iso_date:
        return ""
    try:
        d = date.fromisoformat(iso_date)
    except ValueError:
        return iso_date
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _ordinal(n: int) -> str:
    """1 -> '1st', 2 -> '2nd', 11 -> '11th', etc."""
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _video_ordinal_label(video_title: str) -> str:
    """
    Derive an ordinal label like '1st video' from a 'Post N' title.
    Falls back to the title itself, or 'video' if neither is usable.
    """
    if video_title:
        m = re.search(r"(\d+)", video_title)
        if m:
            return f"{_ordinal(int(m.group(1)))} video"
        return video_title
    return "video"


def build_milestone_blocks(
    creator_username: str,
    campaign_name: str,
    brand_name: str,
    milestone_label: str,
    first_posted: str = "",
    video_link: str = "",
    include_brand: bool = True,
) -> list[dict]:
    """
    Notification when a single post crosses a view milestone (250K, 500K,
    1M, 1.5M, ...). The view count refers to that one post, not the
    creator's combined views across all their posts.

    `include_brand=True` for the admin channel, `False` for the brand's
    own workspace (where the brand line is redundant).
    """
    lines = [f":rocket: *Breakout video alert - {milestone_label} views!*", ""]
    if include_brand and brand_name:
        lines.append(f"*Brand:* {brand_name}")
    if campaign_name:
        lines.append(f"*Campaign:* {campaign_name}")
    if creator_username:
        lines.append(f"*Creator:* @{creator_username}")
    if first_posted:
        lines.append(f"*1st Posted:* {first_posted}")
    if video_link:
        lines.append(f"*Link:* {video_link}")

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        },
        {"type": "divider"},
    ]


def _mark_as_paid_value(campaign_id: str, creator_username: str) -> str:
    """Encode the identifiers needed by the mark_as_paid action handler."""
    return f"{campaign_id}|{creator_username}"


def build_deliverable_complete_blocks(
    creator_username: str,
    campaign_name: str,
    brand_name: str,
    campaign_id: str = "",
) -> list[dict]:
    """Notification when all deliverables are complete — flag for payment."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":white_check_mark: Deliverables Complete!",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*@{creator_username}* has completed all deliverables "
                    f"for *{campaign_name}* ({brand_name}).\n\n"
                    f":moneybag: *This creator is ready to be paid.*"
                ),
            },
        },
        {
            "type": "actions",
            "block_id": f"mark_paid_{campaign_id}_{creator_username}",
            "elements": [
                {
                    "type": "button",
                    "action_id": "mark_as_paid",
                    "style": "primary",
                    "text": {
                        "type": "plain_text",
                        "text": ":moneybag: Mark as paid",
                    },
                    "value": _mark_as_paid_value(campaign_id, creator_username),
                },
            ],
        },
        {"type": "divider"},
    ]


def _chase_value(campaign_id: str, creator_username: str) -> str:
    """Encode the identifiers the chase brake handlers need."""
    return f"{campaign_id}|{creator_username}"


# Headline and tone per rung. The pre-deadline tiers are reminders; the
# post-deadline ones escalate, and the last hands over to a person.
_RUNG_PRESENTATION = {
    "overdue": (":red_circle:", "Deadline Overdue"),
    "overdue_2": (":large_orange_circle:", "Still Overdue — Second Notice"),
    "overdue_3": (":rotating_light:", "Final Notice Sent"),
    "overdue_final": (":no_bell:", "Automated Chase Exhausted"),
    "1_day": (":warning:", "Deadline Tomorrow!"),
    "3_days": (":calendar:", "Deadline Approaching"),
}


def build_deadline_reminder_blocks(
    creator_username: str,
    campaign_name: str,
    brand_name: str,
    deadline: str,
    reminder_type: str,
    days_left: int,
    email_note: str | None = None,
    campaign_id: str = "",
    days_overdue: int | None = None,
    chat_url: str | None = None,
    emailed: bool = True,
) -> list[dict]:
    """
    One rung of the deadline ladder, as the team sees it in Slack.

    `email_note` explains why the creator wasn't emailed — their videos in
    review already cover what's outstanding, the shortfall is views they
    can't act on, or this is the final rung, which never emails. The team
    reads it to know whether to chase the creator, the brand, or neither.

    Post-deadline rungs carry the brake: Snooze parks the ladder for a few
    days when someone has replied outside the system, Stop ends it for good.
    Without them a four-rung ladder cannot be halted between polls.
    """
    emoji, title = _RUNG_PRESENTATION.get(reminder_type, (":calendar:", "Deadline"))
    is_post_deadline = reminder_type.startswith("overdue")
    late = days_overdue if days_overdue is not None else abs(days_left)

    if reminder_type == "overdue_final":
        status_text = (
            f"The deadline was *{deadline}* — now *{late} day(s) overdue*. "
            "Three emails have gone out and the automated chase stops here. "
            "*This one needs a person.*"
        )
    elif is_post_deadline:
        status_text = f"The deadline was *{deadline}* — now *{late} day(s) overdue*."
    elif reminder_type == "1_day":
        status_text = f"The deadline is *{deadline}* — *1 day remaining*."
    else:
        status_text = f"The deadline is *{deadline}* — *{days_left} days remaining*."

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {title}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Creator:*\n@{creator_username}"},
                {"type": "mrkdwn", "text": f"*Campaign:*\n{campaign_name}"},
                {"type": "mrkdwn", "text": f"*Brand:*\n{brand_name}"},
                {"type": "mrkdwn", "text": f"*Deadline:*\n{deadline}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": status_text},
        },
    ]

    if email_note:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":mailbox_with_no_mail: {email_note}"}],
        })
    elif emailed and is_post_deadline and reminder_type != "overdue_final":
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": ":outbox_tray: Creator emailed."}],
        })

    if is_post_deadline and campaign_id:
        elements = [
            {
                "type": "button",
                "action_id": "chase_snooze_3d",
                "text": {"type": "plain_text", "text": ":zzz: Snooze 3d"},
                "value": _chase_value(campaign_id, creator_username),
            },
            {
                "type": "button",
                "action_id": "chase_snooze_7d",
                "text": {"type": "plain_text", "text": ":zzz: Snooze 7d"},
                "value": _chase_value(campaign_id, creator_username),
            },
            {
                "type": "button",
                "action_id": "chase_stop",
                "style": "danger",
                "text": {"type": "plain_text", "text": ":octagonal_sign: Stop chasing"},
                "value": _chase_value(campaign_id, creator_username),
            },
        ]
        if chat_url:
            # Plain link button (no action_id) — it only navigates.
            elements.append({
                "type": "button",
                "text": {"type": "plain_text", "text": ":speech_balloon: Open chat"},
                "url": chat_url,
            })
        blocks.append({
            "type": "actions",
            "block_id": f"chase_actions_{campaign_id}_{creator_username}",
            "elements": elements,
        })

    blocks.append({"type": "divider"})
    return blocks


_DEADLINE_SOURCE_LABELS = {
    "bot": "a creator reply",
    "admin": "the dashboard",
    "deal-studio": "Deal Studio",
}


def build_deadline_changed_blocks(
    creator_username: str,
    campaign_name: str,
    brand_name: str,
    previous_deadline: str | None,
    new_deadline: str | None,
    source: str = "admin",
    actor: str | None = None,
    reason: str | None = None,
    ladder_reset: bool = False,
) -> list[dict]:
    """
    A creator's deadline moved — who moved it, from what to what, and why.

    The campaigns dashboard owns the date and fires this for every writer, so
    this is the one place the team sees a deadline move regardless of whether
    it came from an admin editing the row, a signed contract landing, or a
    creator agreeing a new date in chat.
    """
    origin = _DEADLINE_SOURCE_LABELS.get(source, source)
    fields = [
        {"type": "mrkdwn", "text": f"*Creator:*\n@{creator_username}"},
        {"type": "mrkdwn", "text": f"*Campaign:*\n{campaign_name}"},
        {"type": "mrkdwn", "text": f"*Was:*\n{previous_deadline or '—'}"},
        {"type": "mrkdwn", "text": f"*Now:*\n{new_deadline or '—'}"},
    ]

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":calendar: Deadline Changed"},
        },
        {"type": "section", "fields": fields},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Moved via *{origin}*"
                    + (f" by *{actor}*" if actor else "")
                    + (f" — {brand_name}" if brand_name else "")
                    + "."
                ),
            },
        },
    ]

    if reason:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"> {reason}"},
        })

    if ladder_reset:
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": (
                    ":arrows_counterclockwise: Chase reminders reset for the new "
                    "date — any snooze or stop on this creator has been lifted."
                ),
            }],
        })

    blocks.append({"type": "divider"})
    return blocks


_INTENT_PRESENTATION = {
    "commits_to_date": (":date:", "Creator committed to a date"),
    "cannot_deliver": (":warning:", "Creator says they cannot deliver"),
    "says_already_posted": (":eyes:", "Creator says it is already live"),
    "asks_a_question": (":question:", "Creator asked a question"),
    "unclear": (":envelope:", "Creator replied"),
}


def build_inbound_reply_blocks(
    creator_username: str,
    campaign_name: str,
    campaign_id: str,
    subject: str,
    body: str,
    reading: dict | None = None,
    current_deadline: str | None = None,
) -> list[dict]:
    """
    A creator's emailed reply, and — when they named a date — a *proposal* to
    move their deadline to it.

    The date is never applied here. A deadline is a contract term, and a model
    reading an email is not authority to rewrite one; the Confirm button is,
    because a person pressed it. Without a usable date the reply is still
    posted, because the whole point is that the team stops missing replies.
    """
    reading = reading or {}
    intent = reading.get("intent") or "unclear"
    emoji, title = _INTENT_PRESENTATION.get(intent, _INTENT_PRESENTATION["unclear"])
    proposed = reading.get("proposed_date")
    confidence = reading.get("confidence")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {title}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Creator:*\n@{creator_username}"},
                {"type": "mrkdwn", "text": f"*Campaign:*\n{campaign_name or '—'}"},
                {"type": "mrkdwn", "text": f"*Deadline:*\n{current_deadline or '—'}"},
                {"type": "mrkdwn", "text": f"*Proposed:*\n{proposed or '—'}"},
            ],
        },
    ]

    if reading.get("summary"):
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{reading['summary']}*"},
        })

    excerpt = (body or "").strip()
    if excerpt:
        if len(excerpt) > 1200:
            excerpt = excerpt[:1200] + "…"
        quoted = "\n".join(f"> {line}" for line in excerpt.splitlines())
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": quoted},
        })
    else:
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": (
                    ":grey_question: The message body could not be read — "
                    "check the inbox directly."
                ),
            }],
        })

    if subject:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":email: {subject}"}],
        })

    if proposed and campaign_id:
        note = "Nothing has changed yet — confirm to move the deadline."
        if confidence and confidence != "high":
            note = (
                f"Read with *{confidence}* confidence — check the message above "
                "before confirming."
            )
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":lock: {note}"}],
        })
        blocks.append({
            "type": "actions",
            "block_id": f"chase_revision_{campaign_id}_{creator_username}",
            "elements": [
                {
                    "type": "button",
                    "action_id": "chase_revision_confirm",
                    "style": "primary",
                    "text": {
                        "type": "plain_text",
                        "text": f":white_check_mark: Move deadline to {proposed}",
                    },
                    "value": f"{campaign_id}|{creator_username}|{proposed}",
                },
                {
                    "type": "button",
                    "action_id": "chase_revision_dismiss",
                    "text": {"type": "plain_text", "text": ":x: Dismiss"},
                    "value": f"{campaign_id}|{creator_username}|{proposed}",
                },
            ],
        })
    elif campaign_id:
        # No date to act on, but the chase should still pause while a person
        # reads this — otherwise the next rung goes out underneath them.
        blocks.append({
            "type": "actions",
            "block_id": f"chase_reply_{campaign_id}_{creator_username}",
            "elements": [
                {
                    "type": "button",
                    "action_id": "chase_snooze_3d",
                    "text": {"type": "plain_text", "text": ":zzz: Snooze 3d"},
                    "value": f"{campaign_id}|{creator_username}",
                },
                {
                    "type": "button",
                    "action_id": "chase_stop",
                    "style": "danger",
                    "text": {"type": "plain_text", "text": ":octagonal_sign: Stop chasing"},
                    "value": f"{campaign_id}|{creator_username}",
                },
            ],
        })

    blocks.append({"type": "divider"})
    return blocks


def build_upload_followup_blocks(
    creator_username: str,
    campaign_name: str,
    brand_name: str,
    videos_posted: int,
    videos_required: int,
    deadline: str,
    days_left: int,
) -> list[dict]:
    """Reminder when a creator is behind on uploads near the deadline."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":film_frames: Upload Reminder",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Creator:*\n@{creator_username}"},
                {"type": "mrkdwn", "text": f"*Campaign:*\n{campaign_name}"},
                {"type": "mrkdwn", "text": f"*Brand:*\n{brand_name}"},
                {"type": "mrkdwn", "text": f"*Deadline:*\n{deadline}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"@{creator_username} has posted *{videos_posted}/{videos_required}* "
                    f"videos with *{days_left} day(s)* remaining until the deadline."
                ),
            },
        },
        {"type": "divider"},
    ]


def build_payment_summary_blocks(completed_creators: list[dict]) -> list[dict]:
    """Daily payment summary of all creators with completed deliverables."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":sunrise: Daily Payment Summary",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{len(completed_creators)} creator(s)* have completed "
                    f"deliverables and are ready for payment:"
                ),
            },
        },
        {"type": "divider"},
    ]

    for creator in completed_creators:
        username = creator.get("username", "Unknown")
        campaign_name = creator.get("campaign_name", "")
        brand_name = creator.get("brand_name", "")
        campaign_id = creator.get("campaign_id", "")
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":moneybag: *@{username}* — "
                        f"{campaign_name} ({brand_name})"
                    ),
                },
                "accessory": {
                    "type": "button",
                    "action_id": "mark_as_paid",
                    "style": "primary",
                    "text": {
                        "type": "plain_text",
                        "text": "Mark as paid",
                    },
                    "value": _mark_as_paid_value(campaign_id, username),
                },
            }
        )

    return blocks


def build_review_submitted_blocks(
    creator_username: str,
    campaign_name: str,
    brand_name: str,
    video_link: str,
    notes: str,
    review_id: int | None = None,
    show_meta: bool = False,
    chat_url: str | None = None,
    admin_chat_url: str | None = None,
    include_ignore: bool = False,
) -> list[dict]:
    """
    Webhook event: creator submitted a video for review.

    `show_meta=True` adds Brand + Campaign rows — used on the admin
    side where one channel sees content from many brands. Brand
    workspaces leave it off since the workspace itself identifies
    the brand.

    `chat_url`, when provided, is baked into the Request Changes button
    as a URL — clicking the button opens the brand's chat space in a
    browser AND fires the action handler on our backend simultaneously
    (Slack delivers both when a button has both `url` and `action_id`).

    `admin_chat_url` switches the secondary button from "Request Changes"
    to an "Open as Admin" link that opens the admin side of the chat space
    (``/admin/chats/<id>``). Used for the INFLUENCE (admin) workspace, where
    the team enters the chat as admins rather than requesting changes as the
    brand. It's a plain link button (no action_id), so it only navigates —
    it doesn't record a decision or email the creator.

    `include_ignore` adds the "Ignore" button. INFLUENCE-workspace only:
    ignoring is our own call on submissions that were never meant to be
    reviewed, and the brand shouldn't see (or make) it.
    """
    body_lines = [":video_camera: *Content to be reviewed*", ""]
    if show_meta:
        if brand_name:
            body_lines.append(f"*Brand:* {brand_name}")
        if campaign_name:
            body_lines.append(f"*Campaign:* {campaign_name}")
        if brand_name or campaign_name:
            body_lines.append("")
    if creator_username:
        body_lines.append("*Instagram username*")
        body_lines.append(f"@{creator_username}")
        body_lines.append("")
    if video_link:
        body_lines.append("*Link*")
        body_lines.append(video_link)
    if notes:
        body_lines.append("")
        body_lines.append(f":memo: *Notes:* {notes}")

    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(body_lines).rstrip()},
        },
    ]

    if review_id is not None:
        if admin_chat_url:
            # INFLUENCE (admin) workspace: a plain link into the admin side of
            # the chat space. No action_id — it only navigates.
            secondary_btn = {
                "type": "button",
                "text": {"type": "plain_text", "text": "Open as Admin"},
                "url": admin_chat_url,
            }
        else:
            # Brand workspace: the hybrid Request Changes button (url +
            # action_id) that opens the brand chat AND records the decision.
            secondary_btn = {
                "type": "button",
                "action_id": "review_request_changes",
                "text": {"type": "plain_text", "text": "Request Changes"},
                "value": str(review_id),
            }
            if chat_url:
                secondary_btn["url"] = chat_url
        elements = [
            {
                "type": "button",
                "action_id": "review_approve",
                "style": "primary",
                "text": {"type": "plain_text", "text": "Approve"},
                "value": str(review_id),
            },
            secondary_btn,
        ]
        if include_ignore:
            elements.append(build_review_ignore_button(review_id))
        blocks.append(
            {
                "type": "actions",
                "block_id": f"review_actions_{review_id}",
                "elements": elements,
            }
        )

    blocks.append({"type": "divider"})
    return blocks


def build_review_ignore_button(review_id: int) -> dict:
    """
    The "Ignore" button element for a review's action row.

    Confirmation-gated: ignoring silences the review for good (no
    auto-approval, no coverage of the creator's deliverables), so a stray
    click shouldn't be able to do it. "Undo ignore" is offered afterwards
    either way — see `build_review_ignored_blocks`.
    """
    return {
        "type": "button",
        "action_id": "review_ignore",
        "text": {"type": "plain_text", "text": "Ignore"},
        "value": str(review_id),
        "confirm": {
            "title": {"type": "plain_text", "text": "Ignore this submission?"},
            "text": {
                "type": "mrkdwn",
                "text": (
                    "Use this when the link wasn't meant for review.\n\n"
                    "• It won't be auto-approved after 24h\n"
                    "• It stops counting as a video in review, so the creator "
                    "keeps getting their deadline reminders\n\n"
                    "You can undo this afterwards."
                ),
            },
            "confirm": {"type": "plain_text", "text": "Ignore"},
            "deny": {"type": "plain_text", "text": "Cancel"},
        },
    }


def build_review_ignored_blocks(
    review_id: int,
    creator_username: str,
    actor_label: str,
    timestamp: str,
) -> list[dict]:
    """
    Footer + "Undo ignore" row appended to a review message once it's been
    ignored, replacing the Approve / Ignore action row.

    `actor_label` is rendered as-is, so pass a Slack mention (``<@U123>``)
    when the click's user id is known and a plain name otherwise.
    """
    return [
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f":no_bell: *Ignored* by {actor_label} — "
                        f"@{creator_username} ({timestamp}). No auto-approval, "
                        f"and it no longer counts as a video in review."
                    ),
                }
            ],
        },
        {
            "type": "actions",
            "block_id": f"review_ignored_actions_{review_id}",
            "elements": [
                {
                    "type": "button",
                    "action_id": "review_unignore",
                    "text": {"type": "plain_text", "text": "Undo ignore"},
                    "value": str(review_id),
                }
            ],
        },
    ]


def build_review_closed_context_block(creator_username: str, timestamp: str) -> dict:
    """
    Brand-workspace footer for a review the INFLUENCE team ignored.

    The brand's copy loses its buttons at the same time, so this explains
    why — without exposing our internal "ignored" wording or naming who
    clicked it.
    """
    return {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    f":no_entry_sign: *No review needed* — this submission was "
                    f"closed by the INFLUENCE team. @{creator_username} "
                    f"({timestamp})"
                ),
            }
        ],
    }


def build_review_approved_blocks(
    creator_username: str,
    campaign_name: str,
    brand_name: str,
    video_link: str,
    actor_name: str,
) -> list[dict]:
    """
    Notification posted to the admin #content-reviews channel after a brand
    clicks Approve on a review. Distinct from the updated-in-place review
    message so the admin team gets a fresh ping even when the click came
    from the brand's own workspace.
    """
    body_lines = [":white_check_mark: *Review approved*", ""]
    if brand_name:
        body_lines.append(f"*Brand:* {brand_name}")
    if campaign_name:
        body_lines.append(f"*Campaign:* {campaign_name}")
    if creator_username:
        body_lines.append(f"*Creator:* @{creator_username}")
    if video_link:
        body_lines.append(f"*Link:* {video_link}")
    if actor_name:
        body_lines.append("")
        body_lines.append(f":bust_in_silhouette: Approved by *{actor_name}*")

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(body_lines).rstrip()},
        },
        {"type": "divider"},
    ]


_PLATFORM_LABELS = {
    "instagram": "Reels",
    "tiktok": "Tiktok",
    "youtube": "Shorts",
}


def build_video_links_submitted_blocks(
    creator_username: str,
    campaign_name: str,
    brand_name: str,
    video_title: str,
    links: list[dict],
    show_meta: bool = False,
) -> list[dict]:
    """
    Webhook event: creator submitted video links (posted content).

    `links` is a list of dicts with keys `platform` (raw key, e.g.
    'instagram', 'tiktok', 'youtube') and `url`.

    `show_meta=True` adds Brand + Campaign rows for the admin side.
    """
    body_lines = [":tada: *Content posted*", ""]
    if show_meta:
        if brand_name:
            body_lines.append(f"*Brand:* {brand_name}")
        if campaign_name:
            body_lines.append(f"*Campaign:* {campaign_name}")
        if brand_name or campaign_name:
            body_lines.append("")
    if creator_username:
        body_lines.append("*Instagram username*")
        body_lines.append(f"@{creator_username}")
        body_lines.append("")

    body_lines.append(f"*{_video_ordinal_label(video_title)}*")

    for link in links:
        url = link.get("url")
        if not url:
            continue
        platform_key = (link.get("platform") or "").lower()
        label = _PLATFORM_LABELS.get(platform_key) or (
            link.get("platform") or platform_key or "Link"
        )
        body_lines.append("")
        body_lines.append(f"*{label}*")
        body_lines.append(url)

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(body_lines).rstrip()},
        },
        {"type": "divider"},
    ]


def build_chat_new_message_blocks(
    *,
    creator_username: str,
    campaign_name: str,
    sender_name: str,
    preview: str,
    chat_url: str,
) -> list[dict]:
    """New-message ping into the brand workspace channel."""
    preview = (preview or "").replace("\n", " ").strip()
    if len(preview) > 200:
        preview = preview[:197] + "…"
    header = (
        f":envelope_with_arrow: *New message from {sender_name} "
        f"in chat with @{creator_username}* — _{campaign_name}_"
    )
    if preview:
        header = f"{header}\n>{preview}"
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": header},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open Chat"},
                    "url": chat_url,
                }
            ],
        },
    ]


def build_chat_influence_ping_blocks(
    *,
    creator_username: str,
    brand_name: str,
    campaign_name: str,
    sender_name: str,
    preview: str,
    admin_url: str = "",
    mention: str = "",
) -> list[dict]:
    """
    New-chat-message ping into the INFLUENCE team channel (#content-reviews),
    so Jennifer's team stays in the loop on creator <-> brand chatter.

    `mention`, when set (e.g. "<!subteam^S012ABC3>" or "<@U012ABC3>"), is
    prepended so the team is notified even though the ping threads under the
    review post. It must live inside the block text for Slack to parse it as
    a real mention.
    """
    preview = (preview or "").replace("\n", " ").strip()
    if len(preview) > 200:
        preview = preview[:197] + "…"
    header = (
        f":speech_balloon: *New chat message from {sender_name}*\n"
        f"*{brand_name}* × @{creator_username} · _{campaign_name}_"
    )
    if mention:
        header = f"{mention} {header}"
    if preview:
        header = f"{header}\n>{preview}"
    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
    ]
    if admin_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open in admin"},
                        "url": admin_url,
                    }
                ],
            }
        )
    return blocks

