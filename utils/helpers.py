"""
Utility functions for INFLUENCE Bot.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def format_deadline(dt: datetime) -> str:
    """Format a deadline datetime into a human-readable string."""
    return dt.strftime("%B %d, %Y")


def is_overdue(deadline: datetime) -> bool:
    """Check if a deadline has passed."""
    now = datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline < now


def days_overdue(deadline: datetime) -> int:
    """Return the number of days past the deadline (0 if not overdue)."""
    now = datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline >= now:
        return 0
    return (now - deadline).days


def sanitize_instagram_handle(handle: str) -> str:
    """Clean up an Instagram handle — remove @ prefix and whitespace."""
    return handle.strip().lstrip("@")


def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text to a max length, adding ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
