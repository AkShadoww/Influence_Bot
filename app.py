"""
INFLUENCE Bot — Main Application Entry Point

An automated Slack bot for INFLUENCE (influencer marketing) that:
- Polls the ReelStats API every 5 minutes for campaign data
- Sends view milestone alerts (250K, 500K, 1M, ...)
- Flags creators for payment when deliverables are complete
- Sends deadline reminders (3 days, 1 day, overdue) via Slack + email
- Sends upload follow-ups when creators are behind schedule
- Posts a daily payment summary at 9 AM
- Receives webhook events from ReelStats (review_submitted, video_links_submitted)

Email: jennifer@useinfluence.xyz
ReelStats API: configured via REELSTATS_API_URL env var
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
from services.reelstats_api import ReelStatsAPI
from services.webhook_handler import WebhookHandler
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
reelstats_api = ReelStatsAPI()
webhook_handler = WebhookHandler(bolt_app.client)
scheduler_service = SchedulerService(bolt_app.client, email_service, reelstats_api)

# ---------------------------------------------------------------------------
# Register Slack Handlers
# ---------------------------------------------------------------------------
register_event_handlers(bolt_app)
register_commands(bolt_app, scheduler_service, reelstats_api)
register_actions(bolt_app)

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
# ReelStats Webhook Endpoint
# ---------------------------------------------------------------------------
@flask_app.route("/webhook", methods=["POST"])
def reelstats_webhook():
    """
    Receive webhook events from the ReelStats server.
    Events: review_submitted, video_links_submitted
    """
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "No payload"}), 400

    event_type = payload.get("event", "unknown")
    logger.info(f"Received webhook event: {event_type}")

    success = webhook_handler.handle_event(payload)

    if success:
        return jsonify({"status": "ok"}), 200
    else:
        return jsonify({"status": "unhandled", "event": event_type}), 200


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
    logger.info(f"ReelStats API: {Config.REELSTATS_API_URL}")
    logger.info(f"Poll interval: {Config.POLL_INTERVAL_MINUTES} minutes")

    # Start the polling scheduler
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
