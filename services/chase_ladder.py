"""
Which post-deadline chase step, if any, is a creator due for today?

The deadline reminders that run before the deadline answer "how close is it".
Once the date has passed that question stops being useful — the creator is
late, and what matters is how long they have been late and whether it is
still their move. This module answers that, and nothing else: it reads a
creator dict and returns a decision. Sending is the scheduler's job.

Four rungs at D+1, D+3, D+7 and D+10, and then the automation is finished.
The first keeps the name ``overdue`` that the single pre-existing overdue
tier already used, so the reminder rows and email-log rows written before
this module existed still dedup rung one and nobody mid-chase is re-emailed
on the deploy that ships it.

Three rules shape when a rung actually goes out:

**The highest due rung wins, not every due rung.** A creator who is thirty
days late the day this ships must get one final notice, not four emails in a
minute. Because dedup is per rung name, walking the whole ladder would fire
every unsent rung at once for anyone already past D+10 — so the ladder picks
the last rung whose day has arrived and leaves the earlier ones alone. A
creator moving through it normally still sees each rung in turn: on D+3 the
highest due rung is the second, and the first was sent on D+1.

**The clock holds while the ball is with the brand.** ``review_coverage``
already decides that a creator whose drafts cover what they owe should not be
emailed. Post-deadline that is not enough: four days of brand silence would
still march them to a final notice for work they cannot do. Each held day
increments ``ChaseState.held_days`` and is subtracted from the day count, so
the ladder resumes where it paused instead of jumping two rungs at once.

**A missing target is not the creator's fault.** A creator who has posted
every video they owe and is only short on views has nothing left to act on —
views accrue on their own. They read as incomplete, and the old single
overdue email chased them for it. Here they are Slack-only: the team hears
about the shortfall, the creator does not get a nag for arithmetic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import Config
from models.models import ChaseState, SessionLocal
from services.review_coverage import review_coverage

logger = logging.getLogger(__name__)

# Rung identity. `key` is both the Slack dedup `reminder_type` and the tail of
# the `deadline_<key>` email template type, so renaming one renames both.
RUNG_OVERDUE = "overdue"
RUNG_SECOND = "overdue_2"
RUNG_THIRD = "overdue_3"
RUNG_FINAL = "overdue_final"

RUNG_KEYS = (RUNG_OVERDUE, RUNG_SECOND, RUNG_THIRD, RUNG_FINAL)

# The last rung hands the creator to a person and sends them no email.
RUNG_EMAILS = {
    RUNG_OVERDUE: True,
    RUNG_SECOND: True,
    RUNG_THIRD: True,
    RUNG_FINAL: False,
}

_DEFAULT_RUNG_DAYS = (1, 3, 7, 10)


def rung_days() -> tuple[int, ...]:
    """
    Day offsets for the four rungs, from Config, falling back to the built-in
    cadence when the variable is malformed. A typo in a Railway variable must
    not take the chase down — it degrades to the documented default and says
    so in the log.
    """
    raw = (Config.CHASE_RUNG_DAYS or "").strip()
    if not raw:
        return _DEFAULT_RUNG_DAYS
    try:
        days = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    except ValueError:
        logger.error(
            "CHASE_RUNG_DAYS=%r is not a comma-separated list of integers; "
            "falling back to %s", raw, _DEFAULT_RUNG_DAYS,
        )
        return _DEFAULT_RUNG_DAYS
    if len(days) != len(RUNG_KEYS):
        logger.error(
            "CHASE_RUNG_DAYS=%r has %d entries, expected %d; falling back to %s",
            raw, len(days), len(RUNG_KEYS), _DEFAULT_RUNG_DAYS,
        )
        return _DEFAULT_RUNG_DAYS
    if list(days) != sorted(days) or days[0] < 1:
        logger.error(
            "CHASE_RUNG_DAYS=%r must ascend and start at 1 or more; "
            "falling back to %s", raw, _DEFAULT_RUNG_DAYS,
        )
        return _DEFAULT_RUNG_DAYS
    return days


def chase_timezone() -> ZoneInfo:
    """
    The zone every "today" in the ladder is read in. An unknown zone name
    would otherwise raise on the poll thread and silently stop all chasing,
    so it falls back to UTC loudly instead.
    """
    name = Config.CHASE_TIMEZONE or "America/Los_Angeles"
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.error(
            "CHASE_TIMEZONE=%r could not be loaded (is the tzdata package "
            "installed?); falling back to UTC", name,
        )
        return ZoneInfo("UTC")


def now_local() -> datetime:
    """Current time in the chase zone."""
    return datetime.now(chase_timezone())


def today_local() -> date:
    """Today's calendar date in the chase zone."""
    return now_local().date()


def within_send_window(moment: Optional[datetime] = None) -> bool:
    """
    Is it a reasonable hour to send a chase? The poll ticks every minute, so
    without this a rung goes out the instant its date rolls over — a final
    notice timestamped 12:01am, which reads as automated at exactly the moment
    we want it to read as deliberate.
    """
    moment = moment or now_local()
    return Config.CHASE_SEND_HOUR_START <= moment.hour < Config.CHASE_SEND_HOUR_END


def next_business_day(day: date) -> date:
    """Nudge a Saturday or Sunday forward to the following Monday."""
    while day.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        day += timedelta(days=1)
    return day


def rung_due_dates(deadline: date) -> list[tuple[str, date]]:
    """
    Each rung paired with the date it is due, weekends pushed to the Monday
    after. Shifting the date rather than skipping the send matters: a rung
    whose day lands on a Saturday still goes out, just on the next working
    day, instead of being lost for that creator entirely.

    The shift has to keep the rungs on separate days. A Friday deadline puts
    D+1 on the Saturday and D+3 on the Monday, and a naive shift lands both
    on that same Monday — at which point the highest-due-rung rule quietly
    swallows the first, gentler notice and the creator's opening chase is a
    second nudge for a message they never got. So each rung is also pushed
    past the one before it, and the cadence stretches by a day instead of
    losing a rung.
    """
    due_dates: list[tuple[str, date]] = []
    previous: Optional[date] = None
    for key, offset in zip(RUNG_KEYS, rung_days()):
        due = next_business_day(deadline + timedelta(days=offset))
        if previous is not None and due <= previous:
            due = next_business_day(previous + timedelta(days=1))
        due_dates.append((key, due))
        previous = due
    return due_dates


@dataclass(frozen=True)
class ChaseDecision:
    """What the ladder wants done for one creator, right now."""

    # The rung to fire, or None when nothing is due.
    rung: Optional[str] = None
    # Send the creator an email for this rung? False on the final rung, and
    # whenever the shortfall is not theirs to act on.
    email: bool = False
    # Why the email was withheld, for the Slack note and the log line.
    email_note: Optional[str] = None
    # Why nothing is due at all. Only set when `rung` is None.
    skip_reason: Optional[str] = None
    # Whole days past the deadline, after the hold is subtracted.
    days_overdue: int = 0
    # Days past the deadline on the wall calendar, hold included.
    raw_days_overdue: int = 0

    @property
    def is_final(self) -> bool:
        return self.rung == RUNG_FINAL


def _skip(reason: str, raw: int = 0) -> ChaseDecision:
    return ChaseDecision(skip_reason=reason, raw_days_overdue=raw)


def _parse_deadline(value) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def load_state(campaign_id: str, creator_username: str) -> Optional[ChaseState]:
    """The stored brake/hold for one creator, detached from the session."""
    db = SessionLocal()
    try:
        row = (
            db.query(ChaseState)
            .filter_by(campaign_id=campaign_id, creator_username=creator_username)
            .first()
        )
        if row is None:
            return None
        db.expunge(row)
        return row
    finally:
        db.close()


def set_state(
    campaign_id: str,
    creator_username: str,
    *,
    status: str,
    snoozed_until: Optional[date] = None,
    set_by: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    """Move the brake. Upserts, so the Slack buttons are safe to double-click."""
    db = SessionLocal()
    try:
        row = (
            db.query(ChaseState)
            .filter_by(campaign_id=campaign_id, creator_username=creator_username)
            .first()
        )
        if row is None:
            row = ChaseState(
                campaign_id=campaign_id, creator_username=creator_username,
            )
            db.add(row)
        row.status = status
        row.snoozed_until = snoozed_until
        row.set_by = set_by
        row.reason = reason
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to set chase state for @%s on %s", creator_username, campaign_id,
        )
    finally:
        db.close()


def _hold_clock(campaign_id: str, creator_username: str, today: date) -> int:
    """
    Charge one held day to this creator, at most once per calendar day, and
    return the running total. The once-per-day guard is what makes this safe
    on a 60-second poll — otherwise the hold would outrun the calendar within
    the hour and the ladder would never advance again.
    """
    db = SessionLocal()
    try:
        row = (
            db.query(ChaseState)
            .filter_by(campaign_id=campaign_id, creator_username=creator_username)
            .first()
        )
        if row is None:
            row = ChaseState(
                campaign_id=campaign_id,
                creator_username=creator_username,
                status="active",
                held_days=0,
            )
            db.add(row)
        if row.held_last_date != today:
            row.held_days = (row.held_days or 0) + 1
            row.held_last_date = today
        total = row.held_days or 0
        db.commit()
        return total
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to hold chase clock for @%s on %s", creator_username, campaign_id,
        )
        return 0
    finally:
        db.close()


def _latest_activity_date(creator: dict, tz) -> Optional[date]:
    """
    The most recent day this creator did something — shared a draft or logged
    a live post. Both facts come off the campaigns API rather than our own
    tables, so they survive a database wipe, which is exactly when we least
    want to start nagging someone who is already moving.
    """
    stamps: list[date] = []

    for review in (creator.get("reviews") or []):
        submitted = review.get("submittedAt")
        if not submitted:
            continue
        try:
            stamps.append(
                datetime.fromtimestamp(int(submitted) / 1000, tz=tz).date()
            )
        except (ValueError, TypeError, OSError, OverflowError):
            continue

    for video in (creator.get("videos") or []):
        if not video.get("hasLinks"):
            continue
        posted = _parse_deadline(video.get("uploadDate"))
        if posted:
            stamps.append(posted)

    return max(stamps) if stamps else None


def decide(creator: dict, *, today: Optional[date] = None) -> ChaseDecision:
    """
    The whole ladder in one call: given a creator dict from the campaigns API
    (flattened with campaign_id/campaign_name/brand_name, as the scheduler
    builds it), say which rung is due and whether the creator hears about it.

    Ordering is the design. Every cheap, certain reason to stay quiet is
    checked before the expensive ones, and the two "not their fault" cases are
    checked last because both still want the internal Slack alert.
    """
    tz = chase_timezone()
    today = today or datetime.now(tz).date()

    deadline = _parse_deadline(creator.get("deadline"))
    if deadline is None:
        return _skip("no deadline set")

    raw_days = (today - deadline).days
    if raw_days < 1:
        return _skip("deadline not yet passed", raw_days)

    deliverables = creator.get("deliverables") or {}
    if deliverables.get("allComplete") is True:
        return _skip("deliverables complete", raw_days)

    campaign_id = creator.get("campaign_id", "")
    username = creator.get("username", "")

    state = load_state(campaign_id, username)
    if state is not None:
        if state.status == "stopped":
            return _skip("chase stopped by the team", raw_days)
        if state.status == "snoozed":
            if state.snoozed_until is None or state.snoozed_until >= today:
                return _skip("chase snoozed by the team", raw_days)

    # Already moving on their own — a draft or a live post in the last few
    # days. Chasing here reads as not paying attention.
    window = Config.CHASE_ACTIVITY_SNOOZE_DAYS
    if window > 0:
        last_active = _latest_activity_date(creator, tz)
        if last_active is not None and (today - last_active).days <= window:
            return _skip(
                f"creator active {(today - last_active).days} day(s) ago", raw_days,
            )

    # The ball is with the brand: hold the clock rather than advancing it, and
    # let the caller retarget the Slack alert at the review.
    coverage = review_coverage(creator)
    held = state.held_days if state is not None else 0
    if coverage.covered:
        held = _hold_clock(campaign_id, username, today)

    effective_days = raw_days - (held or 0)
    if effective_days < 1:
        return _skip("chase clock held — waiting on the brand", raw_days)

    effective_today = deadline + timedelta(days=effective_days)
    due = [key for key, due_date in rung_due_dates(deadline) if due_date <= effective_today]
    if not due:
        return _skip("no rung due yet", raw_days)

    rung = due[-1]

    decision_kwargs = {
        "rung": rung,
        "days_overdue": effective_days,
        "raw_days_overdue": raw_days,
    }

    if not RUNG_EMAILS[rung]:
        return ChaseDecision(
            email=False,
            email_note="Final rung — the chase is now a person's call, not an email.",
            **decision_kwargs,
        )

    if coverage.covered:
        return ChaseDecision(
            email=False,
            email_note=f"Creator email skipped — {coverage.summary}.",
            **decision_kwargs,
        )

    # Everything they owe is posted and only the view target is short. Views
    # accrue without them; there is nothing to chase a creator for.
    if deliverables.get("videosComplete") is True and deliverables.get("viewsComplete") is False:
        return ChaseDecision(
            email=False,
            email_note=(
                "Creator email skipped — every video they owe is live and only "
                "the view target is short, which is not theirs to act on."
            ),
            **decision_kwargs,
        )

    if not creator.get("email"):
        return ChaseDecision(
            email=False,
            email_note="No email address on this creator.",
            **decision_kwargs,
        )

    return ChaseDecision(email=True, **decision_kwargs)
