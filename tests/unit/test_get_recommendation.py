"""
Unit tests — GetRecommendationFunction
Phase 9 — Testing Agent

Coverage:
  ✓ Happy path with feedback_id → single item returned (200)
  ✓ Happy path without feedback_id → all items returned (200)
  ✓ feedback_id not found → 404
  ✓ No items for user → 404
  ✓ Missing Cognito claims → 500
  ✓ DynamoDB GetItem failure → 500
  ✓ DynamoDB Query failure → 500
"""
import json
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../lambda/get_recommendation"))

BASE_EVENT = {
    "queryStringParameters": None,
    "requestContext": {
        "authorizer": {
            "claims": {"sub": "user-test-789"}
        }
    },
}

SAMPLE_ITEM = {
    "user_id": "user-test-789",
    "feedback_id": "fb-id-001",
    "feedback_text": "Improve code reviews",
    "recommendation": "Take a course on clean code practices.",
    "timestamp": "2026-03-17T10:00:00+00:00",
}


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "Recommendations")


@patch("handler.dynamodb")
def test_get_recommendation_with_feedback_id_returns_200(mock_dynamodb):
    """GetItem: found item returns 200 with the item."""
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.get_item.return_value = {"Item": SAMPLE_ITEM}

    event = {
        **BASE_EVENT,
        "queryStringParameters": {"feedback_id": "fb-id-001"},
    }

    from handler import lambda_handler
    response = lambda_handler(event, {})

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["feedback_id"] == "fb-id-001"
    mock_table.get_item.assert_called_once_with(
        Key={"user_id": "user-test-789", "feedback_id": "fb-id-001"}
    )


@patch("handler.dynamodb")
def test_get_recommendation_with_feedback_id_not_found_returns_404(mock_dynamodb):
    """GetItem: item not found returns 404."""
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.get_item.return_value = {}  # No "Item" key

    event = {
        **BASE_EVENT,
        "queryStringParameters": {"feedback_id": "fb-id-nonexistent"},
    }

    from handler import lambda_handler
    response = lambda_handler(event, {})

    assert response["statusCode"] == 404
    assert "not found" in json.loads(response["body"])["error"].lower()


@patch("handler.dynamodb")
def test_get_all_recommendations_returns_200(mock_dynamodb):
    """Query: multiple items found returns 200 with items list."""
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.query.return_value = {"Items": [SAMPLE_ITEM, {**SAMPLE_ITEM, "feedback_id": "fb-id-002"}]}

    from handler import lambda_handler
    response = lambda_handler(BASE_EVENT, {})

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["count"] == 2
    assert len(body["items"]) == 2


@patch("handler.dynamodb")
def test_get_all_recommendations_no_items_returns_404(mock_dynamodb):
    """Query: no items returns 404."""
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.query.return_value = {"Items": []}

    from handler import lambda_handler
    response = lambda_handler(BASE_EVENT, {})

    assert response["statusCode"] == 404


@patch("handler.dynamodb")
def test_get_recommendation_missing_cognito_claims_returns_500(mock_dynamodb):
    """Missing Cognito claims returns 500."""
    event = {**BASE_EVENT, "requestContext": {}}

    from handler import lambda_handler
    response = lambda_handler(event, {})

    assert response["statusCode"] == 500


@patch("handler.dynamodb")
def test_get_recommendation_dynamodb_getitem_failure_returns_500(mock_dynamodb):
    """DynamoDB GetItem exception returns 500."""
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.get_item.side_effect = Exception("DynamoDB unavailable")

    event = {**BASE_EVENT, "queryStringParameters": {"feedback_id": "fb-id-001"}}

    from handler import lambda_handler
    response = lambda_handler(event, {})

    assert response["statusCode"] == 500


@patch("handler.dynamodb")
def test_get_recommendation_dynamodb_query_failure_returns_500(mock_dynamodb):
    """DynamoDB Query exception returns 500."""
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.query.side_effect = Exception("DynamoDB unavailable")

    from handler import lambda_handler
    response = lambda_handler(BASE_EVENT, {})

    assert response["statusCode"] == 500
