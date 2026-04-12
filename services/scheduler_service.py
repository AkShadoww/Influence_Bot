"""
Deadline monitoring and automated follow-up scheduler for INFLUENCE Bot.
Checks for overdue campaigns and sends escalating follow-up emails.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from slack_sdk import WebClient

from config import Config
from models.models import SessionLocal, Campaign
from services.email_service import EmailService
from templates.email_templates import (
    followup_delayed_post,
    followup_second_reminder,
    followup_urgent_reminder,
)

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, slack_client: WebClient, email_service: EmailService):
        self.client = slack_client
        self.email_service = email_service
        self.scheduler = BackgroundScheduler()

    def start(self):
        """Start the scheduler with recurring deadline check jobs."""
        # Check for overdue campaigns every hour
        self.scheduler.add_job(
            self.check_overdue_campaigns,
            trigger=IntervalTrigger(hours=1),
            id="check_overdue_campaigns",
            name="Check for overdue creator campaigns",
            replace_existing=True,
        )

        # Daily summary at 9 AM
        self.scheduler.add_job(
            self.send_daily_summary,
            trigger="cron",
            hour=9,
            minute=0,
            id="daily_summary",
            name="Send daily campaign summary to team",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info("Scheduler started with deadline monitoring jobs")

    def shutdown(self):
        """Gracefully shut down the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down")

    def check_overdue_campaigns(self):
        """Check for campaigns past their deadline and send follow-ups."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            overdue = (
                db.query(Campaign)
                .filter(
                    Campaign.deadline < now,
                    Campaign.has_posted.is_(False),
                    Campaign.status.notin_(["posted", "approved"]),
                )
                .all()
            )

            for campaign in overdue:
                creator = campaign.creator
                brand = campaign.brand
                deadline_str = campaign.deadline.strftime("%B %d, %Y")

                # Determine which follow-up to send based on count
                if campaign.followup_count == 0:
                    template = followup_delayed_post(
                        creator.name, brand.name, deadline_str
                    )
                    followup_type = "first"
                elif campaign.followup_count == 1:
                    template = followup_second_reminder(
                        creator.name, brand.name, deadline_str
                    )
                    followup_type = "second"
                elif campaign.followup_count >= 2:
                    template = followup_urgent_reminder(
                        creator.name, brand.name, deadline_str
                    )
                    followup_type = "urgent"
                else:
                    continue

                # Send the follow-up email
                sent = self.email_service.send_followup(creator.email, template)

                if sent:
                    campaign.followup_count += 1
                    campaign.last_followup_at = now
                    campaign.status = "overdue"
                    db.commit()

                    # Alert the team on Slack
                    emoji = {
                        "first": ":clock3:",
                        "second": ":warning:",
                        "urgent": ":rotating_light:",
                    }.get(followup_type, ":bell:")

                    self.client.chat_postMessage(
                        channel=Config.SLACK_ALERTS_CHANNEL_ID or Config.SLACK_TEAM_CHANNEL_ID,
                        text=(
                            f"{emoji} *Overdue Follow-Up Sent ({followup_type})*\n"
                            f"Creator: {creator.name} ({creator.email})\n"
                            f"Brand: {brand.name}\n"
                            f"Original Deadline: {deadline_str}\n"
                            f"Follow-up #{campaign.followup_count} sent."
                        ),
                    )

                    logger.info(
                        f"Follow-up #{campaign.followup_count} sent to {creator.email} "
                        f"for campaign {campaign.id}"
                    )

        except Exception as e:
            logger.error(f"Error checking overdue campaigns: {e}")
        finally:
            db.close()

    def send_daily_summary(self):
        """Send a daily summary of all active campaigns to the team channel."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            active_campaigns = (
                db.query(Campaign)
                .filter(Campaign.status.notin_(["posted"]))
                .order_by(Campaign.deadline.asc())
                .all()
            )

            if not active_campaigns:
                self.client.chat_postMessage(
                    channel=Config.SLACK_TEAM_CHANNEL_ID,
                    text=":sunrise: *Daily Campaign Summary*\nNo active campaigns right now. All caught up!",
                )
                return

            lines = [":sunrise: *Daily Campaign Summary*\n"]
            overdue_count = 0
            pending_review = 0
            on_track = 0

            for c in active_campaigns:
                creator = c.creator
                brand = c.brand
                deadline_str = c.deadline.strftime("%b %d, %Y")
                is_overdue = c.deadline < now and not c.has_posted

                if is_overdue:
                    status_emoji = ":red_circle:"
                    overdue_count += 1
                elif c.status == "under_review":
                    status_emoji = ":large_yellow_circle:"
                    pending_review += 1
                elif c.status == "approved":
                    status_emoji = ":white_check_mark:"
                    on_track += 1
                else:
                    status_emoji = ":large_blue_circle:"
                    on_track += 1

                lines.append(
                    f"{status_emoji} *{creator.name}* x *{brand.name}* — "
                    f"Deadline: {deadline_str} | Status: {c.status}"
                )

            lines.append(
                f"\n:bar_chart: *Totals:* {len(active_campaigns)} active | "
                f"{overdue_count} overdue | {pending_review} pending review | "
                f"{on_track} on track"
            )

            self.client.chat_postMessage(
                channel=Config.SLACK_TEAM_CHANNEL_ID,
                text="\n".join(lines),
            )

            logger.info(f"Daily summary sent: {len(active_campaigns)} campaigns")

        except Exception as e:
            logger.error(f"Error sending daily summary: {e}")
        finally:
            db.close()
