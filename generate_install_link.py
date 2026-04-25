"""
Print a Slack install link for a brand.

Two modes:

1. Direct Slack OAuth URL (offline — needs SLACK_CLIENT_ID, SLACK_CLIENT_SECRET,
   SLACK_OAUTH_REDIRECT_URI set in the environment):

       python generate_install_link.py acme

   The printed URL can be shared with the brand; opening it takes them to
   Slack's consent screen, where they pick a channel and click "Allow".

2. Short shareable URL routed through this app (useful if the bot is already
   running publicly). Pass --public-url:

       python generate_install_link.py acme --public-url https://bot.example.com

   This prints `https://bot.example.com/slack/install/acme` — hitting that URL
   issues the signed state + redirect at request time, so the install link
   never expires.
"""

import argparse
import sys

from services.slack_oauth import InstallConfigError, SlackInstallURLGenerator


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Slack install link for a brand")
    parser.add_argument(
        "brand",
        help="Brand slug (e.g. 'acme'). Embedded in the signed state so the "
             "callback can attribute the install.",
    )
    parser.add_argument(
        "--public-url",
        help="Public base URL of this app. If given, prints "
             "<public-url>/slack/install/<brand> instead of a direct Slack URL.",
    )
    args = parser.parse_args()

    if args.public_url:
        base = args.public_url.rstrip("/")
        print(f"{base}/slack/install/{args.brand}")
        return 0

    try:
        generator = SlackInstallURLGenerator()
    except InstallConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(generator.build_install_url(brand=args.brand))
    return 0


if __name__ == "__main__":
    sys.exit(main())
