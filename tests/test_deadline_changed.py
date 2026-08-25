"""
Tests for the `deadline_changed` webhook the campaigns dashboard fires.

Two things have to happen when a creator's deadline moves: the team hears
about it in Slack, and the chase ladder forgets everything it sent against
the old date. The second is the one with teeth — rung dedup rows record only
*that* a rung went out, never which deadline it was for, so without the reset
a creator who agrees a new date sails past it in total silence.

Run with `python -m pytest tests/test_deadline_changed.py`.
"""

import json
import os
import sys
from datetime import date, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.models import (  # noqa: E402
    ChaseState,
    DeadlineReminder,
    EmailLog,
    SessionLocal,
    init_db,
)
from services import chase_ladder  # noqa: E402
from services.webhook_handler import WebhookHandler  # noqa: E402

init_db()

CAMPAIGN = "camp-dc"
CREATOR = "moved.creator"


class FakeSlackClient:
    def __init__(self):
        self.messages = []

    def chat_postMessage(self, **kwargs):
        self.messages.append(kwargs)
        return {"ok": True, "channel": "C1", "ts": "1.0"}


def _reset():
    db = SessionLocal()
    try:
        for model in (DeadlineReminder, EmailLog, ChaseState):
            db.query(model).filter_by(
                campaign_id=CAMPAIGN, creator_username=CREATOR,
            ).delete()
        db.commit()
    finally:
        db.close()
    return WebhookHandler(FakeSlackClient())


def _chased_through_two_rungs():
    """The state a creator is in after the first two rungs have gone out."""
    db = SessionLocal()
    try:
        for rung in ("overdue", "overdue_2"):
            db.add(DeadlineReminder(
                campaign_id=CAMPAIGN, creator_username=CREATOR, reminder_type=rung,
            ))
            db.add(EmailLog(
                recipient_email="moved@example.com",
                template_type=f"deadline_{rung}",
                campaign_id=CAMPAIGN,
                creator_username=CREATOR,
            ))
        db.commit()
    finally:
        db.close()


def _payload(**overrides):
    payload = {
        "event": "deadline_changed",
        "campaign": {
            "id": CAMPAIGN,
            "name": "Reve Features",
            "brandName": "Reve",
            "slug": "reve/reve-features",
        },
        "creator": {
            "username": CREATOR,
            "email": "moved@example.com",
            "deadline": "2026-09-02",
            "previousDeadline": "2026-08-10",
        },
        "change": {
            "from": "2026-08-10",
            "to": "2026-09-02",
            "source": "bot",
            "actor": CREATOR,
            "reason": "Creator confirmed in chat: posting next Tuesday",
        },
    }
    payload.update(overrides)
    return payload


def _blocks(message):
    return json.dumps(message["blocks"])


# ---------------------------------------------------------------------------
# Telling the team
# ---------------------------------------------------------------------------

def test_the_change_is_announced_with_both_dates():
    handler = _reset()
    assert handler.handle_event(_payload()) is True

    assert len(handler.client.messages) == 1
    blocks = _blocks(handler.client.messages[0])
    assert "Deadline Changed" in blocks
    assert "2026-08-10" in blocks
    assert "2026-09-02" in blocks


def test_a_creator_agreed_change_says_where_it_came_from():
    handler = _reset()
    handler.handle_event(_payload())

    blocks = _blocks(handler.client.messages[0])
    assert "a creator reply" in blocks
    assert "posting next Tuesday" in blocks


def test_an_admin_edit_is_labelled_as_one():
    handler = _reset()
    payload = _payload()
    payload["change"] = {
        "from": "2026-08-10", "to": "2026-09-02",
        "source": "admin", "actor": "Tharun R", "reason": None,
    }
    handler.handle_event(payload)

    blocks = _blocks(handler.client.messages[0])
    assert "the dashboard" in blocks
    assert "Tharun R" in blocks


def test_an_event_without_a_campaign_id_is_rejected():
    handler = _reset()
    payload = _payload()
    payload["campaign"] = {"name": "Reve Features"}
    assert handler.handle_event(payload) is False
    assert handler.client.messages == []


# ---------------------------------------------------------------------------
# Resetting the ladder
# ---------------------------------------------------------------------------

def test_the_rungs_already_sent_are_forgotten():
    handler = _reset()
    _chased_through_two_rungs()
    handler.handle_event(_payload())

    db = SessionLocal()
    try:
        assert db.query(DeadlineReminder).filter_by(
            campaign_id=CAMPAIGN, creator_username=CREATOR,
        ).count() == 0
        assert db.query(EmailLog).filter_by(
            campaign_id=CAMPAIGN, creator_username=CREATOR,
        ).count() == 0
    finally:
        db.close()


def test_the_new_deadline_gets_a_real_chase_rather_than_silence():
    """The whole point. Rung rows don't record which deadline they were for,
    so leaving them in place would let the new date pass unchased."""
    handler = _reset()
    _chased_through_two_rungs()

    creator = {
        "username": CREATOR,
        "email": "moved@example.com",
        "campaign_id": CAMPAIGN,
        "campaign_name": "Reve Features",
        "brand_name": "Reve",
        "deadline": (chase_ladder.today_local() - timedelta(days=1)).isoformat(),
        "deliverables": {
            "minVideos": 2, "minViews": None, "actualVideos": 0,
            "videosComplete": False, "viewsComplete": True, "allComplete": False,
        },
        "videos": [], "reviews": [], "totalVideosPosted": 0,
    }

    handler.handle_event(_payload())

    # Day one past the new date: the first rung is due again and nothing in
    # the log says it was already sent.
    decision = chase_ladder.decide(creator)
    assert decision.rung == chase_ladder.RUNG_OVERDUE

    db = SessionLocal()
    try:
        assert db.query(EmailLog).filter_by(
            campaign_id=CAMPAIGN,
            creator_username=CREATOR,
            template_type="deadline_overdue",
        ).first() is None
    finally:
        db.close()


def test_a_new_date_lifts_a_stop_and_says_so():
    handler = _reset()
    chase_ladder.set_state(CAMPAIGN, CREATOR, status="stopped", set_by="U1")
    handler.handle_event(_payload())

    state = chase_ladder.load_state(CAMPAIGN, CREATOR)
    assert state.status == "active"
    assert state.snoozed_until is None
    assert "lifted" in _blocks(handler.client.messages[0])


def test_the_held_clock_is_cleared_for_the_new_date():
    handler = _reset()
    db = SessionLocal()
    try:
        db.add(ChaseState(
            campaign_id=CAMPAIGN, creator_username=CREATOR,
            status="active", held_days=6, held_last_date=date(2026, 3, 8),
        ))
        db.commit()
    finally:
        db.close()

    handler.handle_event(_payload())

    state = chase_ladder.load_state(CAMPAIGN, CREATOR)
    assert state.held_days == 0
    assert state.held_last_date is None


def test_only_deadline_emails_are_cleared():
    """An approval or chat notice already sent is unrelated to the deadline
    and must not be re-sent because a date moved."""
    handler = _reset()
    db = SessionLocal()
    try:
        db.add(EmailLog(
            recipient_email="moved@example.com",
            template_type="video_approved",
            campaign_id=CAMPAIGN,
            creator_username=CREATOR,
        ))
        db.commit()
    finally:
        db.close()

    handler.handle_event(_payload())

    db = SessionLocal()
    try:
        assert db.query(EmailLog).filter_by(
            campaign_id=CAMPAIGN,
            creator_username=CREATOR,
            template_type="video_approved",
        ).first() is not None
    finally:
        db.close()


def test_another_creators_chase_is_untouched():
    handler = _reset()
    db = SessionLocal()
    try:
        db.add(DeadlineReminder(
            campaign_id=CAMPAIGN,
            creator_username="someone.else",
            reminder_type="overdue",
        ))
        db.commit()
    finally:
        db.close()

    handler.handle_event(_payload())

    db = SessionLocal()
    try:
        assert db.query(DeadlineReminder).filter_by(
            campaign_id=CAMPAIGN, creator_username="someone.else",
        ).count() == 1
        db.query(DeadlineReminder).filter_by(
            creator_username="someone.else",
        ).delete()
        db.commit()
    finally:
        db.close()
