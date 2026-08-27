"""
Campaign updates to creators over WhatsApp.

This bot sees everything that happens to a creator's content — a draft
submitted, a brand approving it, feedback typed into the review chat, a
post link landing, deliverables completing — and tells Slack and email
about all of it. What it has never been able to do is tell the *creator*
on the channel they actually read.

The outreach service (Influence-Inc/Outreach_Email_Automation) can: it
holds the creators' phone numbers, the WhatsApp Business credentials and
the approved message templates. So the division is simply who knows what.
This module reports WHAT happened and to WHOM, in the vocabulary this bot
already speaks — an Instagram handle and a campaign — and every decision
that needs data we don't have (is this creator subscribed? is their 24h
WhatsApp window open? send now as free-form text, send a template, or
queue it until they write in?) is made over there.

Wiring
------
    OUTREACH_API_BASE   the outreach service's base URL
    OUTREACH_BOT_TOKEN  its OUTREACH_BOT_TOKEN, sent as `x-bot-token`

With either unset this module is a no-op that logs once at debug level:
the bot's Slack and email notifications are unaffected, creators simply
don't get the WhatsApp copy. That is the same convention the rest of the
bot uses for optional integrations, and it means a deploy without the
outreach service configured behaves exactly as it did before.

Everything here is best-effort and never raises. A campaign update is a
courtesy notification; a creator missing one is a much smaller problem
than an exception escaping into the webhook handler that was posting to
Slack, so failures are logged and swallowed. Sends run on a background
thread for the same reason — a slow outreach service must not add seconds
to a webhook this bot is expected to answer promptly.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import requests

from config import Config

logger = logging.getLogger(__name__)

# Matches UPDATE_KINDS in the outreach service's services/creatorUpdates.js.
# An event this bot sends that the outreach service doesn't know is rejected
# there with a 400 listing the valid names, so the two lists are checkable
# against each other rather than silently drifting.
EVENT_BRIEF_READY = "brief_ready"
EVENT_REVIEW_SUBMITTED = "review_submitted"
EVENT_REVIEW_APPROVED = "review_approved"
EVENT_REVIEW_FEEDBACK = "review_feedback"
EVENT_POST_SUBMITTED = "post_submitted"
EVENT_DELIVERABLES_COMPLETE = "deliverables_complete"


def _base_url() -> Optional[str]:
    url = Config.OUTREACH_API_BASE
    return url.rstrip("/") if url else None


def _token() -> Optional[str]:
    return Config.OUTREACH_BOT_TOKEN or None


def is_configured() -> bool:
    """True when campaign updates can actually be delivered."""
    return bool(_base_url() and _token())


def _post(payload: dict) -> Optional[dict]:
    """
    POST one update. Returns the parsed response, or None on any failure.

    The outreach service answers 200 with an `outcome` for every ordinary
    result — including ones that sent nothing, like an unmatched handle or
    a creator who isn't on the WhatsApp lane. Those are logged at debug:
    most creators are not subscribed, and at info they would drown the log
    in non-events.
    """
    base, token = _base_url(), _token()
    if not base or not token:
        return None

    try:
        resp = requests.post(
            f"{base}/api/bot/creator-updates",
            json=payload,
            headers={"x-bot-token": token, "Content-Type": "application/json"},
            timeout=Config.OUTREACH_API_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning(
            "Campaign update %s for @%s could not be delivered: %s",
            payload.get("event"),
            (payload.get("creator") or {}).get("username"),
            exc,
        )
        return None

    if resp.status_code == 401:
        logger.error(
            "Campaign updates rejected: OUTREACH_BOT_TOKEN does not match the "
            "outreach service's token. No creator will receive WhatsApp updates "
            "until this is fixed."
        )
        return None
    if resp.status_code == 503:
        logger.error(
            "Campaign updates rejected: OUTREACH_BOT_TOKEN is not set on the "
            "outreach service."
        )
        return None
    if not resp.ok:
        logger.warning(
            "Campaign update %s for @%s returned %s: %s",
            payload.get("event"),
            (payload.get("creator") or {}).get("username"),
            resp.status_code,
            resp.text[:200],
        )
        return None

    try:
        data = resp.json()
    except ValueError:
        return None

    outcome = data.get("outcome")
    username = (payload.get("creator") or {}).get("username")
    if outcome in ("sent", "queued"):
        logger.info(
            "Campaign update %s for @%s: %s", payload.get("event"), username, outcome
        )
    else:
        logger.debug(
            "Campaign update %s for @%s: %s", payload.get("event"), username, outcome
        )
    return data


def send(
    event: str,
    *,
    username: Optional[str] = None,
    email: Optional[str] = None,
    campaign: Optional[dict] = None,
    data: Optional[dict] = None,
    dedup_key: Optional[str] = None,
    blocking: bool = False,
) -> None:
    """
    Report one campaign update for one creator.

    `dedup_key` should be the underlying event's own identity — a review
    id, a post URL. The campaign dashboard fires webhooks AND is polled as
    a safety net, so the same approval genuinely arrives twice; passing a
    key lets the outreach service drop the duplicate instead of messaging
    the creator about it again.

    Fire-and-forget by default: the send runs on a daemon thread so a slow
    or unreachable outreach service can't hold up the Slack notification
    the caller is in the middle of. `blocking=True` is for tests and for
    callers that need the result.
    """
    if not is_configured():
        logger.debug(
            "Campaign update %s skipped — OUTREACH_API_BASE / OUTREACH_BOT_TOKEN "
            "not set",
            event,
        )
        return
    if not username and not email:
        logger.debug("Campaign update %s skipped — no creator identity", event)
        return

    camp = campaign or {}
    payload = {
        "event": event,
        "creator": {
            "username": (username or "").lstrip("@") or None,
            "email": email or None,
        },
        "campaign": {
            "id": camp.get("id"),
            "name": camp.get("name"),
            "brandName": camp.get("brandName") or camp.get("brand_name"),
        },
        "data": data or {},
    }
    if dedup_key:
        payload["dedupKey"] = dedup_key

    if blocking:
        _post(payload)
        return

    def _run() -> None:
        try:
            _post(payload)
        except Exception as exc:  # never let a notification kill a thread noisily
            logger.warning("Campaign update %s failed: %s", event, exc)

    threading.Thread(
        target=_run, name=f"creator-update-{event}", daemon=True
    ).start()


# --- Convenience wrappers, one per event -----------------------------------
# Each takes what its call site already has in hand, so a caller never has to
# assemble the payload shape or remember an event name.


def review_submitted(*, username, email, campaign, dedup_key=None) -> None:
    """A creator's draft reached us and is with the brand for review."""
    send(
        EVENT_REVIEW_SUBMITTED,
        username=username,
        email=email,
        campaign=campaign,
        dedup_key=dedup_key,
    )


def review_approved(
    *, username, email, campaign, submit_posts_url=None, dedup_key=None
) -> None:
    """The brand approved the draft — the creator is clear to post."""
    send(
        EVENT_REVIEW_APPROVED,
        username=username,
        email=email,
        campaign=campaign,
        data={"submitPostsUrl": submit_posts_url},
        dedup_key=dedup_key,
    )


def review_feedback(
    *, username, email, campaign, feedback, sender_name=None, chat_url=None,
    dedup_key=None,
) -> None:
    """
    A brand or INFLUENCE-team message from the review chat space.

    `feedback` is relayed verbatim: a paraphrase of a change request is how
    a re-shoot gets shot wrong.
    """
    send(
        EVENT_REVIEW_FEEDBACK,
        username=username,
        email=email,
        campaign=campaign,
        data={
            "feedback": feedback,
            "senderName": sender_name,
            "chatUrl": chat_url,
        },
        dedup_key=dedup_key,
    )


def post_submitted(*, username, email, campaign, post_url=None, dedup_key=None) -> None:
    """A live post link landed — we're tracking its views from here."""
    send(
        EVENT_POST_SUBMITTED,
        username=username,
        email=email,
        campaign=campaign,
        data={"postUrl": post_url},
        dedup_key=dedup_key,
    )


def deliverables_complete(*, username, email, campaign, dedup_key=None) -> None:
    """
    Every deliverable is met — the campaign is done for this creator.

    The outreach service deliberately keeps them subscribed after this, so
    the next campaign's outreach reaches them on WhatsApp instead of a cold
    email.
    """
    send(
        EVENT_DELIVERABLES_COMPLETE,
        username=username,
        email=email,
        campaign=campaign,
        dedup_key=dedup_key,
    )
