"""
Integration test — End-to-End feedback submission and recommendation retrieval.

Prerequisites (set as environment variables or in a .env file):
    API_URL              Base API Gateway URL, e.g.
                         https://<id>.execute-api.eu-central-1.amazonaws.com/prod
    COGNITO_USER_POOL_ID Cognito User Pool ID (CfnOutput: FeedbackUserPoolId)
    COGNITO_CLIENT_ID    Cognito App Client ID (CfnOutput: FeedbackUserPoolClientId)
    TEST_USER_EMAIL      Email of a pre-created Cognito test user
    TEST_USER_PASSWORD   Password of that test user

The tests are skipped automatically when the variables are not set so they
don't block the CI unit-test job.
"""
import json
import os
import time

import pytest
import boto3
import requests

# ── Config ────────────────────────────────────────────────────────────────────
API_URL = os.getenv("API_URL", "").rstrip("/")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")
TEST_USER_EMAIL = os.getenv("TEST_USER_EMAIL", "")
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "")

_MISSING_CONFIG = not all([API_URL, COGNITO_CLIENT_ID, TEST_USER_EMAIL, TEST_USER_PASSWORD])

pytestmark = pytest.mark.skipif(
    _MISSING_CONFIG,
    reason="Integration env vars not set (API_URL, COGNITO_CLIENT_ID, TEST_USER_EMAIL, TEST_USER_PASSWORD)",
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def id_token() -> str:
    """Authenticate a test Cognito user and return the IdToken JWT."""
    cognito = boto3.client("cognito-idp", region_name=os.getenv("AWS_DEFAULT_REGION", "eu-central-1"))
    response = cognito.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": TEST_USER_EMAIL,
            "PASSWORD": TEST_USER_PASSWORD,
        },
        ClientId=COGNITO_CLIENT_ID,
    )
    return response["AuthenticationResult"]["IdToken"]


@pytest.fixture(scope="module")
def auth_headers(id_token: str) -> dict:
    return {"Authorization": id_token, "Content-Type": "application/json"}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_post_feedback_returns_202(auth_headers: dict):
    """POST /feedback with valid input returns 202 and a feedback_id."""
    payload = {"feedback_text": "Integration test: needs to improve communication."}
    response = requests.post(f"{API_URL}/feedback", json=payload, headers=auth_headers, timeout=15)
    assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
    body = response.json()
    assert "feedback_id" in body
    assert len(body["feedback_id"]) == 36  # UUID v4


def test_post_feedback_missing_body_returns_400(auth_headers: dict):
    """POST /feedback with no feedback_text returns 400."""
    response = requests.post(f"{API_URL}/feedback", json={}, headers=auth_headers, timeout=15)
    assert response.status_code == 400


def test_get_recommendation_returns_200_after_processing(auth_headers: dict):
    """
    Full async flow:
      1. POST /feedback → get feedback_id
      2. Poll GET /recommendation?feedback_id=<id> until recommendation appears
         (Lambda #2 is triggered async via SNS → SQS, may take several seconds)
    """
    # Step 1: submit feedback
    payload = {"feedback_text": "Integration test: needs to delegate more effectively."}
    post_resp = requests.post(f"{API_URL}/feedback", json=payload, headers=auth_headers, timeout=15)
    assert post_resp.status_code == 202
    feedback_id = post_resp.json()["feedback_id"]

    # Step 2: poll until recommendation is ready (max 90s)
    deadline = time.time() + 90
    recommendation_body = None
    while time.time() < deadline:
        get_resp = requests.get(
            f"{API_URL}/recommendation",
            params={"feedback_id": feedback_id},
            headers=auth_headers,
            timeout=15,
        )
        if get_resp.status_code == 200:
            recommendation_body = get_resp.json()
            break
        assert get_resp.status_code == 404, (
            f"Unexpected status {get_resp.status_code}: {get_resp.text}"
        )
        time.sleep(5)

    assert recommendation_body is not None, "Recommendation was not ready within 90 seconds"
    assert "recommendation" in recommendation_body
    assert recommendation_body["feedback_id"] == feedback_id


def test_get_all_recommendations_returns_200(auth_headers: dict):
    """GET /recommendation without feedback_id returns all items for the user."""
    response = requests.get(f"{API_URL}/recommendation", headers=auth_headers, timeout=15)
    assert response.status_code in (200, 404)  # 404 acceptable if user has no items yet
    if response.status_code == 200:
        body = response.json()
        assert "items" in body


def test_get_recommendation_not_found_returns_404(auth_headers: dict):
    """GET /recommendation with a nonexistent feedback_id returns 404."""
    response = requests.get(
        f"{API_URL}/recommendation",
        params={"feedback_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers,
        timeout=15,
    )
    assert response.status_code == 404


def test_unauthenticated_request_returns_401(auth_headers: dict):
    """Requests without Authorization header are rejected by API Gateway."""
    no_auth = {"Content-Type": "application/json"}
    response = requests.post(f"{API_URL}/feedback", json={"feedback_text": "test"}, headers=no_auth, timeout=15)
    assert response.status_code in (401, 403)
