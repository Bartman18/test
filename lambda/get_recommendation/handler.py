"""
Lambda #3 — GetRecommendationFunction
Phase 5 — Python Lambda Agent

Triggered by: API Gateway GET /recommendation (Cognito-authorized)
Responsibilities:
  1. Extract user_id from Cognito authorizer claims (sub)
  2. Optionally read feedback_id from query string parameters
  3a. If feedback_id provided  → GetItem (single recommendation)
  3b. If no feedback_id        → Query all recommendations for this user
  4. Return HTTP 200 with results, or HTTP 404 if not found
"""
import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ["TABLE_NAME"]


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
    logger.info("GetRecommendationFunction invoked")

    # ── Extract authenticated user_id ────────────────────────────────────────
    try:
        user_id: str = event["requestContext"]["authorizer"]["claims"]["sub"]
    except (KeyError, TypeError):
        logger.error("Missing Cognito sub claim")
        return build_response(500, {"error": "Could not determine authenticated user"})

    # ── Optional query string parameter ─────────────────────────────────────
    query_params: dict = event.get("queryStringParameters") or {}
    feedback_id: str | None = query_params.get("feedback_id")

    table = dynamodb.Table(TABLE_NAME)

    # ── Single item lookup ───────────────────────────────────────────────────
    if feedback_id:
        logger.info("GetItem user_id=%s feedback_id=%s", user_id, feedback_id)
        try:
            response = table.get_item(
                Key={"user_id": user_id, "feedback_id": feedback_id}
            )
        except Exception:
            logger.exception("DynamoDB GetItem failed")
            return build_response(500, {"error": "Failed to retrieve recommendation"})

        item = response.get("Item")
        if not item:
            return build_response(
                404,
                {"error": f"Recommendation not found for feedback_id={feedback_id}"},
            )
        return build_response(200, item)

    # ── Query all recommendations for user ───────────────────────────────────
    logger.info("Query all recommendations for user_id=%s", user_id)
    try:
        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id)
        )
    except Exception:
        logger.exception("DynamoDB Query failed for user_id=%s", user_id)
        return build_response(500, {"error": "Failed to retrieve recommendations"})

    items = response.get("Items", [])
    # Return 200 with empty array — the collection exists, it is just empty.
    # 404 is reserved for a specific feedback_id that has not been processed yet.
    return build_response(200, {"items": items, "count": len(items)})
