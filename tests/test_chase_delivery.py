"""
End-to-end tests for delivering a post-deadline chase rung.

services/chase_ladder.py decides *which* rung is due; these cover what the
scheduler then does with that answer — who gets emailed, what the team sees in
Slack, and what happens on the second poll a minute later.

The two dedup paths are deliberately independent and are tested as such: the
Slack alert is posted once, while the email is retried every tick until Resend
accepts it, so an outage never costs a creator their notice.

Run with `python -m pytest tests/test_chase_delivery.py`.
"""

import json
import os
import sys

import pytest
from datetime import timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config  # noqa: E402
from models.models import (  # noqa: E402
    ChaseState,
    ChatSpace,
    DeadlineReminder,
    EmailLog,
    SessionLocal,
    init_db,
)
from services import chase_ladder  # noqa: E402
from services.email_service import EmailSendResult  # noqa: E402
from services.scheduler_service import SchedulerService  # noqa: E402

init_db()


class FakeSlackClient:
    def __init__(self):
        self.messages = []

    def chat_postMessage(self, **kwargs):
        self.messages.append(kwargs)
        return {"ok": True, "channel": "C1", "ts": "1.0"}


class FakeEmailService:
    """
    Stands in for EmailService with the same dedup contract: check the log
    first, only write a row on a successful send, and report which of the
    three outcomes happened. Faking a looser contract than the real one would
    let the scheduler pass here and double-email in production.

    `sends` records genuine attempts; `skipped` records calls the log
    already covered.
    """

    def __init__(self):
        self.sends = []
        self.skipped = []
        self.result = EmailSendResult.SENT

    def send_followup_if_not_sent(self, **kwargs):
        db = SessionLocal()
        try:
            existing = db.query(EmailLog).filter_by(
                recipient_email=kwargs["to_email"],
                template_type=kwargs["template_type"],
                campaign_id=kwargs["campaign_id"],
                creator_username=kwargs["creator_username"],
            ).first()
            if existing is not None:
                self.skipped.append(kwargs)
                return EmailSendResult.ALREADY_SENT

            self.sends.append(kwargs)
            if self.result is not EmailSendResult.SENT:
                # No row on failure — that is what makes the retry work.
                return self.result

            db.add(EmailLog(
                recipient_email=kwargs["to_email"],
                template_type=kwargs["template_type"],
                campaign_id=kwargs["campaign_id"],
                creator_username=kwargs["creator_username"],
            ))
            db.commit()
            return EmailSendResult.SENT
        finally:
            db.close()


CREATOR = "tharun.fyi"
CAMPAIGN = "camp1"


def _fresh():
    """
    Clear only this module's own fixture rows.

    The suite shares one in-memory database across test modules, so a blanket
    `delete()` here deletes chat spaces other modules built during import and
    fails them depending on collection order.
    """
    db = SessionLocal()
    try:
        for model in (DeadlineReminder, EmailLog, ChaseState):
            db.query(model).filter_by(
                campaign_id=CAMPAIGN, creator_username=CREATOR,
            ).delete()
        db.query(ChatSpace).filter_by(creator_username=CREATOR).delete()
        db.commit()
    finally:
        db.close()
    slack, email = FakeSlackClient(), FakeEmailService()
    return SchedulerService(slack, email, reelstats_api=None), slack, email


def _creator(days_overdue, *, min_videos=2, posted=0, email="tharun@example.com"):
    """A creator whose deadline was `days_overdue` days ago, in the chase zone."""
    deadline = chase_ladder.today_local() - timedelta(days=days_overdue)
    return {
        "username": "tharun.fyi",
        "email": email,
        "campaign_id": "camp1",
        "campaign_name": "Reve Features",
        "campaign_slug": "reve/reve-features",
        "brand_name": "Reve",
        "deadline": deadline.isoformat(),
        "deliverables": {
            "minVideos": min_videos,
            "minViews": None,
            "actualVideos": posted,
            "videosComplete": posted >= min_videos,
            "viewsComplete": True,
            "allComplete": False,
        },
        "videos": [],
        "reviews": [],
        "totalVideosPosted": posted,
    }


def _blocks(message):
    return json.dumps(message["blocks"])


@pytest.fixture(autouse=True)
def _chase_test_config():
    """
    Pin the settings these tests depend on, and put them back afterwards.

    Config attributes are process-global, so both halves matter. Setting them
    here rather than reading the shell keeps the tests hermetic — the chat
    link needs a base URL and a signing key to mint a token, and taking those
    from the environment would make the suite pass or fail on how it was
    invoked. Restoring them matters just as much: an open send window breaks
    the window test in the ladder suite, and a pinned base URL breaks the
    chat route tests, which derive theirs from the request.
    """
    saved = (
        Config.CHASE_SEND_HOUR_START,
        Config.CHASE_SEND_HOUR_END,
        Config.PUBLIC_BASE_URL,
        Config.CHAT_SECRET_KEY,
    )
    Config.CHASE_SEND_HOUR_START, Config.CHASE_SEND_HOUR_END = 0, 24
    Config.PUBLIC_BASE_URL = "https://bot.test"
    Config.CHAT_SECRET_KEY = Config.CHAT_SECRET_KEY or "test-chat-secret"
    yield
    (
        Config.CHASE_SEND_HOUR_START,
        Config.CHASE_SEND_HOUR_END,
        Config.PUBLIC_BASE_URL,
        Config.CHAT_SECRET_KEY,
    ) = saved


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def test_first_rung_emails_the_creator_and_alerts_the_team():
    scheduler, slack, email = _fresh()
    scheduler.check_deadline_reminder_for(_creator(1))

    assert len(email.sends) == 1
    assert email.sends[0]["template_type"] == "deadline_overdue"
    assert len(slack.messages) == 1
    assert "Deadline Overdue" in _blocks(slack.messages[0])


def test_an_already_sent_overdue_email_is_not_sent_again_after_the_upgrade():
    """A creator mid-chase when this deploys already has a `deadline_overdue`
    row from the old single-email code. The first rung keeps that exact
    template type so the row still counts and they are not re-emailed."""
    scheduler, _slack, email = _fresh()
    db = SessionLocal()
    try:
        db.add(EmailLog(
            recipient_email="tharun@example.com",
            template_type="deadline_overdue",
            campaign_id="camp1",
            creator_username="tharun.fyi",
        ))
        db.commit()
    finally:
        db.close()

    scheduler.check_deadline_reminder_for(_creator(1))
    assert email.sends == []
    assert len(email.skipped) == 1


def test_second_rung_carries_the_delivery_gap():
    scheduler, slack, email = _fresh()
    scheduler.check_deadline_reminder_for(_creator(3, min_videos=2, posted=1))

    assert email.sends[0]["template_type"] == "deadline_overdue_2"
    body = email.sends[0]["template_data"]["body"]
    assert "1 of 2 videos live" in body


def test_every_chase_email_carries_the_chat_link():
    """Resend cannot read replies, so each email points at the one place a
    reply lands somewhere the system can act on."""
    scheduler, _slack, email = _fresh()
    scheduler.check_deadline_reminder_for(_creator(3))

    body = email.sends[0]["template_data"]["body"]
    assert "/chat/invite/" in body


def test_a_chat_space_is_opened_for_a_creator_who_never_submitted():
    """The creator being chased hardest has no review, so the review flow
    would never have opened them a space."""
    scheduler, _slack, _email = _fresh()
    scheduler.check_deadline_reminder_for(_creator(3))

    db = SessionLocal()
    try:
        space = db.query(ChatSpace).filter_by(creator_username="tharun.fyi").one()
        assert space.latest_review_id is None
        assert space.campaign_name == "Reve Features"
    finally:
        db.close()


def test_final_rung_alerts_the_team_and_emails_nobody():
    scheduler, slack, email = _fresh()
    scheduler.check_deadline_reminder_for(_creator(10))

    assert email.sends == []
    assert len(slack.messages) == 1
    blocks = _blocks(slack.messages[0])
    assert "Automated Chase Exhausted" in blocks
    assert "needs a person" in blocks


def test_the_brake_buttons_ride_along_with_every_post_deadline_alert():
    scheduler, slack, _email = _fresh()
    scheduler.check_deadline_reminder_for(_creator(1))

    blocks = _blocks(slack.messages[0])
    assert "chase_snooze_3d" in blocks
    assert "chase_snooze_7d" in blocks
    assert "chase_stop" in blocks


# ---------------------------------------------------------------------------
# Dedup and repeat polls
# ---------------------------------------------------------------------------

def test_a_rung_is_announced_once_however_often_we_poll():
    scheduler, slack, email = _fresh()
    creator = _creator(3)
    for _ in range(5):
        scheduler.check_deadline_reminder_for(creator)

    assert len(slack.messages) == 1
    assert len(email.sends) == 1


def test_a_failed_send_is_retried_on_the_next_poll():
    """Resend being down must not cost a creator their notice — no EmailLog
    row is written on failure, so the next tick tries again."""
    scheduler, _slack, email = _fresh()
    email.result = EmailSendResult.FAILED
    creator = _creator(3)

    scheduler.check_deadline_reminder_for(creator)
    scheduler.check_deadline_reminder_for(creator)
    assert len(email.sends) == 2

    email.result = EmailSendResult.SENT
    scheduler.check_deadline_reminder_for(creator)
    assert len(email.sends) == 3
    # Now it stuck, so we stop.
    scheduler.check_deadline_reminder_for(creator)
    assert len(email.sends) == 3


def test_the_ladder_walks_rung_by_rung_as_the_days_pass():
    scheduler, slack, email = _fresh()

    for day in (1, 3, 7, 10):
        # "Today" is fixed, so the passage of time is simulated by moving the
        # deadline further back rather than by faking the clock.
        creator = _creator(day)
        scheduler.check_deadline_reminder_for(creator)

    assert [s["template_type"] for s in email.sends] == [
        "deadline_overdue", "deadline_overdue_2", "deadline_overdue_3",
    ]
    # Four Slack alerts — the final rung posts without an email.
    assert len(slack.messages) == 4


# ---------------------------------------------------------------------------
# Staying quiet
# ---------------------------------------------------------------------------

def test_outside_the_send_window_nothing_goes_out_yet():
    scheduler, slack, email = _fresh()
    # An empty window — never in hours. The autouse fixture reopens it after.
    Config.CHASE_SEND_HOUR_START = 9
    Config.CHASE_SEND_HOUR_END = 9
    scheduler.check_deadline_reminder_for(_creator(3))
    assert email.sends == []
    assert slack.messages == []

    Config.CHASE_SEND_HOUR_START, Config.CHASE_SEND_HOUR_END = 0, 24
    # Nothing was recorded, so the rung is still owed once hours resume.
    scheduler.check_deadline_reminder_for(_creator(3))
    assert len(email.sends) == 1


def test_a_stopped_chase_delivers_nothing():
    scheduler, slack, email = _fresh()
    chase_ladder.set_state("camp1", "tharun.fyi", status="stopped", set_by="U1")
    scheduler.check_deadline_reminder_for(_creator(7))

    assert email.sends == []
    assert slack.messages == []


def test_a_creator_short_only_on_views_is_never_emailed():
    scheduler, slack, email = _fresh()
    creator = _creator(3, min_videos=2, posted=2)
    creator["deliverables"].update({
        "minViews": 200000,
        "actualViews": 1000,
        "viewsComplete": False,
        "videosComplete": True,
    })
    scheduler.check_deadline_reminder_for(creator)

    assert email.sends == []
    assert len(slack.messages) == 1
    assert "view target" in _blocks(slack.messages[0])


def test_a_creator_with_no_email_still_reaches_the_team():
    scheduler, slack, email = _fresh()
    scheduler.check_deadline_reminder_for(_creator(3, email=None))

    assert email.sends == []
    assert len(slack.messages) == 1
    assert "No email" in _blocks(slack.messages[0])


# ---------------------------------------------------------------------------
# Pre-deadline reminders are untouched
# ---------------------------------------------------------------------------

def test_pre_deadline_reminders_still_work():
    scheduler, slack, email = _fresh()
    creator = _creator(1)
    creator["deadline"] = (chase_ladder.today_local() + timedelta(days=1)).isoformat()
    scheduler.check_deadline_reminder_for(creator)

    assert email.sends[0]["template_type"] == "deadline_1_day"
    assert len(slack.messages) == 1
    # The brake belongs to the chase, not to a friendly reminder.
    assert "chase_stop" not in _blocks(slack.messages[0])


def test_the_deadline_day_itself_sends_nothing_new():
    scheduler, slack, email = _fresh()
    creator = _creator(0)
    scheduler.check_deadline_reminder_for(creator)
    # Day zero is the 1_day tier, not a chase rung.
    assert email.sends[0]["template_type"] == "deadline_1_day"
