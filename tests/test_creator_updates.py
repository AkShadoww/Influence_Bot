"""
Tests for campaign updates to creators over WhatsApp
(services/creator_updates.py).

This bot doesn't send the WhatsApp message — the outreach service does.
What this module is responsible for is narrower, and that's what's pinned
here: that it stays silent and harmless when it isn't configured, that
the payload it POSTs says who the creator is and what happened in a shape
the outreach service accepts, and that nothing it does can take down the
Slack notification it runs alongside.

The last one matters most. Every call site is in the middle of a webhook
handler that was posting to Slack and emailing a brand; a campaign update
is a courtesy on top of that work, so an unreachable outreach service, a
bad token or a malformed response must all end as a log line, never as an
exception escaping into the handler.

Run with `python -m pytest tests/test_creator_updates.py`.
"""

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import requests  # noqa: E402

from config import Config  # noqa: E402
from services import creator_updates  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ""

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def configured(monkeypatch):
    """A wired-up outreach service."""
    monkeypatch.setattr(Config, "OUTREACH_API_BASE", "https://outreach.example/")
    monkeypatch.setattr(Config, "OUTREACH_BOT_TOKEN", "secret-token")


@pytest.fixture
def posted(monkeypatch):
    """Capture every requests.post the module makes, answering 200 OK."""
    calls = []

    def _fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse(200, {"ok": True, "outcome": "queued", "creatorId": 7})

    monkeypatch.setattr(requests, "post", _fake_post)
    return calls


# --- configuration ---------------------------------------------------------


def test_unconfigured_is_a_silent_no_op(monkeypatch):
    """
    A deploy without the outreach service must behave exactly as this bot
    did before campaign updates existed — no request, no exception.
    """
    monkeypatch.setattr(Config, "OUTREACH_API_BASE", None)
    monkeypatch.setattr(Config, "OUTREACH_BOT_TOKEN", None)

    def _explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("no request should be made when unconfigured")

    monkeypatch.setattr(requests, "post", _explode)

    assert creator_updates.is_configured() is False
    creator_updates.review_submitted(
        username="sam", email="sam@example.com", campaign={"id": "c1"}
    )


def test_half_configured_counts_as_unconfigured(monkeypatch):
    """A base URL with no token would only ever earn a 401."""
    monkeypatch.setattr(Config, "OUTREACH_API_BASE", "https://outreach.example")
    monkeypatch.setattr(Config, "OUTREACH_BOT_TOKEN", None)
    assert creator_updates.is_configured() is False

    monkeypatch.setattr(Config, "OUTREACH_API_BASE", None)
    monkeypatch.setattr(Config, "OUTREACH_BOT_TOKEN", "t")
    assert creator_updates.is_configured() is False


def test_a_creator_with_no_identity_is_not_sent(configured, posted):
    """Neither handle nor email — there is nobody for the other side to match."""
    creator_updates.send("review_submitted", campaign={"id": "c1"}, blocking=True)
    assert posted == []


# --- payload shape ---------------------------------------------------------


def test_the_request_is_addressed_and_authenticated(configured, posted):
    creator_updates.send(
        "review_submitted",
        username="sam",
        email="sam@example.com",
        campaign={"id": "c1"},
        blocking=True,
    )

    assert len(posted) == 1
    call = posted[0]
    # The trailing slash on OUTREACH_API_BASE must not produce a double slash.
    assert call["url"] == "https://outreach.example/api/bot/creator-updates"
    assert call["headers"]["x-bot-token"] == "secret-token"
    assert call["timeout"] == Config.OUTREACH_API_TIMEOUT


def test_the_at_sign_is_stripped_from_the_handle(configured, posted):
    """
    Slack copy carries "@sam"; the outreach service matches on the bare
    handle stored in its creators table.
    """
    creator_updates.send(
        "review_submitted", username="@sam", campaign={"id": "c1"}, blocking=True
    )
    assert posted[0]["json"]["creator"]["username"] == "sam"


def test_brand_name_is_read_from_either_spelling(configured, posted):
    """
    Webhook payloads use `brandName`; some internal dicts use `brand_name`.
    Callers pass whichever they were handed.
    """
    creator_updates.send(
        "review_submitted",
        username="sam",
        campaign={"id": "c1", "brand_name": "Reve"},
        blocking=True,
    )
    assert posted[0]["json"]["campaign"]["brandName"] == "Reve"


def test_a_dedup_key_is_forwarded_so_a_redelivery_is_dropped(configured, posted):
    """
    The campaigns dashboard fires webhooks AND is polled as a safety net, so
    the same approval genuinely arrives twice. The key is what stops the
    creator being messaged about it twice.
    """
    creator_updates.review_approved(
        username="sam",
        email=None,
        campaign={"id": "c1"},
        submit_posts_url="https://x.io/submit",
        dedup_key="review:42",
    )
    _wait_for(posted, 1)
    assert posted[0]["json"]["dedupKey"] == "review:42"


def test_no_dedup_key_means_the_field_is_absent_not_null(configured, posted):
    creator_updates.send(
        "review_submitted", username="sam", campaign={"id": "c1"}, blocking=True
    )
    assert "dedupKey" not in posted[0]["json"]


# --- per-event wrappers ----------------------------------------------------


def test_review_feedback_relays_the_text_verbatim(configured, posted):
    """A paraphrased change request is how a re-shoot gets shot wrong."""
    feedback = "Cut the first 3 seconds and say the product name earlier"
    creator_updates.review_feedback(
        username="sam",
        email="sam@example.com",
        campaign={"id": "c1", "brandName": "Reve"},
        feedback=feedback,
        sender_name="Ana",
        chat_url="https://x.io/chat/1",
        dedup_key="chat:9",
    )
    _wait_for(posted, 1)

    body = posted[0]["json"]
    assert body["event"] == "review_feedback"
    assert body["data"]["feedback"] == feedback
    assert body["data"]["senderName"] == "Ana"
    assert body["data"]["chatUrl"] == "https://x.io/chat/1"


def test_review_approved_carries_the_submit_posts_url(configured, posted):
    creator_updates.review_approved(
        username="sam",
        email=None,
        campaign={"id": "c1"},
        submit_posts_url="https://x.io/submit",
    )
    _wait_for(posted, 1)
    assert posted[0]["json"]["data"]["submitPostsUrl"] == "https://x.io/submit"


def test_post_submitted_carries_the_post_url(configured, posted):
    creator_updates.post_submitted(
        username="sam", email=None, campaign={"id": "c1"}, post_url="https://ig.com/p/1"
    )
    _wait_for(posted, 1)
    assert posted[0]["json"]["data"]["postUrl"] == "https://ig.com/p/1"


def test_every_wrapper_sends_the_event_name_it_advertises(configured, posted):
    """
    The outreach service rejects an unknown event name outright, so a typo
    here silently costs a creator every message of that kind.
    """
    creator_updates.review_submitted(username="sam", email=None, campaign={})
    creator_updates.review_approved(username="sam", email=None, campaign={})
    creator_updates.review_feedback(
        username="sam", email=None, campaign={}, feedback="x"
    )
    creator_updates.post_submitted(username="sam", email=None, campaign={})
    creator_updates.deliverables_complete(username="sam", email=None, campaign={})
    _wait_for(posted, 5)

    assert sorted(c["json"]["event"] for c in posted) == sorted(
        [
            creator_updates.EVENT_REVIEW_SUBMITTED,
            creator_updates.EVENT_REVIEW_APPROVED,
            creator_updates.EVENT_REVIEW_FEEDBACK,
            creator_updates.EVENT_POST_SUBMITTED,
            creator_updates.EVENT_DELIVERABLES_COMPLETE,
        ]
    )


# --- failure is never fatal ------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(401, text="Unauthorized"),
        FakeResponse(503, text="not configured"),
        FakeResponse(400, {"error": "unknown event"}, text="unknown event"),
        FakeResponse(500, text="boom"),
        FakeResponse(200, None, text="not json"),
    ],
    ids=["bad-token", "not-configured", "rejected", "server-error", "unparseable"],
)
def test_an_unhappy_response_never_raises(configured, monkeypatch, response):
    monkeypatch.setattr(requests, "post", lambda *a, **k: response)
    creator_updates.send(
        "review_submitted", username="sam", campaign={"id": "c1"}, blocking=True
    )


def test_an_unreachable_outreach_service_never_raises(configured, monkeypatch):
    """
    The Slack notification this runs alongside must go out regardless of
    whether the outreach service is up.
    """

    def _boom(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(requests, "post", _boom)
    creator_updates.send(
        "review_submitted", username="sam", campaign={"id": "c1"}, blocking=True
    )


def test_a_background_send_does_not_surface_its_failure(configured, monkeypatch):
    """
    The default path runs on a daemon thread so a slow outreach service can't
    add seconds to a webhook. A failure there must die quietly in the thread.
    """

    def _boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(requests, "post", _boom)
    creator_updates.review_submitted(username="sam", email=None, campaign={"id": "c1"})
    # Reaching here without an exception in the calling thread is the assertion.


def _wait_for(calls, count, timeout=2.0):
    """Wait for `count` background sends to land."""
    import time

    deadline = time.time() + timeout
    while len(calls) < count and time.time() < deadline:
        time.sleep(0.01)
    assert len(calls) == count, f"expected {count} sends, saw {len(calls)}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
