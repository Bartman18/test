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
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.titan-text-express-v1")

# Log resolved config on cold start — visible in CloudWatch Logs
logger.info(
    "ProcessFeedbackFunction cold start: TABLE_NAME=%s BEDROCK_MODEL_ID=%s",
    TABLE_NAME,
    BEDROCK_MODEL_ID,
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
        "You are a professional career coach.\n"
        "A person received the following feedback from their manager:\n\n"
        f'"{feedback_text}"\n\n'
        "Please provide:\n"
        "1. Key areas for improvement\n"
        "2. Specific actionable steps\n"
        "3. Relevant training or certifications to consider\n"
    )

    request_body = json.dumps(
        {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 512,
                "temperature": 0.7,
                "topP": 0.9,
            },
        }
    )

    logger.info("Invoking Bedrock model=%s", BEDROCK_MODEL_ID)
    try:
        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=request_body,
        )
        result = json.loads(response["body"].read())
        recommendation: str = result["results"][0]["outputText"]
        logger.info("Bedrock response received, length=%d chars", len(recommendation))
        return recommendation
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            logger.error(
                "Bedrock model '%s' not found or not enabled. "
                "Go to AWS Console → Amazon Bedrock → Model access and enable this model "
                "for region %s, then redeploy.",
                BEDROCK_MODEL_ID,
                os.environ.get("AWS_REGION", "unknown"),
            )
        elif error_code == "AccessDeniedException":
            logger.error(
                "Access denied calling Bedrock model '%s'. "
                "Check the Lambda IAM role has bedrock:InvokeModel permission "
                "and the model is enabled in Bedrock Model access.",
                BEDROCK_MODEL_ID,
            )
        else:
            logger.exception("Bedrock ClientError for model=%s", BEDROCK_MODEL_ID)
        raise  # Re-raise → SQS will retry → DLQ after max_receive_count
    except Exception:
        logger.exception("Bedrock invocation failed for model=%s", BEDROCK_MODEL_ID)
        raise  # Re-raise → SQS will retry → DLQ after max_receive_count


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
