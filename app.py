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
from services.slack_oauth import (
    InstallConfigError,
    InstallStateError,
    SlackInstallURLGenerator,
    handle_oauth_callback,
)

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
# Slack OAuth — per-brand install links
# ---------------------------------------------------------------------------
@flask_app.route("/slack/install", methods=["GET"])
@flask_app.route("/slack/install/<brand>", methods=["GET"])
def slack_install(brand: str = None):
    """
    Generate an install URL and redirect the brand to Slack's OAuth consent
    screen. The optional `<brand>` path segment is embedded (signed) in the
    `state` param so we know which brand the installation belongs to when
    Slack calls us back.
    """
    try:
        generator = SlackInstallURLGenerator()
    except InstallConfigError as exc:
        logger.error("Slack OAuth not configured: %s", exc)
        return jsonify({"error": str(exc)}), 500

    url = generator.build_install_url(brand=brand)
    # 302 so a browser following the link lands on Slack's consent page.
    return "", 302, {"Location": url}


@flask_app.route("/slack/oauth_redirect", methods=["GET"])
def slack_oauth_redirect():
    """OAuth callback: Slack redirects here with ?code=...&state=..."""
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")
    if error:
        return jsonify({"status": "denied", "error": error}), 400
    if not code or not state:
        return jsonify({"error": "Missing code or state"}), 400

    try:
        install = handle_oauth_callback(code=code, state=state)
    except InstallStateError as exc:
        logger.warning("Invalid OAuth state: %s", exc)
        return jsonify({"error": "Invalid state"}), 400
    except Exception as exc:
        logger.exception("OAuth callback failed: %s", exc)
        return jsonify({"error": "Install failed"}), 500

    return jsonify({
        "status": "installed",
        "brand": install.brand,
        "team": install.team_name,
        "channel": install.channel_name,
    }), 200


# ---------------------------------------------------------------------------
# ReelStats Webhook Endpoint
# ---------------------------------------------------------------------------
@flask_app.route("/webhook", methods=["POST"])
def reelstats_webhook():
    """
    Receive webhook events from the ReelStats server.
    Events: review_submitted, video_links_submitted
    """
    payload = request.get_json(silent=True)
    if not payload:
        logger.warning("Received webhook with no JSON payload")
        return jsonify({"error": "No payload"}), 400

    event_type = payload.get("event", "unknown")
    creator = (payload.get("creator") or {}).get("username", "?")
    campaign = (payload.get("campaign") or {}).get("name", "?")
    logger.info(
        f"Received webhook event: {event_type} "
        f"(creator=@{creator}, campaign='{campaign}')"
    )

    try:
        success = webhook_handler.handle_event(payload)
    except Exception as e:
        logger.exception(f"Unhandled error processing webhook {event_type}: {e}")
        return jsonify({"status": "error", "event": event_type}), 500

    if success:
        return jsonify({"status": "ok"}), 200
    return jsonify({"status": "failed", "event": event_type}), 500


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
