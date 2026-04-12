"""
Professional and friendly email templates for INFLUENCE Bot.
All emails are sent from jennifer@useinfluence.xyz.
"""


def followup_delayed_post(creator_name: str, brand_name: str, deadline: str) -> dict:
    """Email template when a creator has missed their posting deadline."""
    subject = f"Quick Check-In: {brand_name} Content Deadline"
    body = f"""Hi {creator_name},

Hope you're doing great! Just wanted to quickly check in regarding your content for {brand_name}.

We noticed that the posting deadline ({deadline}) has passed, and we haven't seen the content go live yet. We totally understand that things can get busy, so no worries at all — just wanted to make sure everything is on track!

Could you give us a quick update on where things stand? If there's anything holding things up or if you need any support from our end, we're here to help.

Looking forward to hearing from you!

Warm regards,
Jennifer
INFLUENCE Team
"""
    return {"subject": subject, "body": body}


def followup_second_reminder(creator_name: str, brand_name: str, deadline: str) -> dict:
    """Second follow-up email for delayed posting."""
    subject = f"Following Up: {brand_name} Content — Need Your Update"
    body = f"""Hi {creator_name},

Hope all is well! I'm following up on my previous email regarding the {brand_name} content that was due on {deadline}.

We'd love to get this wrapped up as the brand is eager to see the content go live. Could you please share an update at your earliest convenience?

If there are any challenges or if the timeline needs to be adjusted, just let us know — we're happy to work with you on it.

Thanks so much for your time!

Best,
Jennifer
INFLUENCE Team
"""
    return {"subject": subject, "body": body}


def followup_urgent_reminder(creator_name: str, brand_name: str, deadline: str) -> dict:
    """Urgent third follow-up for significantly delayed posting."""
    subject = f"Urgent: {brand_name} Content — Action Required"
    body = f"""Hi {creator_name},

I hope you're doing well. I wanted to reach out once more regarding the {brand_name} content that was originally due on {deadline}.

This is becoming quite time-sensitive, and the brand has been checking in with us for updates. We really want to make sure everything goes smoothly for both you and the brand.

Could you please reply to this email today with a status update? Even a quick note letting us know when we can expect the post would be really helpful.

Thank you so much — we truly appreciate your collaboration!

Best regards,
Jennifer
INFLUENCE Team
"""
    return {"subject": subject, "body": body}


def video_approved(creator_name: str, brand_name: str) -> dict:
    """Email to creator when their video has been approved by the brand."""
    subject = f"Great News! Your {brand_name} Video Has Been Approved 🎉"
    body = f"""Hi {creator_name},

Amazing news — the {brand_name} team has reviewed and approved your video! Everything looks fantastic, and they're really happy with the content.

You're all set to go ahead and post it according to the campaign guidelines. Just a quick reminder to make sure all the required tags, hashtags, and mentions are included as discussed.

Once it's live, please share the post link with us so we can track the performance.

Thanks for the awesome work — you absolutely nailed it!

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


def video_submitted_for_review_brand(
    brand_poc_name: str, creator_name: str, creator_handle: str, video_url: str
) -> dict:
    """Email to brand POC when a creator submits a video for review."""
    subject = f"Video Ready for Review: {creator_name} (@{creator_handle})"
    body = f"""Hi {brand_poc_name},

A new video has been submitted for your review by {creator_name} (@{creator_handle}).

You can review the video here: {video_url}

We've also sent this to your Slack channel for quick review and approval. You can approve or request changes directly from Slack, or simply reply to this email with your feedback.

Looking forward to your thoughts!

Best,
Jennifer
INFLUENCE Team
"""
    return {"subject": subject, "body": body}


def campaign_kickoff(creator_name: str, brand_name: str, deadline: str, post_type: str) -> dict:
    """Welcome email to creator when a new campaign is set up."""
    subject = f"Welcome to the {brand_name} Campaign!"
    body = f"""Hi {creator_name},

We're thrilled to have you on board for the {brand_name} campaign! Here are the key details:

- Brand: {brand_name}
- Content Type: {post_type.capitalize()}
- Deadline: {deadline}

Please make sure to submit your draft video for brand review before the deadline. Once approved, you'll get the green light to post!

If you have any questions about the brief, deliverables, or anything else, don't hesitate to reach out.

Excited to see what you create!

Best,
Jennifer
INFLUENCE Team
"""
    return {"subject": subject, "body": body}
