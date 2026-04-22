import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- ReelStats API ---
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    REELSTATS_API_URL = os.environ.get(
        "REELSTATS_API_URL", "https://campaigns.influence.technology"
    )

    # --- Slack ---
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
    SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")

    # --- Slack OAuth (for per-brand install links) ---
    # Create an app at https://api.slack.com/apps, enable "Distribution", then
    # copy Client ID / Client Secret here. SLACK_OAUTH_REDIRECT_URI must match
    # the redirect URL registered on the Slack app (e.g.
    # https://your-domain/slack/oauth_redirect).
    SLACK_CLIENT_ID = os.environ.get("SLACK_CLIENT_ID")
    SLACK_CLIENT_SECRET = os.environ.get("SLACK_CLIENT_SECRET")
    SLACK_OAUTH_REDIRECT_URI = os.environ.get("SLACK_OAUTH_REDIRECT_URI")
    # Scopes requested during install. `incoming-webhook` causes Slack to prompt
    # the installing user to pick a channel, which is the channel the bot will
    # post to for that workspace.
    SLACK_OAUTH_SCOPES = os.environ.get(
        "SLACK_OAUTH_SCOPES",
        "chat:write,channels:read,commands,incoming-webhook,users:read",
    )
    # HMAC key used to sign the `state` param in install URLs. Defaults to the
    # signing secret, but can be overridden.
    SLACK_OAUTH_STATE_SECRET = (
        os.environ.get("SLACK_OAUTH_STATE_SECRET")
        or os.environ.get("SLACK_SIGNING_SECRET")
    )

    # --- Per-category Slack channels ---
    # Each notification type routes to its own channel. Accepts a channel name
    # (e.g. "#content-reviews") or a channel ID (e.g. "C0XXXXXXXXX"). The bot
    # must be a member of each channel or posts fail with `not_in_channel`.
    SLACK_CHANNEL_REVIEWS = os.environ.get("SLACK_CHANNEL_REVIEWS") or "#content-reviews"
    SLACK_CHANNEL_UPLOADS = os.environ.get("SLACK_CHANNEL_UPLOADS") or "#content-uploads"
    SLACK_CHANNEL_PAYMENTS = os.environ.get("SLACK_CHANNEL_PAYMENTS") or "#payment-reminders"
    SLACK_CHANNEL_MILESTONES = os.environ.get("SLACK_CHANNEL_MILESTONES") or "#breakout-content-alerts"
    SLACK_CHANNEL_DEADLINES = os.environ.get("SLACK_CHANNEL_DEADLINES") or "#creator-deadlines"

    # --- Email (jennifer@useinfluence.xyz) ---
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "jennifer@useinfluence.xyz")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Jennifer - INFLUENCE")

    # --- Application ---
    APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.environ.get("APP_PORT", 3000))
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///influence_bot.db")
    POLL_INTERVAL_MINUTES = int(os.environ.get("POLL_INTERVAL_MINUTES", 5))

    # --- Testing ---
    # If set, the bot only processes the campaign with this exact name.
    # Leave empty/unset in production to process all campaigns.
    TEST_CAMPAIGN_NAME = os.environ.get("TEST_CAMPAIGN_NAME") or None
