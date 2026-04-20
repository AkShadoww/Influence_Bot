"""
Scheduler for INFLUENCE Bot.
Polls the ReelStats API every 5 minutes and runs all notification checks:
- View milestones (250k, 500k, 1M, 1.5M, 2M, 5M, 10M, ...)
- Deliverables complete → payment flag
- Deadline reminders (3 days, 1 day, overdue)
- Upload follow-ups (videos behind schedule within 5 days of deadline)
- Daily payment summary
"""

import logging
from datetime import datetime, date, timezone, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from slack_sdk import WebClient
from sqlalchemy.exc import IntegrityError

from config import Config
from models.models import (
    SessionLocal,
    MilestoneAlert,
    DeliverableAlert,
    DeadlineReminder,
    UploadFollowup,
)
from services.reelstats_api import ReelStatsAPI
from services.email_service import EmailService
from templates.slack_blocks import (
    build_milestone_blocks,
    build_deliverable_complete_blocks,
    build_deadline_reminder_blocks,
    build_upload_followup_blocks,
    build_payment_summary_blocks,
)

logger = logging.getLogger(__name__)

MILESTONE_THRESHOLDS = [
    250_000, 500_000, 1_000_000, 1_500_000, 2_000_000,
    5_000_000, 10_000_000, 20_000_000, 50_000_000, 100_000_000,
]


class SchedulerService:
    def __init__(
        self,
        slack_client: WebClient,
        email_service: EmailService,
        reelstats_api: ReelStatsAPI,
    ):
        self.client = slack_client
        self.email_service = email_service
        self.api = reelstats_api
        self.channel = Config.SLACK_CHANNEL_ID
        self.scheduler = BackgroundScheduler()

    def start(self):
        """Start the scheduler with all polling jobs."""
        poll_minutes = Config.POLL_INTERVAL_MINUTES

        # Main polling job — runs all checks
        self.scheduler.add_job(
            self.run_all_checks,
            trigger=IntervalTrigger(minutes=poll_minutes),
            id="poll_and_check",
            name=f"Poll ReelStats API every {poll_minutes} min and run all checks",
            replace_existing=True,
        )

        # Daily payment summary at 9 AM
        self.scheduler.add_job(
            self.send_payment_summary,
            trigger="cron",
            hour=9,
            minute=0,
            id="daily_payment_summary",
            name="Daily payment summary",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(
            f"Scheduler started: polling every {poll_minutes} min, "
            f"daily summary at 9 AM"
        )

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down")

    def run_all_checks(self):
        """Fetch data from ReelStats API and run all notification checks."""
        creators = self.api.get_all_creators()
        if not creators:
            logger.info("No creators returned from API, skipping checks")
            return

        logger.info(f"Running checks on {len(creators)} creators")

        self.check_milestones(creators)
        self.check_deliverables_complete(creators)
        self.check_deadline_reminders(creators)
        self.check_upload_followups(creators)

    # ------------------------------------------------------------------
    # View Milestones
    # ------------------------------------------------------------------
    def check_milestones(self, creators: list[dict]):
        """Check if any creator's totalViews crossed a milestone threshold."""
        db = SessionLocal()
        try:
            for creator in creators:
                total_views = creator.get("totalViews", 0)
                username = creator.get("username", "")
                campaign_id = creator.get("campaign_id", "")

                for threshold in MILESTONE_THRESHOLDS:
                    if total_views >= threshold:
                        # Check if already notified
                        existing = (
                            db.query(MilestoneAlert)
                            .filter_by(
                                campaign_id=campaign_id,
                                creator_username=username,
                                milestone_value=threshold,
                            )
                            .first()
                        )
                        if existing:
                            continue

                        # Record and notify
                        alert = MilestoneAlert(
                            campaign_id=campaign_id,
                            creator_username=username,
                            milestone_value=threshold,
                        )
                        db.add(alert)
                        try:
                            db.commit()
                        except IntegrityError:
                            db.rollback()
                            continue

                        self._send_milestone_notification(
                            creator, threshold, total_views
                        )

        except Exception as e:
            logger.error(f"Error checking milestones: {e}")
        finally:
            db.close()

    def _send_milestone_notification(
        self, creator: dict, milestone: int, current_views: int
    ):
        milestone_label = _format_views(milestone)
        blocks = build_milestone_blocks(
            creator_username=creator.get("username", ""),
            campaign_name=creator.get("campaign_name", ""),
            brand_name=creator.get("brand_name", ""),
            milestone_label=milestone_label,
            current_views=_format_views(current_views),
        )
        self.client.chat_postMessage(
            channel=self.channel,
            text=(
                f"Milestone! @{creator.get('username')} hit "
                f"{milestone_label} views on {creator.get('campaign_name')}"
            ),
            blocks=blocks,
        )
        logger.info(
            f"Milestone alert: @{creator.get('username')} hit "
            f"{milestone_label} views"
        )

    # ------------------------------------------------------------------
    # Deliverables Complete
    # ------------------------------------------------------------------
    def check_deliverables_complete(self, creators: list[dict]):
        """Check if any creator's deliverables.allComplete flipped to true."""
        db = SessionLocal()
        try:
            for creator in creators:
                deliverables = creator.get("deliverables", {})
                all_complete = deliverables.get("allComplete")
                username = creator.get("username", "")
                campaign_id = creator.get("campaign_id", "")

                if all_complete is not True:
                    continue

                existing = (
                    db.query(DeliverableAlert)
                    .filter_by(
                        campaign_id=campaign_id,
                        creator_username=username,
                    )
                    .first()
                )
                if existing:
                    continue

                alert = DeliverableAlert(
                    campaign_id=campaign_id,
                    creator_username=username,
                )
                db.add(alert)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    continue

                blocks = build_deliverable_complete_blocks(
                    creator_username=username,
                    campaign_name=creator.get("campaign_name", ""),
                    brand_name=creator.get("brand_name", ""),
                    campaign_id=campaign_id,
                )
                self.client.chat_postMessage(
                    channel=self.channel,
                    text=(
                        f"Deliverables complete! @{username} partnering with "
                        f"{creator.get('brand_name')} has completed their "
                        f"deliverables and is supposed to be paid."
                    ),
                    blocks=blocks,
                )
                logger.info(f"Deliverable complete alert: @{username}")

        except Exception as e:
            logger.error(f"Error checking deliverables: {e}")
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Deadline Reminders
    # ------------------------------------------------------------------
    def check_deadline_reminders(self, creators: list[dict]):
        """Send reminders at 3 days before, 1 day before, and overdue."""
        db = SessionLocal()
        try:
            today = date.today()

            for creator in creators:
                deadline_str = creator.get("deadline")
                if not deadline_str:
                    continue

                try:
                    deadline = date.fromisoformat(deadline_str)
                except ValueError:
                    continue

                username = creator.get("username", "")
                campaign_id = creator.get("campaign_id", "")
                days_left = (deadline - today).days

                # Determine which reminder to send
                if days_left < 0:
                    reminder_type = "overdue"
                elif days_left <= 1:
                    reminder_type = "1_day"
                elif days_left <= 3:
                    reminder_type = "3_days"
                else:
                    continue

                # Check if already sent
                existing = (
                    db.query(DeadlineReminder)
                    .filter_by(
                        campaign_id=campaign_id,
                        creator_username=username,
                        reminder_type=reminder_type,
                    )
                    .first()
                )
                if existing:
                    continue

                # Send Slack notification
                blocks = build_deadline_reminder_blocks(
                    creator_username=username,
                    campaign_name=creator.get("campaign_name", ""),
                    brand_name=creator.get("brand_name", ""),
                    deadline=deadline_str,
                    reminder_type=reminder_type,
                    days_left=days_left,
                )
                self.client.chat_postMessage(
                    channel=self.channel,
                    text=f"Deadline reminder for @{username}: {reminder_type.replace('_', ' ')}",
                    blocks=blocks,
                )

                # Send email if available
                email_sent = False
                email = creator.get("email")
                if email:
                    from templates.email_templates import deadline_reminder_email
                    template = deadline_reminder_email(
                        creator_name=username,
                        campaign_name=creator.get("campaign_name", ""),
                        brand_name=creator.get("brand_name", ""),
                        deadline=deadline_str,
                        reminder_type=reminder_type,
                        days_left=days_left,
                    )
                    email_sent = self.email_service.send_followup(email, template)

                # Record
                reminder = DeadlineReminder(
                    campaign_id=campaign_id,
                    creator_username=username,
                    reminder_type=reminder_type,
                    email_sent=email_sent,
                )
                db.add(reminder)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    continue

                logger.info(
                    f"Deadline reminder ({reminder_type}): @{username}, "
                    f"email_sent={email_sent}"
                )

        except Exception as e:
            logger.error(f"Error checking deadlines: {e}")
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Upload Follow-ups
    # ------------------------------------------------------------------
    def check_upload_followups(self, creators: list[dict]):
        """
        If a creator has totalVideosPosted < minVideos and their deadline
        is within 5 days, send a reminder.
        """
        db = SessionLocal()
        try:
            today = date.today()

            for creator in creators:
                deliverables = creator.get("deliverables", {})
                min_videos = deliverables.get("minVideos")
                if min_videos is None:
                    continue

                total_posted = creator.get("totalVideosPosted", 0)
                if total_posted >= min_videos:
                    continue

                deadline_str = creator.get("deadline")
                if not deadline_str:
                    continue

                try:
                    deadline = date.fromisoformat(deadline_str)
                except ValueError:
                    continue

                days_left = (deadline - today).days
                if days_left > 5 or days_left < 0:
                    continue

                username = creator.get("username", "")
                campaign_id = creator.get("campaign_id", "")

                # Check if already sent
                existing = (
                    db.query(UploadFollowup)
                    .filter_by(
                        campaign_id=campaign_id,
                        creator_username=username,
                    )
                    .first()
                )
                if existing:
                    continue

                blocks = build_upload_followup_blocks(
                    creator_username=username,
                    campaign_name=creator.get("campaign_name", ""),
                    brand_name=creator.get("brand_name", ""),
                    videos_posted=total_posted,
                    videos_required=min_videos,
                    deadline=deadline_str,
                    days_left=days_left,
                )
                self.client.chat_postMessage(
                    channel=self.channel,
                    text=(
                        f"Upload reminder: @{username} has posted "
                        f"{total_posted}/{min_videos} videos, "
                        f"{days_left} days until deadline"
                    ),
                    blocks=blocks,
                )

                followup = UploadFollowup(
                    campaign_id=campaign_id,
                    creator_username=username,
                )
                db.add(followup)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    continue

                logger.info(f"Upload followup: @{username}")

        except Exception as e:
            logger.error(f"Error checking upload followups: {e}")
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Daily Payment Summary
    # ------------------------------------------------------------------
    def send_payment_summary(self):
        """Daily summary of all creators with completed deliverables."""
        creators = self.api.get_all_creators()
        completed = [
            c for c in creators
            if c.get("deliverables", {}).get("allComplete") is True
        ]

        if not completed:
            self.client.chat_postMessage(
                channel=self.channel,
                text=":sunrise: *Daily Payment Summary*\nNo creators with completed deliverables pending payment.",
            )
            return

        blocks = build_payment_summary_blocks(completed)
        self.client.chat_postMessage(
            channel=self.channel,
            text=f"Daily Payment Summary: {len(completed)} creator(s) ready for payment",
            blocks=blocks,
        )
        logger.info(f"Payment summary sent: {len(completed)} creators")


def _format_views(count: int) -> str:
    """Format a view count into a human-readable string (e.g. 1.5M, 500K)."""
    if count >= 1_000_000:
        val = count / 1_000_000
        return f"{val:.1f}M".replace(".0M", "M")
    elif count >= 1_000:
        val = count / 1_000
        return f"{val:.0f}K"
    return str(count)
