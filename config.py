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

    # --- Email (jennifer@useinfluence.xyz) ---
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "jennifer@useinfluence.xyz")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Jennifer - INFLUENCE")

    # --- Application ---
    # Host/port binding is handled by gunicorn ($PORT on Railway), not here.
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///influence_bot.db")

    # Poll interval for the safety-net fallback. Real-time notifications come
    # from ReelStats webhooks; this loop catches anything a dropped webhook
    # missed. Prefer POLL_INTERVAL_SECONDS; POLL_INTERVAL_MINUTES is legacy.
    _poll_seconds = os.environ.get("POLL_INTERVAL_SECONDS")
    if _poll_seconds is not None:
        POLL_INTERVAL_SECONDS = int(_poll_seconds)
    elif os.environ.get("POLL_INTERVAL_MINUTES") is not None:
        POLL_INTERVAL_SECONDS = int(os.environ["POLL_INTERVAL_MINUTES"]) * 60
    else:
        POLL_INTERVAL_SECONDS = 60

    # --- Testing ---
    # If set, the bot only processes the campaign with this exact name.
    # Leave empty/unset in production to process all campaigns.
    TEST_CAMPAIGN_NAME = os.environ.get("TEST_CAMPAIGN_NAME") or None
