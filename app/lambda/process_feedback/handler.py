"""
Lambda #2 — ProcessFeedbackFunction
Phase 5 — Python Lambda Agent (includes Phase 8 Bedrock integration)

Triggered by: SQS Event Source Mapping from FeedbackQueue
The SQS message body is an SNS notification envelope — must be unwrapped.

Responsibilities:
  1. Unwrap the SNS-over-SQS message envelope
  2. Parse user_id, feedback_id, feedback_text
  3. Call Amazon Bedrock to generate a career improvement recommendation
  4. Save the recommendation to DynamoDB
  5. Re-raise any exception so SQS can retry (→ DLQ after max_receive_count)
"""
import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
bedrock_client = boto3.client("bedrock-runtime")

TABLE_NAME = os.environ["TABLE_NAME"]
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "qwen.qwen3-32b-v1:0")
BEDROCK_INFERENCE_PROFILE_ID = os.environ.get("BEDROCK_INFERENCE_PROFILE_ID")
BEDROCK_FALLBACK_MODEL_ID = os.environ.get(
    "BEDROCK_FALLBACK_MODEL_ID",
    "mistral.mistral-7b-instruct-v0:2",
)

# Log resolved config on cold start — visible in CloudWatch Logs
logger.info(
    "ProcessFeedbackFunction cold start: TABLE_NAME=%s BEDROCK_MODEL_ID=%s "
    "BEDROCK_INFERENCE_PROFILE_ID=%s BEDROCK_FALLBACK_MODEL_ID=%s",
    TABLE_NAME,
    BEDROCK_MODEL_ID,
    BEDROCK_INFERENCE_PROFILE_ID or "<unset>",
    BEDROCK_FALLBACK_MODEL_ID,
)


# ── SNS-over-SQS envelope unwrapping ────────────────────────────────────────

def parse_sqs_sns_message(record: dict) -> dict:
    """Unwrap the SNS envelope inside an SQS record body."""
    sqs_body = json.loads(record["body"])     # SNS notification JSON
    return json.loads(sqs_body["Message"])    # actual application payload


# ── Amazon Bedrock invocation (Phase 8 — Bedrock sub-task) ──────────────────

def get_recommendation(feedback_text: str) -> str:
    """
    Calls Amazon Bedrock with a career-coach prompt and returns the
    generated recommendation text.
    Re-raises on any exception to allow SQS retry.
    """
    prompt = (
        "You are a career coach. Read the manager feedback below and reply with "
        "2-3 concise sentences that tell the person exactly what to improve and one "
        "concrete action they can take immediately. Do not use bullet points, headers, "
        "or numbered lists — plain sentences only.\n\n"
        f'Feedback: "{feedback_text}"'
    )

    def _extract_converse_text(response: dict) -> str:
        """Extract plain text from Bedrock Converse API response."""
        output = response.get("output", {})
        message = output.get("message", {}) if isinstance(output, dict) else {}
        content = message.get("content", []) if isinstance(message, dict) else []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                return block["text"]
        raise KeyError(f"Could not extract text from Bedrock Converse response, keys={list(response.keys())}")

    model_candidates = [BEDROCK_MODEL_ID]
    if BEDROCK_INFERENCE_PROFILE_ID:
        model_candidates.append(BEDROCK_INFERENCE_PROFILE_ID)
    if BEDROCK_FALLBACK_MODEL_ID and BEDROCK_FALLBACK_MODEL_ID not in model_candidates:
        model_candidates.append(BEDROCK_FALLBACK_MODEL_ID)

    last_error: Exception | None = None

    for model_id in model_candidates:
        logger.info("Invoking Bedrock Converse modelId=%s", model_id)
        try:
            response = bedrock_client.converse(
                modelId=model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
                    }
                ],
                inferenceConfig={
                    "maxTokens": 120,
                    "temperature": 0.7,
                    "topP": 0.9,
                },
            )
            recommendation = _extract_converse_text(response)
            logger.info(
                "Bedrock response received from modelId=%s, length=%d chars",
                model_id,
                len(recommendation),
            )
            return recommendation
        except ClientError as exc:
            last_error = exc
            error_code = exc.response["Error"]["Code"]
            logger.warning(
                "Bedrock call failed for modelId=%s (code=%s): %s",
                model_id,
                error_code,
                exc.response["Error"].get("Message", "no error message"),
            )
            continue
        except Exception as exc:
            last_error = exc
            logger.exception("Unexpected Bedrock invocation failure for modelId=%s", model_id)
            continue

    if isinstance(last_error, ClientError):
        error_code = last_error.response["Error"].get("Code", "Unknown")
        if error_code in ("ResourceNotFoundException", "ValidationException"):
            logger.error(
                "No usable Bedrock target for region=%s. Tried model IDs=%s. "
                "Likely causes: model not enabled in Bedrock Model access, model unavailable in this region, "
                "or missing BEDROCK_INFERENCE_PROFILE_ID for cross-region routing.",
                os.environ.get("AWS_REGION", "unknown"),
                model_candidates,
            )
        elif error_code == "AccessDeniedException":
            logger.error(
                "Access denied for Bedrock model invocation. Ensure Lambda role has "
                "bedrock:InvokeModel on foundation-model and inference-profile resources. "
                "Tried model IDs=%s",
                model_candidates,
            )
        raise last_error

    if last_error:
        raise last_error

    raise RuntimeError("Bedrock invocation failed: no model candidates were configured")


# ── DynamoDB persistence ─────────────────────────────────────────────────────

def save_recommendation(
    user_id: str,
    feedback_id: str,
    feedback_text: str,
    recommendation: str,
) -> None:
    """Persist the recommendation item to DynamoDB."""
    table = dynamodb.Table(TABLE_NAME)
    item = {
        "user_id": user_id,
        "feedback_id": feedback_id,
        "feedback_text": feedback_text,
        "recommendation": recommendation,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        table.put_item(Item=item)
        logger.info("Saved recommendation user_id=%s feedback_id=%s", user_id, feedback_id)
    except Exception:
        logger.exception("DynamoDB PutItem failed for feedback_id=%s", feedback_id)
        raise  # Re-raise → SQS retry


# ── Handler ──────────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> None:
    """
    Processes one SQS record at a time (batch_size=1).
    Any unhandled exception is re-raised so SQS can retry the message.
    """
    records = event.get("Records", [])
    logger.info("ProcessFeedbackFunction received %d record(s)", len(records))

    for record in records:
        try:
            payload = parse_sqs_sns_message(record)
        except (KeyError, json.JSONDecodeError):
            logger.exception("Failed to parse SQS/SNS message: %s", record.get("body"))
            raise  # Malformed message — let it go to DLQ

        user_id: str = payload["user_id"]
        feedback_id: str = payload["feedback_id"]
        feedback_text: str = payload["feedback_text"]

        logger.info("Processing user_id=%s feedback_id=%s", user_id, feedback_id)

        recommendation = get_recommendation(feedback_text)
        save_recommendation(user_id, feedback_id, feedback_text, recommendation)

    logger.info("ProcessFeedbackFunction completed successfully")
