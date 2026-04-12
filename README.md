# INFLUENCE Bot

An automated Slack bot for **INFLUENCE** — an influencer marketing business that connects brands with Instagram creators for social media marketing campaigns.

## What It Does

INFLUENCE Bot automates the entire creator-brand content workflow:

1. **Video Review & Approval** — Creators submit draft videos via Tally. The bot sends them to brand POCs on Slack with Approve / Request Changes buttons. Decisions trigger automatic emails to creators.

2. **Automated Follow-Up Emails** — When a creator misses their posting deadline, the bot sends escalating follow-up emails (friendly reminder -> second nudge -> urgent notice) from `jennifer@useinfluence.xyz`.

3. **Team Notifications & Alerts** — Real-time Slack alerts for new campaigns, video submissions, approvals, overdue deadlines, and daily campaign summaries every morning at 9 AM.

4. **Instagram Stats** — Check any creator's follower count, engagement, and recent post performance directly from Slack.

5. **Campaign Tracking** — Full lifecycle tracking: pending -> video submitted -> under review -> approved/changes requested -> posted.

## Architecture

```
INFLUENCE Bot
├── app.py                          # Main entry point (Flask + Slack Bolt)
├── config.py                       # Environment variable configuration
├── bot/
│   ├── handlers.py                 # Slack event handlers (mentions, messages)
│   ├── commands.py                 # Slash commands (/influence-status, etc.)
│   └── actions.py                  # Interactive actions (approve/reject buttons)
├── services/
│   ├── email_service.py            # SMTP email sending (jennifer@useinfluence.xyz)
│   ├── tally_service.py            # Tally webhook processing
│   ├── instagram_service.py        # Instagram Graph API integration
│   ├── approval_workflow.py        # Video review & approval flow
│   └── scheduler_service.py        # Deadline monitoring & scheduled tasks
├── models/
│   └── models.py                   # Database models (Creator, Brand, Campaign, Video)
├── templates/
│   ├── email_templates.py          # Professional email templates
│   └── slack_blocks.py             # Slack Block Kit message templates
└── utils/
    └── helpers.py                  # Utility functions
```

## Workflow

```
Creator submits video via Tally
        │
        ▼
  Tally Webhook ──► INFLUENCE Bot
        │
        ├──► Sends video to Brand's Slack channel
        │    (with Approve / Request Changes buttons)
        │
        ├──► Notifies INFLUENCE team on Slack
        │
        └──► Emails Brand POC about the submission
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
   Brand Approves         Brand Requests Changes
        │                       │
        ▼                       ▼
  Email creator            Email creator
  "You're approved!"      with feedback
        │                       │
        ▼                       ▼
  Notify team              Notify team
  on Slack                 on Slack
```

## Integrations

| Service | Purpose | Link |
|---------|---------|------|
| **Slack** | Team notifications, brand approvals | Workspace `T09DSH6AEQH` |
| **Tally** | Creator form submissions, video uploads | https://tally.so/dashboard |
| **Email (SMTP)** | Follow-ups and approval notifications | `jennifer@useinfluence.xyz` |
| **Instagram Graph API** | Creator stats and performance tracking | Meta Developer API |
| **Campaign Website** | Campaign management | https://campaigns.influence.technology/reve/reve-features |

## Setup

### 1. Clone and Install

```bash
git clone <repo-url>
cd Influence_Bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

Required environment variables:
- `SLACK_BOT_TOKEN` — Slack Bot User OAuth Token (`xoxb-...`)
- `SLACK_SIGNING_SECRET` — From Slack App settings
- `SLACK_TEAM_CHANNEL_ID` — Channel for team notifications
- `SMTP_PASSWORD` — App password for `jennifer@useinfluence.xyz`
- `INSTAGRAM_ACCESS_TOKEN` — Meta Graph API token

### 3. Create Slack App

At https://api.slack.com/apps, create a new app with:

**Bot Token Scopes:**
- `channels:history`, `channels:read`
- `chat:write`
- `commands`
- `im:write`
- `users:read`

**Event Subscriptions** (Request URL: `https://your-domain/slack/events`):
- `message.channels`
- `app_mention`
- `team_join`

**Slash Commands** (all point to `https://your-domain/slack/commands`):
- `/influence-status`
- `/influence-followup`
- `/influence-stats`
- `/influence-help`

**Interactivity** (Request URL: `https://your-domain/slack/actions`)

### 4. Configure Tally Webhook

In Tally Dashboard -> Your Form -> Integrations -> Webhooks:
- Webhook URL: `https://your-domain/webhooks/tally`

### 5. Run

```bash
python app.py
```

The bot starts on port 3000 by default. Use a tunnel (e.g., ngrok) for development:

```bash
ngrok http 3000
```

## Slack Commands

| Command | Description |
|---------|-------------|
| `/influence-status` | View all active campaign statuses |
| `/influence-followup` | Manually trigger overdue campaign checks |
| `/influence-stats <handle>` | Check a creator's Instagram stats |
| `/influence-help` | Show all available commands |

## Automated Features

- **Hourly deadline checks** — Scans for overdue campaigns and sends follow-up emails
- **Daily summary at 9 AM** — Posts campaign overview to team channel
- **Escalating follow-ups** — 1st reminder (friendly) -> 2nd reminder (nudge) -> 3rd (urgent)
- **Real-time Slack alerts** — New campaigns, video submissions, approvals, overdue notices
