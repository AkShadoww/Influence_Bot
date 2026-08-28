"""
Tests for reading creator replies — services/inbound_replies.py.

The security tests here are the important ones. This is the only inbound path
that can lead to a contracted deadline moving, so it must refuse anything it
cannot verify, and it must never apply a change on its own say-so.

The classifier is stubbed throughout: what is under test is the plumbing
around it — attribution, quoted-thread stripping, the sanity bounds on a
proposed date, and the rule that a reply always reaches Slack even when every
optional step fails.

Run with `python -m pytest tests/test_inbound_replies.py`.
"""

import base64
import hashlib
import hmac
import json
import os
import sys
from datetime import date, timedelta

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config  # noqa: E402
from models.models import (  # noqa: E402
    ChaseReplyAddress,
    ChaseState,
    SessionLocal,
    init_db,
)
from services import chase_ladder, inbound_replies  # noqa: E402
from services.inbound_replies import (  # noqa: E402
    InboundReply,
    InboundReplyHandler,
    normalize,
    reply_address_for,
    resolve_reply_address,
    strip_quoted,
    verify_signature,
)

init_db()

CAMPAIGN = "camp-in"
CREATOR = "replying.creator"
SECRET_RAW = b"0123456789abcdef0123456789abcdef"
SECRET = "whsec_" + base64.b64encode(SECRET_RAW).decode()


class FakeSlackClient:
    def __init__(self):
        self.messages = []

    def chat_postMessage(self, **kwargs):
        self.messages.append(kwargs)
        return {"ok": True}


@pytest.fixture(autouse=True)
def _inbound_config():
    saved = (
        Config.CHASE_INBOUND_ENABLED,
        Config.CHASE_REPLY_DOMAIN,
        Config.RESEND_WEBHOOK_SECRET,
        Config.ANTHROPIC_API_KEY,
    )
    Config.CHASE_INBOUND_ENABLED = True
    Config.CHASE_REPLY_DOMAIN = "reply.test"
    Config.RESEND_WEBHOOK_SECRET = SECRET
    # No key: interpret() returns None, so these exercise the unread path
    # unless a test stubs the classifier explicitly.
    Config.ANTHROPIC_API_KEY = None
    yield
    (
        Config.CHASE_INBOUND_ENABLED,
        Config.CHASE_REPLY_DOMAIN,
        Config.RESEND_WEBHOOK_SECRET,
        Config.ANTHROPIC_API_KEY,
    ) = saved

    db = SessionLocal()
    try:
        db.query(ChaseReplyAddress).filter_by(campaign_id=CAMPAIGN).delete()
        db.query(ChaseState).filter_by(campaign_id=CAMPAIGN).delete()
        db.commit()
    finally:
        db.close()


def _sign(body: bytes, msg_id="msg_1", timestamp="1700000000"):
    signed = b".".join([msg_id.encode(), timestamp.encode(), body])
    digest = base64.b64encode(
        hmac.new(SECRET_RAW, signed, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": msg_id,
        "svix-timestamp": timestamp,
        "svix-signature": f"v1,{digest}",
    }


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def test_a_correctly_signed_body_verifies():
    body = json.dumps({"type": "email.received"}).encode()
    assert verify_signature(body, _sign(body)) is True


def test_a_tampered_body_is_refused():
    body = json.dumps({"type": "email.received"}).encode()
    headers = _sign(body)
    assert verify_signature(b'{"type":"evil"}', headers) is False


def test_a_wrong_secret_is_refused():
    body = b"{}"
    headers = _sign(body)
    Config.RESEND_WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"x" * 32).decode()
    assert verify_signature(body, headers) is False


def test_missing_headers_are_refused():
    body = b"{}"
    assert verify_signature(body, {}) is False
    assert verify_signature(body, {"svix-id": "a"}) is False


def test_an_unconfigured_secret_fails_closed():
    """"Not configured" must mean refuse, never trust — this endpoint can
    move a contracted deadline."""
    body = b"{}"
    headers = _sign(body)
    Config.RESEND_WEBHOOK_SECRET = None
    assert verify_signature(body, headers) is False


def test_signature_rotation_is_tolerated():
    """Svix sends several signatures during a secret rotation; matching any
    one of them is enough."""
    body = b"{}"
    headers = _sign(body)
    good = headers["svix-signature"]
    headers["svix-signature"] = f"v1,{base64.b64encode(b'nope').decode()} {good}"
    assert verify_signature(body, headers) is True


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------

def test_a_reply_address_is_minted_once_and_reused():
    first = reply_address_for(CAMPAIGN, CREATOR)
    assert first and first.endswith("@reply.test")
    assert first.startswith("chase+")
    assert reply_address_for(CAMPAIGN, CREATOR) == first


def test_the_reply_address_fits_in_an_email_local_part():
    """RFC 5321 caps a local part at 64 characters; a signed blob would not
    reliably fit, which is why the token is a stored id."""
    address = reply_address_for(CAMPAIGN, CREATOR)
    local = address.split("@")[0]
    assert len(local) <= 64


def test_no_address_is_minted_while_inbound_is_off():
    Config.CHASE_INBOUND_ENABLED = False
    assert reply_address_for(CAMPAIGN, CREATOR) is None


def test_a_reply_is_attributed_by_its_address():
    address = reply_address_for(CAMPAIGN, CREATOR)
    assert resolve_reply_address([address]) == (CAMPAIGN, CREATOR)


def test_the_chase_address_is_found_among_several_recipients():
    address = reply_address_for(CAMPAIGN, CREATOR)
    recipients = ["someone@else.com", f"Jennifer <{address}>", "cc@x.com"]
    assert resolve_reply_address(recipients) == (CAMPAIGN, CREATOR)


def test_an_unknown_address_attributes_to_nothing():
    assert resolve_reply_address(["chase+notatoken@reply.test"]) is None
    assert resolve_reply_address(["hello@example.com"]) is None
    assert resolve_reply_address([]) is None


# ---------------------------------------------------------------------------
# Payload handling
# ---------------------------------------------------------------------------

def test_the_payload_is_read_from_data_or_the_root():
    nested = normalize({"data": {"email_id": "e1", "from": "a@b.c", "to": ["x@y.z"]}})
    assert nested.email_id == "e1"
    flat = normalize({"email_id": "e2", "from": "a@b.c", "to": "x@y.z"})
    assert flat.email_id == "e2"
    assert flat.recipients == ["x@y.z"]


def test_an_unrecognised_payload_is_reported_not_guessed():
    assert normalize({"something": "else"}) is None


def test_our_own_quoted_email_is_stripped_before_reading():
    """Our chase emails talk about dates constantly. Feeding the quoted thread
    to the classifier invites reading our words as the creator's."""
    body = (
        "Posting on Tuesday, sorry for the delay!\n"
        "\n"
        "On Mon, Aug 24 2026, Jennifer wrote:\n"
        "> The deadline for the Reve campaign was 2026-08-10\n"
        "> Could you reply today\n"
    )
    cleaned = strip_quoted(body)
    assert "Posting on Tuesday" in cleaned
    assert "2026-08-10" not in cleaned
    assert ">" not in cleaned


def test_a_signature_block_is_stripped():
    cleaned = strip_quoted("Will post Friday.\n\n--\nSent from my iPhone")
    assert cleaned == "Will post Friday."


# ---------------------------------------------------------------------------
# Sanity bounds on a proposed date
# ---------------------------------------------------------------------------

def test_a_date_in_the_past_is_discarded():
    today = date(2026, 8, 24)
    assert inbound_replies._sane_date("2026-08-01", today) is None


def test_a_date_years_out_is_discarded_as_a_misparse():
    today = date(2026, 8, 24)
    assert inbound_replies._sane_date("2029-01-01", today) is None


def test_a_plausible_date_survives():
    today = date(2026, 8, 24)
    assert inbound_replies._sane_date("2026-09-01", today) == "2026-09-01"
    assert inbound_replies._sane_date(None, today) is None
    assert inbound_replies._sane_date("not a date", today) is None


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

def _payload(address, text=""):
    return {
        "type": "email.received",
        "data": {
            "email_id": "email_123",
            "from": "creator@example.com",
            "to": [address],
            "subject": "Re: Urgent: Reve Content",
            "text": text,
        },
    }


def test_a_reply_reaches_slack_and_pauses_the_chase():
    address = reply_address_for(CAMPAIGN, CREATOR)
    handler = InboundReplyHandler(FakeSlackClient())

    assert handler.handle(_payload(address, "Posting Tuesday, sorry!")) is True
    assert len(handler.client.messages) == 1
    assert CREATOR in handler.client.messages[0]["text"]

    # A reply means they are engaging — the next rung must not go out from
    # under the person now reading it.
    state = chase_ladder.load_state(CAMPAIGN, CREATOR)
    assert state.status == "snoozed"
    assert state.snoozed_until >= chase_ladder.today_local()


def test_an_unreadable_reply_still_reaches_the_team():
    """The failure this feature exists to fix is a creator's answer going
    unseen. A partial post beats a dropped one."""
    address = reply_address_for(CAMPAIGN, CREATOR)
    handler = InboundReplyHandler(FakeSlackClient())

    # No body, no classifier, no campaigns API.
    assert handler.handle(_payload(address, "")) is True
    blocks = json.dumps(handler.client.messages[0]["blocks"])
    assert "could not be read" in blocks


def test_a_reply_we_cannot_attribute_is_ignored():
    handler = InboundReplyHandler(FakeSlackClient())
    assert handler.handle(_payload("stranger@example.com", "hello")) is False
    assert handler.client.messages == []


def test_a_committed_date_is_only_ever_proposed(monkeypatch):
    """The model never moves a deadline. It draws a button; a person presses
    it."""
    address = reply_address_for(CAMPAIGN, CREATOR)
    proposed = (date.today() + timedelta(days=7)).isoformat()
    monkeypatch.setattr(
        inbound_replies, "interpret",
        lambda reply, **kw: {
            "intent": "commits_to_date",
            "proposed_date": proposed,
            "confidence": "high",
            "summary": "Will post next Tuesday.",
        },
    )

    handler = InboundReplyHandler(FakeSlackClient())
    handler.handle(_payload(address, "Posting next Tuesday!"))

    blocks = json.dumps(handler.client.messages[0]["blocks"])
    assert "chase_revision_confirm" in blocks
    assert proposed in blocks
    assert "Nothing has changed yet" in blocks

    # And nothing was written to the deadline anywhere.
    assert handler.api is None


def test_a_low_confidence_reading_says_so_on_the_button_card(monkeypatch):
    address = reply_address_for(CAMPAIGN, CREATOR)
    proposed = (date.today() + timedelta(days=4)).isoformat()
    monkeypatch.setattr(
        inbound_replies, "interpret",
        lambda reply, **kw: {
            "intent": "commits_to_date",
            "proposed_date": proposed,
            "confidence": "low",
            "summary": "Maybe next week.",
        },
    )
    handler = InboundReplyHandler(FakeSlackClient())
    handler.handle(_payload(address, "I'll try for next week maybe"))

    blocks = json.dumps(handler.client.messages[0]["blocks"])
    assert "low" in blocks
    assert "check the message above" in blocks


def test_a_reply_with_no_date_offers_the_brake_instead(monkeypatch):
    address = reply_address_for(CAMPAIGN, CREATOR)
    monkeypatch.setattr(
        inbound_replies, "interpret",
        lambda reply, **kw: {
            "intent": "asks_a_question",
            "proposed_date": None,
            "confidence": "high",
            "summary": "Asked which hashtags to use.",
        },
    )
    handler = InboundReplyHandler(FakeSlackClient())
    handler.handle(_payload(address, "Which hashtags should I use?"))

    blocks = json.dumps(handler.client.messages[0]["blocks"])
    assert "chase_revision_confirm" not in blocks
    assert "chase_stop" in blocks
