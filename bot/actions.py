"""
Slack interactive action handlers for INFLUENCE Bot.
Handles button clicks (approve/reject) and modal submissions (feedback).
"""

import json
import logging

logger = logging.getLogger(__name__)


def register_actions(app, approval_workflow):
    """Register all interactive component handlers on the Bolt app."""

    @app.action("approve_video")
    def handle_approve(ack, body, respond):
        """Handle the 'Approve Video' button click."""
        ack()
        user_id = body["user"]["id"]
        action_value = json.loads(body["actions"][0]["value"])
        video_id = action_value["video_id"]

        result = approval_workflow.handle_approval(
            video_id=video_id, approver_user_id=user_id
        )

        if result["success"]:
            respond(
                text=f":white_check_mark: Video approved! Approval email sent to {result['creator_email']}.",
                replace_original=False,
            )
        else:
            respond(
                text=f":x: Error: {result['message']}",
                replace_original=False,
            )

    @app.action("request_changes")
    def handle_request_changes(ack, body, client):
        """Handle the 'Request Changes' button — open a modal for feedback."""
        ack()
        action_value = json.loads(body["actions"][0]["value"])

        client.views_open(
            trigger_id=body["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "feedback_modal",
                "private_metadata": json.dumps(action_value),
                "title": {"type": "plain_text", "text": "Request Changes"},
                "submit": {"type": "plain_text", "text": "Send Feedback"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "feedback_block",
                        "label": {
                            "type": "plain_text",
                            "text": "What changes are needed?",
                        },
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "feedback_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Describe the changes the brand would like...",
                            },
                        },
                    }
                ],
            },
        )

    @app.view("feedback_modal")
    def handle_feedback_submission(ack, body, view):
        """Handle the feedback modal submission."""
        ack()
        user_id = body["user"]["id"]
        metadata = json.loads(view["private_metadata"])
        video_id = metadata["video_id"]

        feedback = view["state"]["values"]["feedback_block"]["feedback_input"]["value"]

        result = approval_workflow.handle_changes_requested(
            video_id=video_id,
            reviewer_user_id=user_id,
            feedback=feedback,
        )

        # Send a DM to the reviewer confirming the feedback was sent
        app.client.chat_postMessage(
            channel=user_id,
            text=(
                f":white_check_mark: Your feedback has been sent to the creator.\n"
                f"*Feedback:* {feedback}"
                if result["success"]
                else f":x: Error: {result['message']}"
            ),
        )
