"""
Lambda #1 — PostFeedbackFunction
Phase 5 — Python Lambda Agent

Triggered by: API Gateway POST /feedback (Cognito-authorized)
Responsibilities:
  1. Parse and validate feedback_text from request body
  2. Extract user_id from Cognito authorizer claims (sub)
  3. Generate a unique feedback_id (UUID v4)
  4. Publish the feedback message to SNS
  5. Return HTTP 202 Accepted with the feedback_id
"""
import json
import logging
import os
import uuid

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns_client = boto3.client("sns")
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]


def build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event: dict, context) -> dict:
    logger.info("PostFeedbackFunction invoked")

    # ── Parse body ───────────────────────────────────────────────────────────
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return build_response(400, {"error": "Invalid JSON in request body"})

    feedback_text: str = body.get("feedback_text", "").strip()
    if not feedback_text:
        return build_response(400, {"error": "feedback_text is required and cannot be empty"})

    # ── Extract authenticated user_id from Cognito claims ────────────────────
    try:
        user_id: str = event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        logger.error("Missing Cognito sub claim in event requestContext")
        return build_response(500, {"error": "Could not determine authenticated user"})

    # ── Generate feedback_id ─────────────────────────────────────────────────
    feedback_id: str = str(uuid.uuid4())
    logger.info("Processing feedback for user_id=%s feedback_id=%s", user_id, feedback_id)

    # ── Publish to SNS ───────────────────────────────────────────────────────
    message_payload = json.dumps(
        {
            "user_id": user_id,
            "feedback_id": feedback_id,
            "feedback_text": feedback_text,
        }
    )

    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=message_payload,
            Subject="FeedbackSubmitted",
        )
        logger.info("Published to SNS topic feedback_id=%s", feedback_id)
    except Exception:
        logger.exception("Failed to publish feedback to SNS")
        raise  # Surface to Lambda runtime for visibility — not retried here (POST path)

    return build_response(202, {"feedback_id": feedback_id})
