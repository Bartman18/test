"""
Unit tests — PostFeedbackFunction
Phase 9 — Testing Agent

Coverage:
  ✓ Happy path → 202 with feedback_id
  ✓ Missing feedback_text → 400
  ✓ Empty feedback_text → 400
  ✓ Invalid JSON body → 400
  ✓ Missing Cognito claims → 500
  ✓ SNS publish failure → re-raises exception
"""
import json
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# Make the lambda directory importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../lambda/post_feedback"))

BASE_EVENT = {
    "body": json.dumps({"feedback_text": "You need to improve communication skills"}),
    "requestContext": {
        "authorizer": {
            "claims": {"sub": "user-test-123"}
        }
    },
}


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:FeedbackTopic")


@patch("handler.sns_client")
def test_post_feedback_happy_path_returns_202(mock_sns):
    """Happy path: valid input returns 202 with a feedback_id."""
    mock_sns.publish.return_value = {"MessageId": "msg-abc-123"}

    from handler import lambda_handler  # noqa: PLC0415
    response = lambda_handler(BASE_EVENT, {})

    assert response["statusCode"] == 202
    body = json.loads(response["body"])
    assert "feedback_id" in body
    assert len(body["feedback_id"]) == 36  # UUID v4 format

    mock_sns.publish.assert_called_once()
    call_kwargs = mock_sns.publish.call_args[1]
    assert call_kwargs["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:FeedbackTopic"
    published_message = json.loads(call_kwargs["Message"])
    assert published_message["user_id"] == "user-test-123"
    assert published_message["feedback_text"] == "You need to improve communication skills"


@patch("handler.sns_client")
def test_post_feedback_missing_feedback_text_returns_400(mock_sns):
    """Missing feedback_text field in body returns 400."""
    event = {**BASE_EVENT, "body": json.dumps({})}

    from handler import lambda_handler
    response = lambda_handler(event, {})

    assert response["statusCode"] == 400
    assert "feedback_text" in json.loads(response["body"])["error"]
    mock_sns.publish.assert_not_called()


@patch("handler.sns_client")
def test_post_feedback_empty_feedback_text_returns_400(mock_sns):
    """Empty string feedback_text returns 400."""
    event = {**BASE_EVENT, "body": json.dumps({"feedback_text": "   "})}

    from handler import lambda_handler
    response = lambda_handler(event, {})

    assert response["statusCode"] == 400
    mock_sns.publish.assert_not_called()


@patch("handler.sns_client")
def test_post_feedback_invalid_json_body_returns_400(mock_sns):
    """Non-JSON body returns 400."""
    event = {**BASE_EVENT, "body": "not-valid-json"}

    from handler import lambda_handler
    response = lambda_handler(event, {})

    assert response["statusCode"] == 400
    mock_sns.publish.assert_not_called()


@patch("handler.sns_client")
def test_post_feedback_missing_cognito_claims_returns_500(mock_sns):
    """Missing Cognito authorizer claims returns 500."""
    event = {**BASE_EVENT, "requestContext": {}}

    from handler import lambda_handler
    response = lambda_handler(event, {})

    assert response["statusCode"] == 500
    mock_sns.publish.assert_not_called()


@patch("handler.sns_client")
def test_post_feedback_sns_failure_raises(mock_sns):
    """SNS publish failure re-raises (Lambda runtime handles retries)."""
    mock_sns.publish.side_effect = Exception("SNS unavailable")

    from handler import lambda_handler
    with pytest.raises(Exception, match="SNS unavailable"):
        lambda_handler(BASE_EVENT, {})
