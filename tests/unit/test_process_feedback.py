"""
Unit tests — ProcessFeedbackFunction
Phase 9 — Testing Agent

Coverage:
  ✓ Happy path → Bedrock called, item saved to DynamoDB
  ✓ Malformed SQS body → re-raises (→ DLQ)
  ✓ Bedrock failure → re-raises (→ SQS retry → DLQ)
  ✓ DynamoDB failure → re-raises (→ SQS retry → DLQ)
  ✓ SNS envelope correctly unwrapped
"""
import json
import sys
import os
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../lambda/process_feedback"))


PAYLOAD = {
    "user_id": "user-test-456",
    "feedback_id": "fb-id-789",
    "feedback_text": "Needs to improve leadership skills",
}

# SNS notification wraps the payload in a "Message" key (JSON string)
SNS_ENVELOPE = json.dumps({"Message": json.dumps(PAYLOAD)})

SQS_EVENT = {
    "Records": [
        {
            "body": SNS_ENVELOPE,
            "receiptHandle": "abc-receipt",
        }
    ]
}


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "Recommendations")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "qwen.qwen3-32b-v1:0")
    monkeypatch.setenv("BEDROCK_FALLBACK_MODEL_ID", "mistral.mistral-7b-instruct-v0:2")


@patch("handler.dynamodb")
@patch("handler.bedrock_client")
def test_process_feedback_happy_path(mock_bedrock, mock_dynamodb):
    """Happy path: Bedrock returns recommendation, item saved to DynamoDB."""
    # Mock Bedrock response — Converse API format
    mock_bedrock.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": "Focus on active listening and delegation."}]
            }
        }
    }

    # Mock DynamoDB Table
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.put_item.return_value = {}

    from handler import lambda_handler
    lambda_handler(SQS_EVENT, {})

    # Bedrock was called
    mock_bedrock.converse.assert_called_once()
    call_kwargs = mock_bedrock.converse.call_args[1]
    assert call_kwargs["modelId"] == "qwen.qwen3-32b-v1:0"
    messages = call_kwargs["messages"]
    assert PAYLOAD["feedback_text"] in messages[0]["content"][0]["text"]

    # DynamoDB put_item was called with correct keys
    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["user_id"] == PAYLOAD["user_id"]
    assert item["feedback_id"] == PAYLOAD["feedback_id"]
    assert item["recommendation"] == "Focus on active listening and delegation."
    assert "timestamp" in item


@patch("handler.dynamodb")
@patch("handler.bedrock_client")
def test_process_feedback_malformed_sqs_body_raises(mock_bedrock, mock_dynamodb):
    """Malformed SQS body (not valid JSON) causes re-raise."""
    bad_event = {"Records": [{"body": "not-json", "receiptHandle": "x"}]}

    from handler import lambda_handler
    with pytest.raises(Exception):
        lambda_handler(bad_event, {})

    mock_bedrock.converse.assert_not_called()


@patch("handler.dynamodb")
@patch("handler.bedrock_client")
def test_process_feedback_bedrock_failure_raises(mock_bedrock, mock_dynamodb):
    """Bedrock failure re-raises so SQS can retry the message."""
    mock_bedrock.converse.side_effect = Exception("Bedrock throttled")

    from handler import lambda_handler
    with pytest.raises(Exception, match="Bedrock throttled"):
        lambda_handler(SQS_EVENT, {})


@patch("handler.dynamodb")
@patch("handler.bedrock_client")
def test_process_feedback_dynamodb_failure_raises(mock_bedrock, mock_dynamodb):
    """DynamoDB failure re-raises so SQS can retry the message."""
    mock_bedrock.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": "Some recommendation"}]
            }
        }
    }

    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.put_item.side_effect = Exception("DynamoDB write failed")

    from handler import lambda_handler
    with pytest.raises(Exception, match="DynamoDB write failed"):
        lambda_handler(SQS_EVENT, {})
