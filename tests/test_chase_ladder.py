"""
Tests for the post-deadline chase ladder in services/chase_ladder.py.

The ladder decides who gets chased, how hard, and — more importantly — who
does not. Most of these cases are about staying quiet: a creator who is
already moving, one whose drafts are sitting with the brand, one whose only
shortfall is views they cannot hurry along.

Dates are fixed rather than relative to today so the weekend-shift cases mean
the same thing every day of the week. 2026-03-02 is a Monday, which puts the
D+1 / D+3 / D+7 / D+10 rungs on Tue / Thu / Mon / Thu — all working days,
so a test that isn't about the weekend never trips over one.

Run with `python -m pytest tests/test_chase_ladder.py`.
"""

import os
import sys
from datetime import date, datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config  # noqa: E402
from models.models import (  # noqa: E402
    ChaseState,
    ReviewSubmission,
    SessionLocal,
    init_db,
)
from services import chase_ladder  # noqa: E402
from services.chase_ladder import (  # noqa: E402
    RUNG_FINAL,
    RUNG_OVERDUE,
    RUNG_SECOND,
    RUNG_THIRD,
    decide,
    next_business_day,
    rung_days,
    rung_due_dates,
    within_send_window,
)

init_db()

# A Monday, so every rung lands on a working day.
DEADLINE = date(2026, 3, 2)
# The same week, but a Friday — D+1 falls on a Saturday.
FRIDAY_DEADLINE = date(2026, 3, 6)


def _reset():
    db = SessionLocal()
    try:
        db.query(ChaseState).delete()
        db.query(ReviewSubmission).delete()
        db.commit()
    finally:
        db.close()


def _creator(**overrides):
    """A creator who owes 2 videos, has posted none, and is past their date."""
    creator = {
        "username": "tharun.fyi",
        "email": "tharun@example.com",
        "campaign_id": "camp1",
        "campaign_name": "Reve Features",
        "brand_name": "Reve",
        "deadline": DEADLINE.isoformat(),
        "deliverables": {
            "minVideos": 2,
            "minViews": None,
            "actualVideos": 0,
            "actualViews": 0,
            "videosComplete": False,
            "viewsComplete": True,
            "allComplete": False,
        },
        "videos": [],
        "reviews": [],
        "totalVideosPosted": 0,
    }
    deliverables = overrides.pop("deliverables", None)
    if deliverables:
        creator["deliverables"].update(deliverables)
    creator.update(overrides)
    return creator


def _at(days):
    """The calendar date `days` after the deadline."""
    return DEADLINE + timedelta(days=days)


# ---------------------------------------------------------------------------
# Nothing due
# ---------------------------------------------------------------------------

def test_no_deadline_is_never_chased():
    _reset()
    decision = decide(_creator(deadline=None), today=_at(30))
    assert decision.rung is None
    assert "no deadline" in decision.skip_reason


def test_unparseable_deadline_is_never_chased():
    _reset()
    decision = decide(_creator(deadline="not-a-date"), today=_at(30))
    assert decision.rung is None


def test_deadline_day_itself_is_not_overdue():
    _reset()
    assert decide(_creator(), today=DEADLINE).rung is None


def test_day_before_first_rung_is_quiet():
    _reset()
    # D+1 is the first rung, so nothing is due while raw_days is 0.
    assert decide(_creator(), today=_at(0)).rung is None


def test_completed_deliverables_end_the_chase():
    _reset()
    creator = _creator(deliverables={"allComplete": True})
    decision = decide(creator, today=_at(10))
    assert decision.rung is None
    assert "complete" in decision.skip_reason


# ---------------------------------------------------------------------------
# The four rungs
# ---------------------------------------------------------------------------

def test_first_rung_keeps_the_legacy_overdue_name():
    """The pre-existing tier was called `overdue`; renaming it would re-email
    everyone already mid-chase on the deploy that ships this."""
    _reset()
    decision = decide(_creator(), today=_at(1))
    assert decision.rung == RUNG_OVERDUE
    assert decision.email is True
    assert decision.days_overdue == 1


def test_second_rung_at_day_three():
    _reset()
    decision = decide(_creator(), today=_at(3))
    assert decision.rung == RUNG_SECOND
    assert decision.email is True


def test_third_rung_at_day_seven():
    _reset()
    decision = decide(_creator(), today=_at(7))
    assert decision.rung == RUNG_THIRD
    assert decision.email is True


def test_final_rung_sends_no_creator_email():
    _reset()
    decision = decide(_creator(), today=_at(10))
    assert decision.rung == RUNG_FINAL
    assert decision.email is False
    assert decision.is_final
    assert "person" in decision.email_note


def test_between_rungs_holds_at_the_last_one_reached():
    _reset()
    # Day 5 is past D+3 but not yet D+7 — the second rung is still the
    # highest due, and its dedup row keeps it from sending twice.
    assert decide(_creator(), today=_at(5)).rung == RUNG_SECOND


def test_long_overdue_creator_gets_only_the_final_rung():
    """The blast guard: a creator 30 days late when this ships must not
    receive all four rungs in one poll."""
    _reset()
    decision = decide(_creator(), today=_at(30))
    assert decision.rung == RUNG_FINAL
    assert decision.email is False


def test_ladder_stops_after_the_final_rung():
    _reset()
    # Far past D+10 the answer is still the final rung — deduped, so it
    # fires once and the automation is then finished.
    assert decide(_creator(), today=_at(120)).rung == RUNG_FINAL


# ---------------------------------------------------------------------------
# The brake
# ---------------------------------------------------------------------------

def test_stopped_chase_sends_nothing():
    _reset()
    chase_ladder.set_state("camp1", "tharun.fyi", status="stopped", set_by="U1")
    decision = decide(_creator(), today=_at(7))
    assert decision.rung is None
    assert "stopped" in decision.skip_reason


def test_snooze_holds_until_its_date_passes():
    _reset()
    chase_ladder.set_state(
        "camp1", "tharun.fyi", status="snoozed", snoozed_until=_at(9),
    )
    assert decide(_creator(), today=_at(7)).rung is None
    # The day after the snooze expires, the ladder picks up again.
    assert decide(_creator(), today=_at(10)).rung == RUNG_FINAL


def test_snooze_without_a_date_holds_indefinitely():
    _reset()
    chase_ladder.set_state("camp1", "tharun.fyi", status="snoozed")
    assert decide(_creator(), today=_at(30)).rung is None


# ---------------------------------------------------------------------------
# Not the creator's move
# ---------------------------------------------------------------------------

def test_recent_activity_pauses_the_chase():
    _reset()
    posted_at = int(
        datetime(_at(6).year, _at(6).month, _at(6).day, 12).timestamp() * 1000
    )
    creator = _creator(reviews=[{"videoLink": "https://x/1", "submittedAt": posted_at}])
    decision = decide(creator, today=_at(7))
    assert decision.rung is None
    assert "active" in decision.skip_reason


def test_stale_activity_does_not_pause_the_chase():
    _reset()
    long_ago = int(
        datetime(DEADLINE.year, DEADLINE.month, DEADLINE.day, 12).timestamp() * 1000
    )
    creator = _creator(reviews=[{"videoLink": "https://x/1", "submittedAt": long_ago}])
    # 7 days later that draft is well outside the activity window, but it
    # still covers the work — so a rung is due with the email held.
    decision = decide(creator, today=_at(7))
    assert decision.rung is not None


def test_views_short_but_videos_done_never_emails_the_creator():
    """Views accrue on their own. Chasing someone for arithmetic they can't
    affect is the mis-target the old single overdue email made."""
    _reset()
    creator = _creator(
        deliverables={
            "minVideos": 2,
            "minViews": 200000,
            "actualVideos": 2,
            "actualViews": 10000,
            "videosComplete": True,
            "viewsComplete": False,
            "allComplete": False,
        },
        totalVideosPosted=2,
    )
    decision = decide(creator, today=_at(3))
    assert decision.rung == RUNG_SECOND
    assert decision.email is False
    assert "view target" in decision.email_note


def test_missing_email_address_still_raises_the_slack_alert():
    _reset()
    decision = decide(_creator(email=None), today=_at(3))
    assert decision.rung == RUNG_SECOND
    assert decision.email is False
    assert "No email" in decision.email_note


# ---------------------------------------------------------------------------
# The clock hold
# ---------------------------------------------------------------------------

def _covered_creator():
    """
    Two drafts shared before the deadline and still unanswered, none posted,
    two owed — squarely the brand's move.

    The timestamps sit well before the deadline on purpose. A draft shared in
    the last few days would trip the activity check first and skip for that
    reason instead, which is correct behaviour but tests nothing about the
    hold.
    """
    shared_on = DEADLINE - timedelta(days=10)
    long_ago = int(
        datetime(shared_on.year, shared_on.month, shared_on.day, 12).timestamp() * 1000
    )
    return _creator(
        reviews=[
            {"videoLink": "https://x/1", "submittedAt": long_ago},
            {"videoLink": "https://x/2", "submittedAt": long_ago},
        ],
    )


def test_coverage_holds_the_email_but_still_names_a_rung():
    _reset()
    decision = decide(_covered_creator(), today=_at(3))
    assert decision.rung is not None
    assert decision.email is False
    assert "in review" in decision.email_note


def test_each_held_day_is_charged_once_no_matter_how_often_we_poll():
    """The 60-second poll must not outrun the calendar — otherwise the hold
    would overtake the deadline within the hour and the ladder would never
    advance again."""
    _reset()
    creator = _covered_creator()
    for _ in range(20):
        decide(creator, today=_at(3))

    db = SessionLocal()
    try:
        state = db.query(ChaseState).filter_by(
            campaign_id="camp1", creator_username="tharun.fyi",
        ).first()
        assert state.held_days == 1
        assert state.held_last_date == _at(3)
    finally:
        db.close()


def test_the_ladder_resumes_where_it_paused_rather_than_jumping():
    _reset()
    held = _covered_creator()
    # Days 1 through 6: the brand owes a decision, so nothing fires.
    for day in range(1, 7):
        assert decide(held, today=_at(day)).rung is None

    # On day 7 the brand sends the drafts back and the ball returns to the
    # creator. Day 7 is the third rung on the wall calendar, but six days
    # were held — so the effective count is 1 and they get the *first*
    # rung, not a final-notice-adjacent escalation for a stalled review.
    resumed = _creator()
    decision = decide(resumed, today=_at(7))
    assert decision.raw_days_overdue == 7
    assert decision.days_overdue == 1
    assert decision.rung == RUNG_OVERDUE


def test_hold_can_pause_the_ladder_entirely():
    _reset()
    # One day overdue, that day held — nothing is due at all.
    decision = decide(_covered_creator(), today=_at(1))
    assert decision.rung is None
    assert "held" in decision.skip_reason


# ---------------------------------------------------------------------------
# Calendar mechanics
# ---------------------------------------------------------------------------

def test_weekend_rungs_slide_to_monday():
    _reset()
    saturday = date(2026, 3, 7)
    sunday = date(2026, 3, 8)
    monday = date(2026, 3, 9)
    assert next_business_day(saturday) == monday
    assert next_business_day(sunday) == monday
    assert next_business_day(monday) == monday


def test_a_rung_landing_on_a_weekend_waits_rather_than_being_lost():
    _reset()
    creator = _creator(deadline=FRIDAY_DEADLINE.isoformat())
    # D+1 is Saturday the 7th: nothing goes out.
    assert decide(creator, today=date(2026, 3, 7)).rung is None
    # It arrives on the Monday instead.
    assert decide(creator, today=date(2026, 3, 9)).rung == RUNG_OVERDUE


def test_a_weekend_shift_never_collapses_two_rungs_onto_one_day():
    """A Friday deadline puts D+1 on the Saturday and D+3 on the Monday. If
    both shift to that Monday, the highest-due-rung rule eats the first
    notice and the creator's opening chase is a second nudge."""
    due = dict(rung_due_dates(FRIDAY_DEADLINE))
    assert due[RUNG_OVERDUE] == date(2026, 3, 9)    # Saturday -> Monday
    assert due[RUNG_SECOND] == date(2026, 3, 10)    # pushed past it, not merged
    dates = [d for _key, d in rung_due_dates(FRIDAY_DEADLINE)]
    assert len(set(dates)) == len(dates)
    assert dates == sorted(dates)


def test_rung_due_dates_are_all_working_days():
    for _key, due in rung_due_dates(FRIDAY_DEADLINE):
        assert due.weekday() < 5


def test_send_window_excludes_the_small_hours():
    tz = chase_ladder.chase_timezone()
    assert within_send_window(datetime(2026, 3, 3, 10, 0, tzinfo=tz)) is True
    assert within_send_window(datetime(2026, 3, 3, 0, 1, tzinfo=tz)) is False
    assert within_send_window(datetime(2026, 3, 3, 23, 0, tzinfo=tz)) is False
    # The end hour is exclusive, so 17:00 itself is outside the window.
    assert within_send_window(datetime(2026, 3, 3, 17, 0, tzinfo=tz)) is False


def test_us_pacific_zone_resolves():
    """If tzdata is missing from the image this silently falls back to UTC
    and every creator is chased three hours early."""
    assert str(chase_ladder.chase_timezone()) == "America/Los_Angeles"


# ---------------------------------------------------------------------------
# Cadence config
# ---------------------------------------------------------------------------

def test_default_cadence():
    assert rung_days() == (1, 3, 7, 10)


def test_cadence_is_configurable():
    original = Config.CHASE_RUNG_DAYS
    try:
        Config.CHASE_RUNG_DAYS = "2,5,9,14"
        assert rung_days() == (2, 5, 9, 14)
    finally:
        Config.CHASE_RUNG_DAYS = original


def test_a_typo_in_the_cadence_variable_does_not_stop_the_chase():
    original = Config.CHASE_RUNG_DAYS
    try:
        for bad in ("1,3,seven,10", "1,3", "10,3,7,1", "0,3,7,10", ""):
            Config.CHASE_RUNG_DAYS = bad
            assert rung_days() == (1, 3, 7, 10), bad
    finally:
        Config.CHASE_RUNG_DAYS = original
