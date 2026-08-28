"""
Professional and friendly email templates for INFLUENCE Bot.
All emails are sent from jennifer@useinfluence.xyz.
"""


def _reply_block(chat_url: str | None) -> str:
    """
    The line that turns a reply we cannot read into one we can.

    Resend only sends. A creator who answers a chase by hitting reply lands in
    a human inbox the bot never sees, so the ladder keeps climbing and the
    next rung goes out as though they had said nothing. Pointing them at their
    chat space instead puts the answer somewhere the system can act on. When
    the link can't be built we say nothing rather than ship a dead URL.
    """
    if not chat_url:
        return ""
    return (
        "The quickest way to reach us is your campaign chat — "
        "you'll also find whatever's next for you there:\n"
        f"{chat_url}\n\n"
    )


def _delivery_gap(videos_posted: int | None, videos_required: int | None) -> str:
    """
    "1 of 2 videos are live" — the specific shortfall, in one clause.

    A chase that names the number is much harder to file away than one that
    refers vaguely to "your content", and it also catches the case where our
    records and the creator's memory disagree: they can see immediately what
    we think is missing.
    """
    if not videos_required:
        return ""
    posted = videos_posted or 0
    if posted <= 0:
        noun = "video is" if videos_required == 1 else "videos are"
        return f"We haven't seen any of the {videos_required} {noun} live yet."
    return (
        f"We're showing {posted} of {videos_required} videos live, "
        f"so {videos_required - posted} still to come."
    )


def deadline_reminder_email(
    creator_name: str,
    campaign_name: str,
    brand_name: str,
    deadline: str,
    reminder_type: str,
    days_left: int,
    chat_url: str | None = None,
    days_overdue: int | None = None,
    videos_posted: int | None = None,
    videos_required: int | None = None,
) -> dict:
    """
    Email body for one rung of the deadline ladder.

    Before the deadline (``3_days``, ``1_day``) the job is a nudge. After it
    (``overdue``, ``overdue_2``, ``overdue_3``) the job is to get a date out
    of the creator, and each rung asks more plainly than the last. The fourth
    rung has no body here on purpose — it hands the creator to a person and
    sends them nothing.

    Every rung carries the chat link, so a reply lands somewhere the bot can
    read it rather than in an inbox it cannot.
    """
    reply = _reply_block(chat_url)
    gap = _delivery_gap(videos_posted, videos_required)
    gap_line = f"{gap}\n\n" if gap else ""
    late = days_overdue if days_overdue is not None else abs(days_left)

    if reminder_type == "overdue_3":
        subject = f"Final notice: {brand_name} content is {late} days overdue"
        body = f"""Hi {creator_name},

We've written twice about the {brand_name} campaign ("{campaign_name}"), and we haven't heard back. The deadline was {deadline} — {late} days ago.

{gap_line}The deliverables and date in this email are the ones in your signed agreement, so we do need to resolve it now rather than let it drift. Please reply today with either the content or a date you can commit to.

{reply}If something has changed on your side and you can no longer deliver, that's genuinely fine to say — tell us and we'll close it off cleanly. What doesn't work is silence.

Best regards,

Jennifer
INFLUENCE Team
"""
    elif reminder_type == "overdue_2":
        subject = f"Following up: {brand_name} content — {late} days past deadline"
        body = f"""Hi {creator_name},

Following up on the {brand_name} campaign ("{campaign_name}"). The deadline was {deadline}, so we're now {late} days past it.

{gap_line}Could you reply with the date you'll have this posted? Even "next Tuesday" is enough — we just need something to tell the brand.

{reply}If anything's blocking you — the brief, the product, approvals — say so and we'll sort it out.

Thanks,

Jennifer
INFLUENCE Team
"""
    elif reminder_type == "overdue":
        subject = f"Urgent: {brand_name} Content — Deadline Passed"
        body = f"""Hi {creator_name},

Hope you're doing well. The deadline for the {brand_name} campaign ("{campaign_name}") was {deadline} and has now passed.

{gap_line}Could you reply today and let us know when the content will go up? A specific date is ideal — it lets us keep the brand in the loop instead of guessing.

{reply}If you need anything from us to get it over the line, just ask.

Thank you so much - we truly appreciate your collaboration!

Best regards,

Jennifer
INFLUENCE Team
"""
    elif reminder_type == "1_day":
        subject = f"Reminder: {brand_name} Content Due Tomorrow"
        body = f"""Hi {creator_name},

Just a quick heads-up, the deadline for your {brand_name} campaign ("{campaign_name}") is tomorrow ({deadline}).

{gap_line}Please make sure your content is posted on time. If there's anything holding things up or if you need any support from our end, let us know and we're happy to help!

{reply}Looking forward to seeing the content go live.

Best,

Jennifer
INFLUENCE Team
"""
    else:
        subject = f"Upcoming Deadline: {brand_name} Content Due in {days_left} Days"
        body = f"""Hi {creator_name},

Just a friendly reminder that the deadline for your {brand_name} campaign ("{campaign_name}") is coming up on {deadline} - that's {days_left} days from now.

If you haven't already, please make sure everything is on track for posting by the deadline. If you have any questions about the brief or deliverables, don't hesitate to reach out.

{reply}Thanks for being such a great partner on this!

Warm regards,

Jennifer
INFLUENCE Team
"""
    return {"subject": subject, "body": body}


def video_approved(
    creator_name: str,
    brand_name: str,
    submit_posts_url: str | None = None,
) -> dict:
    """
    Email to creator when their video has been approved by the brand.

    `submit_posts_url` is the creator-specific URL from the ReelStats
    API (`creators[].submissionLinks.submitPostsUrl`). When present we
    include the "submit the post link(s) here" sentence; when missing
    (older review rows / API didn't return it) we drop that sentence
    entirely so the email doesn't ship a broken link.
    """
    subject = f"Great News! Your {brand_name} Video Has Been Approved"
    if submit_posts_url:
        submit_line = (
            "Once it's live, please submit the post link(s) here so we can "
            f"track the performance: {submit_posts_url}\n\n"
        )
    else:
        submit_line = ""
    body = f"""Hi {creator_name},

The {brand_name} team has reviewed and approved your video!

You're all set to go ahead and post it. Just a quick reminder to make sure all the required tags, hashtags, and mentions are included as per the posting guidelines in the content brief.

{submit_line}Thanks for the awesome work! :)

Cheers,

Jennifer
INFLUENCE Team
"""
    return {"subject": subject, "body": body}


def video_changes_requested(
    creator_name: str, brand_name: str, feedback: str
) -> dict:
    """Email to creator when the brand requests changes to their video."""
    subject = f"Feedback on Your {brand_name} Video — Small Changes Needed"
    body = f"""Hi {creator_name},

Thanks so much for submitting your video for {brand_name}! The brand team has reviewed it and they really liked the overall direction. They do have a few notes they'd love for you to incorporate:

---
{feedback}
---

We know revisions can be a bit of extra work, but these tweaks will really help make the final content shine. Once you've made the updates, please resubmit the revised video and we'll get it back to the brand for a quick final review.

If you have any questions about the feedback, feel free to reach out — happy to clarify anything!

Thanks for being such a great partner on this.

Warm regards,
Jennifer
INFLUENCE Team
"""
    return {"subject": subject, "body": body}


def chat_new_message(
    creator_name: str,
    brand_name: str,
    message: str,
    chat_url: str,
    sender_party: str = "brand",
) -> dict:
    """Email to a creator when a new message lands in the chat space.

    `message` is the full message body (newlines preserved) — the email quotes
    it in its entirety rather than a truncated preview.

    `sender_party` decides the attribution: brand messages are announced as
    coming from the brand team, while messages from our own (INFLUENCE) side
    stay neutral — the creator just hears that feedback came in, not that
    "the INFLUENCE team messaged you".
    """
    if sender_party == "brand":
        subject = f"{brand_name} team messaged you — Content Review"
        intro = (
            f"{brand_name} Team just sent you a message about the content you "
            "submitted for review:"
        )
    else:
        # `brand_name` falls back to a generic placeholder upstream when the
        # space has no brand on it — don't splice that into the subject.
        brand_label = (brand_name or "").strip()
        if brand_label.lower() in ("", "the brand"):
            subject = "You've received feedback on your content — Content Review"
        else:
            subject = f"You've received feedback on your {brand_label} content"
        intro = (
            "You've received feedback on the content you submitted for review:"
        )
    body = f"""Hi {creator_name},

{intro}

--
{message}
--

Reply here:
{chat_url}

Best,

Jennifer
INFLUENCE Team
"""
    return {"subject": subject, "body": body}


def review_thread_comment(
    creator_name: str, brand_name: str, commenter: str, comment: str
) -> dict:
    """Email to creator relaying a Slack thread reply on their review submission."""
    subject = f"New Comment on Your {brand_name} Video Submission"
    body = f"""Hi {creator_name},

Someone from the {brand_name} team left a comment on your video submission:

---
{commenter}:
{comment}
---

Feel free to reach out if you'd like to discuss or have any questions.

Thanks!
Jennifer
INFLUENCE Team
"""
    return {"subject": subject, "body": body}
