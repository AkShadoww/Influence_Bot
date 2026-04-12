import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- Slack ---
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
    SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
    SLACK_TEAM_CHANNEL_ID = os.environ.get("SLACK_TEAM_CHANNEL_ID")
    SLACK_ALERTS_CHANNEL_ID = os.environ.get("SLACK_ALERTS_CHANNEL_ID")

    # --- Email (jennifer@useinfluence.xyz) ---
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "jennifer@useinfluence.xyz")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Jennifer - INFLUENCE")

    # --- Tally ---
    TALLY_WEBHOOK_SECRET = os.environ.get("TALLY_WEBHOOK_SECRET")

    # --- Instagram / Meta ---
    INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

    # --- Anthropic AI ---
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

    # --- Campaign Website ---
    CAMPAIGN_WEBSITE_URL = os.environ.get(
        "CAMPAIGN_WEBSITE_URL",
        "https://campaigns.influence.technology/reve/reve-features",
    )

    # --- Application ---
    APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.environ.get("APP_PORT", 3000))
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///influence_bot.db")
