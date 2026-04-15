"""
Slack interactive action handlers for INFLUENCE Bot.
Handles any interactive components (button clicks, modal submissions).
"""

import logging

logger = logging.getLogger(__name__)


def register_actions(app):
    """Register interactive component handlers on the Bolt app.

    Currently no interactive actions are needed — webhook events
    from the ReelStats server handle review/video link notifications.
    This module is kept as a hook for future interactive features.
    """
    pass
