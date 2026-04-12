"""
INFLUENCE Bot — Main Application Entry Point

An automated Slack bot for INFLUENCE (influencer marketing) that:
- Receives video submissions via Tally webhooks
- Sends videos to brand POCs on Slack for review/approval
- Sends automated follow-up emails for overdue creator posts
- Notifies the team with daily summaries and real-time alerts
- Tracks creator Instagram stats

Email: jennifer@useinfluence.xyz
Tally: https://tally.so/dashboard
Slack Workspace: T09DSH6AEQH
Campaign Site: https://campaigns.influence.technology/reve/reve-features
"""

import logging

from flask import Flask, request, jsonify
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from config import Config
from models.models import init_db
from bot.handlers import register_event_handlers
from bot.commands import register_commands
from bot.actions import register_actions
from services.email_service import EmailService
from services.tally_service import TallyService
from services.instagram_service import InstagramService
from services.approval_workflow import ApprovalWorkflow
from services.scheduler_service import SchedulerService

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initialize Database
# ---------------------------------------------------------------------------
init_db()

# ---------------------------------------------------------------------------
# Slack Bolt App
# ---------------------------------------------------------------------------
bolt_app = App(
    token=Config.SLACK_BOT_TOKEN,
    signing_secret=Config.SLACK_SIGNING_SECRET,
)

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
email_service = EmailService()
tally_service = TallyService()
instagram_service = InstagramService()
approval_workflow = ApprovalWorkflow(bolt_app.client, email_service)
scheduler_service = SchedulerService(bolt_app.client, email_service)

# ---------------------------------------------------------------------------
# Register Slack Handlers
# ---------------------------------------------------------------------------
register_event_handlers(bolt_app, approval_workflow, scheduler_service)
register_commands(bolt_app, scheduler_service, instagram_service)
register_actions(bolt_app, approval_workflow)

# ---------------------------------------------------------------------------
# Flask App  (wraps Bolt for HTTP endpoints)
# ---------------------------------------------------------------------------
flask_app = Flask(__name__)
handler = SlackRequestHandler(bolt_app)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    """Handle all Slack events (messages, mentions, etc.)."""
    return handler.handle(request)


@flask_app.route("/slack/commands", methods=["POST"])
def slack_commands():
    """Handle slash commands."""
    return handler.handle(request)


@flask_app.route("/slack/actions", methods=["POST"])
def slack_actions():
    """Handle interactive actions (button clicks, modal submissions)."""
    return handler.handle(request)


# ---------------------------------------------------------------------------
# Tally Webhook Endpoint
# ---------------------------------------------------------------------------
@flask_app.route("/webhooks/tally", methods=["POST"])
def tally_webhook():
    """
    Receive webhooks from Tally form submissions.
    Processes creator info, video uploads, and posting status updates.
    Configure this URL in Tally: https://tally.so/dashboard -> Form -> Integrations -> Webhooks
    """
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "No payload"}), 400

    result = tally_service.process_webhook(payload)
    action = result.get("action")

    if action == "video_review":
        # A creator submitted a video — send it to the brand for review
        approval_workflow.send_video_for_review(result)
        logger.info(f"Video review workflow triggered for campaign {result.get('campaign_id')}")

    elif action == "new_campaign":
        # A new campaign was set up — notify the team
        bolt_app.client.chat_postMessage(
            channel=Config.SLACK_TEAM_CHANNEL_ID,
            text=(
                f":sparkles: *New Campaign Created!*\n"
                f"Creator: {result['creator_name']}\n"
                f"Brand: {result['brand_name']}\n"
                f"Deadline: {result['deadline']}\n"
                f"Content Type: {result['post_type'].capitalize()}"
            ),
        )
        logger.info(f"New campaign created: {result['creator_name']} x {result['brand_name']}")

    elif action == "posting_status":
        # Creator reported posting status
        if result["posted"]:
            bolt_app.client.chat_postMessage(
                channel=Config.SLACK_TEAM_CHANNEL_ID,
                text=(
                    f":tada: *Creator Posted!*\n"
                    f"{result['creator_name']} has posted their content for "
                    f"{result['brand_name']}!"
                ),
            )
        else:
            bolt_app.client.chat_postMessage(
                channel=Config.SLACK_ALERTS_CHANNEL_ID or Config.SLACK_TEAM_CHANNEL_ID,
                text=(
                    f":warning: *Creator Has Not Posted*\n"
                    f"{result['creator_name']} reported they have NOT posted yet for "
                    f"{result['brand_name']}. Follow-up will be triggered."
                ),
            )

    elif action == "error":
        logger.warning(f"Tally webhook error: {result.get('message')}")

    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "bot": "INFLUENCE Bot"}), 200


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    logger.info("Starting INFLUENCE Bot...")
    logger.info(f"Campaign Website: {Config.CAMPAIGN_WEBSITE_URL}")

    # Start the deadline monitoring scheduler
    scheduler_service.start()

    try:
        flask_app.run(
            host=Config.APP_HOST,
            port=Config.APP_PORT,
            debug=False,
        )
    finally:
        scheduler_service.shutdown()


if __name__ == "__main__":
    main()
