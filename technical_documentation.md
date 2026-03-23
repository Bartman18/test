# Technical Documentation — Serverless Feedback & Recommendation App

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Architecture Overview](#3-architecture-overview)
4. [Project Structure](#4-project-structure)
5. [Infrastructure (AWS CDK Stacks)](#5-infrastructure-aws-cdk-stacks)
6. [Lambda Functions](#6-lambda-functions)
7. [API Reference](#7-api-reference)
8. [Authentication & Authorization](#8-authentication--authorization)
9. [Messaging Pipeline](#9-messaging-pipeline)
10. [Database](#10-database)
11. [AI Integration (Amazon Bedrock)](#11-ai-integration-amazon-bedrock)
12. [Front-End Application](#12-front-end-application)
13. [Testing](#13-testing)
14. [Deployment](#14-deployment)
15. [Environment Variables](#15-environment-variables)
16. [CloudFormation Outputs](#16-cloudformation-outputs)
17. [Error Handling & Observability](#17-error-handling--observability)
18. [Security](#18-security)

---

## 1. Project Overview

**Serverless Feedback & Recommendation App** is a fully serverless, cloud-native application that allows authenticated users to submit manager feedback and receive concise, AI-generated career improvement recommendations.

The application follows an **asynchronous processing pattern**: feedback is accepted immediately (HTTP 202) and processed in the background via a messaging pipeline. Results are stored in DynamoDB and retrievable at any time.

### Key Design Principles
- **Async by default** — feedback submission is decoupled from AI processing via SNS → SQS
- **Least-privilege IAM** — each Lambda only has the permissions it needs
- **Infrastructure as Code** — entire backend defined in Python using AWS CDK v2
- **No business logic in stacks** — CDK files define infrastructure only; logic lives in Lambda handlers

---

## 2. Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Infrastructure (IaC) | AWS CDK v2 | `>=2.100.0` |
| IaC Language | Python | 3.11+ |
| Authentication | Amazon Cognito User Pool | — |
| REST API | Amazon API Gateway (REST) | — |
| Compute | AWS Lambda | Python 3.11 |
| Messaging (pub/sub) | Amazon SNS | — |
| Messaging (queue) | Amazon SQS | — |
| Database | Amazon DynamoDB | — |
| AI / LLM | Amazon Bedrock | Converse API |
| AI Model (primary) | `qwen.qwen3-32b-v1:0` | — |
| AI Model (fallback) | `mistral.mistral-7b-instruct-v0:2` | — |
| Front-End Framework | React | `^18.3.1` |
| Front-End Auth UI | `@aws-amplify/ui-react` | `^6.6.0` |
| Front-End Amplify | `aws-amplify` | `^6.13.0` |
| Routing | `react-router-dom` | `^6.23.1` |
| Unit Testing | pytest | `>=7.4.0` |
| Mocking | `unittest.mock` | stdlib |
| AWS Service Mocking | moto (SNS, SQS, DynamoDB) | `>=4.2.0` |
| HTTP Client (tests) | requests | `>=2.31.0` |
| CDK Assertions | `aws_cdk.assertions` | — |

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                          FRONT-END                               │
│   React + AWS Amplify  (@aws-amplify/ui-react Authenticator)     │
└──────────────────────────┬───────────────────────────────────────┘
                           │  HTTPS + JWT (Cognito IdToken)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│              Amazon API Gateway (REST API — prod stage)          │
│  POST /feedback          │   GET /recommendation[?feedback_id=]  │
│  ↓ Cognito Authorizer    │   ↓ Cognito Authorizer                │
└──────────┬───────────────┴──────────────────────┬───────────────┘
           │                                       │
           ▼                                       ▼
┌──────────────────────┐              ┌────────────────────────────┐
│  Lambda #1           │              │  Lambda #3                 │
│  PostFeedbackFn      │              │  GetRecommendationFn       │
│  (Python 3.11)       │              │  (Python 3.11)             │
│  → Publishes to SNS  │              │  → Queries DynamoDB        │
│  → Returns 202       │              │  → Returns 200/404         │
└──────────┬───────────┘              └────────────────────────────┘
           │                                       ▲
           ▼                                       │
┌──────────────────────┐                           │
│  Amazon SNS Topic    │                           │
│  FeedbackTopic       │                           │
└──────────┬───────────┘                           │
           │ SqsSubscription (SNS envelope)        │
           ▼                                       │
┌──────────────────────┐                           │
│  Amazon SQS Queue    │                           │
│  FeedbackQueue       │◄── DLQ (max_receive=3)    │
│  visibility: 30 min  │                           │
└──────────┬───────────┘                           │
           │ SQS Event Source (batch_size=1)        │
           ▼                                       │
┌──────────────────────┐              ┌────────────────────────────┐
│  Lambda #2           │              │  Amazon DynamoDB           │
│  ProcessFeedbackFn   │─────────────►│  Recommendations table     │
│  (Python 3.11)       │  PutItem     │  PK: user_id  SK:feedback_id│
│  → Calls Bedrock     │              └────────────────────────────┘
│  → Saves to DynamoDB │
└──────────┬───────────┘
           │ Converse API
           ▼
┌──────────────────────┐
│  Amazon Bedrock      │
│  Primary:  qwen3-32b │
│  Fallback: mistral   │
└──────────────────────┘

      ┌────────────────────────┐
      │  Amazon Cognito        │
      │  User Pool             │
      │  · Email sign-up/in    │
      │  · JWT issued on login │
      └────────────────────────┘
```

### Request Flow — POST /feedback
1. User submits feedback via the React UI
2. Amplify attaches the Cognito JWT as an `Authorization` header
3. API Gateway validates the JWT with Cognito Authorizer
4. **Lambda #1** parses `feedback_text`, generates a UUID `feedback_id`, publishes to SNS, returns **HTTP 202**
5. SNS delivers the message to SQS (with SNS envelope)
6. **Lambda #2** is triggered by the SQS event source mapping, unwraps the SNS envelope, calls Bedrock Converse API, saves result to DynamoDB

### Request Flow — GET /recommendation
1. React UI polls with `Authorization` header + optional `?feedback_id=<uuid>`
2. API Gateway validates JWT
3. **Lambda #3** performs `GetItem` (single) or `Query` (all) on DynamoDB, returns items

---

## 4. Project Structure

```
.
├── app/
│   ├── app.py                          # CDK entry point — synthesises FeedbackAppStage
│   ├── lambda/
│   │   ├── post_feedback/
│   │   │   ├── handler.py              # Lambda #1 handler
│   │   │   └── requirements.txt
│   │   ├── process_feedback/
│   │   │   ├── handler.py              # Lambda #2 handler (Bedrock + DynamoDB)
│   │   │   └── requirements.txt
│   │   └── get_recommendation/
│   │       ├── handler.py              # Lambda #3 handler
│   │       └── requirements.txt
│   ├── stacks/
│   │   ├── cognito_stack.py            # Cognito User Pool + App Client
│   │   ├── database_stack.py           # DynamoDB Recommendations table
│   │   ├── messaging_stack.py          # SNS Topic + SQS Queue + DLQ
│   │   ├── lambda_stack.py             # All 3 Lambda functions + IAM grants
│   │   └── api_stack.py                # API Gateway REST API + Cognito Authorizer
│   ├── stages/
│   │   └── feedback_stage.py           # Wires all stacks together
│   └── tests/
│       ├── unit/
│       │   ├── test_stacks.py          # CDK Template assertion tests
│       │   ├── test_post_feedback.py   # Lambda #1 unit tests
│       │   ├── test_process_feedback.py# Lambda #2 unit tests
│       │   └── test_get_recommendation.py # Lambda #3 unit tests
│       └── integration/
│           └── test_e2e.py             # End-to-end integration tests (real AWS)
├── front-end/
│   ├── src/
│   │   ├── App.js                      # Root component + Authenticator wrapper
│   │   ├── aws-exports.js              # Amplify configuration (from CfnOutputs)
│   │   ├── components/
│   │   │   └── FeedbackForm.js         # POST /feedback form
│   │   ├── pages/
│   │   │   └── RecommendationsPage.js  # GET /recommendation page
│   │   └── lib/                        # Shared utilities (API client, etc.)
│   └── package.json
├── requirements.txt                    # Python dependencies (CDK + testing)
├── pytest.ini                          # pytest configuration
├── cdk.json                            # CDK app configuration
└── .github/
    └── agents/
        ├── documentation_agent.md      # Documentation agent definition
        └── technical_documentation.md  # This file
```

---

## 5. Infrastructure (AWS CDK Stacks)

All stacks live under `app/stacks/`. They are assembled in `app/stages/feedback_stage.py` and synthesised via `app/app.py`.

### CognitoStack (`stacks/cognito_stack.py`)
Creates the Cognito User Pool and App Client.

| Resource | Details |
|---|---|
| User Pool | Email sign-in, self-sign-up enabled, email auto-verify |
| Password Policy | Min 8 chars, requires uppercase + digits |
| App Client | `AmplifyAppClient` — no secret (SPA), supports `USER_PASSWORD_AUTH` + `USER_SRP_AUTH` |
| Account Recovery | Email only |
| Removal Policy | `DESTROY` (dev/test) |

**Public properties exposed:** `user_pool`, `app_client`

---

### DatabaseStack (`stacks/database_stack.py`)
Creates the DynamoDB `Recommendations` table.

| Attribute | Value |
|---|---|
| Table Name | `Recommendations` |
| Partition Key | `user_id` (String) — Cognito `sub` claim |
| Sort Key | `feedback_id` (String) — UUID v4 |
| Billing Mode | `PAY_PER_REQUEST` (on-demand) |
| PITR | Enabled |
| TTL Attribute | `ttl` (epoch seconds) |
| Removal Policy | `DESTROY` (dev/test) |

**Additional item attributes (written by Lambda #2):**
- `feedback_text` — original feedback submitted by user
- `recommendation` — AI-generated text from Bedrock
- `timestamp` — ISO 8601 UTC string

**Public properties exposed:** `table`

---

### MessagingStack (`stacks/messaging_stack.py`)
Creates the async messaging layer.

| Resource | Details |
|---|---|
| SNS Topic | `FeedbackTopic` |
| SQS Queue | `FeedbackQueue` — visibility timeout: **1800s (30 min)** |
| Dead Letter Queue | `FeedbackDLQ` — retention: 14 days |
| DLQ Threshold | `max_receive_count=3` |
| SNS→SQS subscription | `raw_message_delivery=False` (SNS envelope preserved) |

> **Note:** The visibility timeout must be ≥ 6× Lambda #2 timeout. Lambda #2 has a 5-minute timeout → 6 × 300s = 1800s.

**Public properties exposed:** `topic`, `queue`, `dlq`

---

### LambdaStack (`stacks/lambda_stack.py`)
Creates all three Lambda functions with runtime configuration, environment variables, and IAM grants.

| Function | Timeout | Memory | Trigger |
|---|---|---|---|
| `PostFeedbackFunction` | 30s | 256 MB | API Gateway POST /feedback |
| `ProcessFeedbackFunction` | 5 min | 512 MB | SQS Event Source (batch=1) |
| `GetRecommendationFunction` | 30s | 256 MB | API Gateway GET /recommendation |

**Common configuration for all functions:**
- Runtime: `PYTHON_3_11`
- X-Ray tracing: `ACTIVE`
- Log retention: `ONE_WEEK`
- Handler: `handler.lambda_handler`

**IAM Grants:**
- Lambda #1 → `topic.grant_publish()` (SNS publish only)
- Lambda #2 → `table.grant_read_write_data()` (DynamoDB R/W)
- Lambda #2 → `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` (scoped to specific model ARNs)
- Lambda #3 → `table.grant_read_data()` (DynamoDB read only)

**Public properties exposed:** `post_feedback_fn`, `process_feedback_fn`, `get_recommendation_fn`

---

### ApiStack (`stacks/api_stack.py`)
Creates the REST API Gateway with Cognito authorizer.

| Resource | Details |
|---|---|
| API Name | `FeedbackService` |
| Stage | `prod` |
| Tracing | Enabled (X-Ray) |
| Logging Level | `INFO` |
| CORS | All origins, all methods, `Authorization` + `Content-Type` headers |
| Authorizer | `CognitoUserPoolsAuthorizer` — validates JWT from `Authorization` header |

**Endpoints:**

| Method | Path | Lambda | Auth | Response |
|---|---|---|---|---|
| `POST` | `/feedback` | PostFeedbackFunction | Cognito JWT | 202 Accepted |
| `GET` | `/recommendation` | GetRecommendationFunction | Cognito JWT | 200 / 404 |

**Public properties exposed:** `api`

---

## 6. Lambda Functions

### Lambda #1 — PostFeedbackFunction
**File:** `lambda/post_feedback/handler.py`

**Trigger:** `POST /feedback` via API Gateway

**Flow:**
1. Parse `feedback_text` from JSON body → return `400` if missing or empty
2. Extract `user_id` from `event["requestContext"]["authorizer"]["claims"]["sub"]`
3. Generate `feedback_id = str(uuid.uuid4())`
4. Publish JSON payload to SNS topic
5. Return `202 Accepted` with `{ "feedback_id": "<uuid>" }`

**Environment Variables:**

| Variable | Description |
|---|---|
| `SNS_TOPIC_ARN` | ARN of the FeedbackTopic |

---

### Lambda #2 — ProcessFeedbackFunction
**File:** `lambda/process_feedback/handler.py`

**Trigger:** SQS Event Source Mapping from `FeedbackQueue` (batch size: 1)

**Flow:**
1. Unwrap SNS-over-SQS envelope: `json.loads(record["body"])["Message"]`
2. Parse `user_id`, `feedback_id`, `feedback_text`
3. Build career-coach prompt
4. Call Bedrock Converse API (tries primary model, then fallback)
5. Save `{ user_id, feedback_id, feedback_text, recommendation, timestamp }` to DynamoDB via `PutItem`
6. Re-raise any exception → SQS retries → DLQ after 3 attempts

**Environment Variables:**

| Variable | Default | Description |
|---|---|---|
| `TABLE_NAME` | — | DynamoDB table name |
| `BEDROCK_MODEL_ID` | `qwen.qwen3-32b-v1:0` | Primary Bedrock model ID |
| `BEDROCK_FALLBACK_MODEL_ID` | `mistral.mistral-7b-instruct-v0:2` | Fallback model ID |
| `BEDROCK_INFERENCE_PROFILE_ID` | *(unset)* | Optional inference profile ARN |

**Bedrock Prompt:**
```
You are a career coach. Read the manager feedback below and reply with
2-3 concise sentences that tell the person exactly what to improve and one
concrete action they can take immediately. Do not use bullet points, headers,
or numbered lists — plain sentences only.

Feedback: "<feedback_text>"
```

---

### Lambda #3 — GetRecommendationFunction
**File:** `lambda/get_recommendation/handler.py`

**Trigger:** `GET /recommendation` via API Gateway

**Flow:**
1. Extract `user_id` from Cognito claims
2. Read optional `?feedback_id=` query string parameter
3. If `feedback_id` provided → `GetItem` → return `200` or `404`
4. If no `feedback_id` → `Query` all items for `user_id` → return `200` with `{ "items": [...] }`

**Environment Variables:**

| Variable | Description |
|---|---|
| `TABLE_NAME` | DynamoDB table name |

---

## 7. API Reference

### Base URL
```
https://<api-id>.execute-api.<region>.amazonaws.com/prod
```

### Authentication
All requests must include a valid Cognito JWT in the `Authorization` header:
```
Authorization: <IdToken>
```

---

### POST /feedback

**Description:** Submit manager feedback for async AI processing.

**Request Body:**
```json
{
  "feedback_text": "You need to work on your communication skills."
}
```

**Responses:**

| Status | Body | Description |
|---|---|---|
| `202` | `{ "feedback_id": "<uuid>" }` | Feedback accepted, processing started |
| `400` | `{ "error": "feedback_text is required and cannot be empty" }` | Missing or empty input |
| `500` | `{ "error": "Could not determine authenticated user" }` | Auth context error |

---

### GET /recommendation

**Description:** Retrieve AI-generated recommendation(s) for the authenticated user.

**Query Parameters:**

| Parameter | Required | Description |
|---|---|---|
| `feedback_id` | No | UUID of a specific feedback item |

**Responses:**

| Status | Body | Description |
|---|---|---|
| `200` | `{ "user_id": "...", "feedback_id": "...", "feedback_text": "...", "recommendation": "...", "timestamp": "..." }` | Single item (when `feedback_id` provided) |
| `200` | `{ "items": [ ... ] }` | All items for the user (no `feedback_id`) |
| `404` | `{ "error": "Recommendation not found for feedback_id=<uuid>" }` | Item not found |
| `500` | `{ "error": "..." }` | Internal error |

---

## 8. Authentication & Authorization

### Cognito User Pool
- **Sign-in mechanism:** Email + password
- **Self-sign-up:** Enabled
- **Email verification:** Automatic
- **Password requirements:** Min 8 chars, 1 uppercase, 1 digit

### JWT Flow
1. User signs in via the Amplify `<Authenticator />` component
2. Cognito issues an **IdToken** (JWT)
3. The React app retrieves it via `fetchAuthSession()` from `aws-amplify/auth`
4. Every API call includes it as: `Authorization: <IdToken>`
5. API Gateway's `CognitoUserPoolsAuthorizer` validates the token before invoking any Lambda
6. Lambda functions extract `user_id` from `event["requestContext"]["authorizer"]["claims"]["sub"]`

### Identity Pool
A Cognito Identity Pool is provisioned but does **not** grant any DynamoDB permissions directly. All data access is routed through the API Gateway → Lambda → DynamoDB chain.

---

## 9. Messaging Pipeline

The async pipeline decouples feedback ingestion from AI processing:

```
POST /feedback
     │
     ▼
Lambda #1 ──sns.publish()──► SNS FeedbackTopic
                                      │
                              SqsSubscription
                              (raw_message_delivery=False)
                                      │
                                      ▼
                              SQS FeedbackQueue
                              visibility_timeout=1800s
                              dead_letter_queue=FeedbackDLQ
                                      │
                              SQS Event Source Mapping
                              batch_size=1
                                      │
                                      ▼
                              Lambda #2 ProcessFeedbackFn
                              (unwrap SNS envelope, call Bedrock, write DynamoDB)
```

### Message Format (SNS payload)
```json
{
  "user_id": "<cognito-sub>",
  "feedback_id": "<uuid-v4>",
  "feedback_text": "<raw feedback string>"
}
```

### SNS-over-SQS Envelope Unwrapping (Lambda #2)
```python
sqs_body = json.loads(record["body"])   # SNS notification
payload  = json.loads(sqs_body["Message"])  # actual message
```

### Retry & DLQ Behaviour
| Scenario | Behaviour |
|---|---|
| Lambda #2 raises exception | SQS makes message visible again after 1800s |
| After 3 receive attempts | Message routed to `FeedbackDLQ` (retained 14 days) |
| DLQ investigation | Check CloudWatch Logs for Lambda #2, inspect DLQ message body |

---

## 10. Database

### Table: `Recommendations`

| Attribute | Type | Role |
|---|---|---|
| `user_id` | String | Partition key — Cognito `sub` |
| `feedback_id` | String | Sort key — UUID v4 |
| `feedback_text` | String | Original feedback text |
| `recommendation` | String | AI-generated career recommendation |
| `timestamp` | String | ISO 8601 UTC (e.g. `2026-03-22T10:30:00+00:00`) |
| `ttl` | Number | Optional epoch seconds — items auto-expire |

**Access Patterns:**
- **Single item:** `GetItem` by `(user_id, feedback_id)`
- **All user items:** `Query` by `user_id` (partition key only)

---

## 11. AI Integration (Amazon Bedrock)

Lambda #2 uses the **Bedrock Converse API** (`bedrock_client.converse()`), which provides a unified interface across different model families.

### Model Candidates (tried in order)
1. `BEDROCK_MODEL_ID` (default: `qwen.qwen3-32b-v1:0`)
2. `BEDROCK_INFERENCE_PROFILE_ID` (optional inference profile)
3. `BEDROCK_FALLBACK_MODEL_ID` (default: `mistral.mistral-7b-instruct-v0:2`)

### Converse API Request Structure
```python
bedrock_client.converse(
    modelId=model_id,
    messages=[
        {
            "role": "user",
            "content": [{"text": prompt}]
        }
    ],
    inferenceConfig={
        "maxTokens": 120,
        "temperature": 0.5,
    }
)
```

### Response Extraction
```python
response["output"]["message"]["content"][0]["text"]
```

### Error Handling
- Each model candidate is tried in a loop
- If all candidates fail, the last exception is re-raised
- Re-raising causes SQS to retry the message (up to 3 times → DLQ)

---

## 12. Front-End Application

**Location:** `front-end/`  
**Framework:** React 18 + AWS Amplify + `@aws-amplify/ui-react`

### Key Components

| File | Description |
|---|---|
| `src/App.js` | Root component, wraps everything in `<Authenticator />` |
| `src/aws-exports.js` | Amplify config (User Pool ID, Client ID, API URL from CfnOutputs) |
| `src/components/FeedbackForm.js` | Submits feedback via `POST /feedback`, displays `feedback_id` |
| `src/pages/RecommendationsPage.js` | Lists recommendations via `GET /recommendation` |

### Amplify Configuration (`aws-exports.js`)
```js
const awsExports = {
  Auth: {
    region: '<region>',
    userPoolId: '<UserPoolId CfnOutput>',
    userPoolWebClientId: '<UserPoolClientId CfnOutput>',
  },
  API: {
    endpoints: [
      {
        name: 'FeedbackAPI',
        endpoint: '<ApiUrl CfnOutput>',
      },
    ],
  },
};
export default awsExports;
```

### Auth Pattern
```js
import { fetchAuthSession } from 'aws-amplify/auth';

const { tokens } = await fetchAuthSession();
const idToken = tokens.idToken.toString();

fetch(`${API_URL}/feedback`, {
  method: 'POST',
  headers: {
    'Authorization': idToken,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ feedback_text: text }),
});
```

### Polling Pattern (202 → recommendation)
After receiving a `202` from `POST /feedback`:
1. Display "Processing your recommendation…" message
2. Poll `GET /recommendation?feedback_id=<id>` every few seconds
3. Stop polling when `200` is returned with a non-empty `recommendation`

---

## 13. Testing

### Running Unit Tests
```bash
# From project root
pytest app/tests/unit/ -v
```

### Running All Tests
```bash
pytest --cov=app --cov-report=term-missing
```

### Unit Tests

| File | What It Tests |
|---|---|
| `test_stacks.py` | CDK template assertions (no AWS account needed) |
| `test_post_feedback.py` | Lambda #1: 202 happy path, 400 missing input |
| `test_process_feedback.py` | Lambda #2: Bedrock call, DynamoDB save, SQS retry |
| `test_get_recommendation.py` | Lambda #3: 200 single, 200 list, 404 not found |

**Mock Strategy:**
```python
from unittest.mock import patch, MagicMock

@patch("post_feedback.handler.sns_client")
def test_post_feedback_returns_202(mock_sns):
    mock_sns.publish.return_value = {}
    event = {
        "body": json.dumps({"feedback_text": "Improve communication"}),
        "requestContext": {"authorizer": {"claims": {"sub": "user-123"}}},
    }
    response = lambda_handler(event, {})
    assert response["statusCode"] == 202
```

### CDK Stack Tests (`test_stacks.py`)
```python
from aws_cdk import assertions

template = assertions.Template.from_stack(stack)
template.has_resource_properties("AWS::DynamoDB::Table", {
    "TableName": "Recommendations",
    "BillingMode": "PAY_PER_REQUEST",
})
```

### Integration Tests (`test_e2e.py`)

Integration tests run against a **real deployed stack**. They are **automatically skipped** in CI when environment variables are not set.

**Required environment variables:**

| Variable | Description |
|---|---|
| `API_URL` | Base API Gateway URL (e.g. `https://<id>.execute-api.eu-central-1.amazonaws.com/prod`) |
| `COGNITO_USER_POOL_ID` | From `FeedbackUserPoolId` CfnOutput |
| `COGNITO_CLIENT_ID` | From `FeedbackUserPoolClientId` CfnOutput |
| `TEST_USER_EMAIL` | Email of a pre-created Cognito test user |
| `TEST_USER_PASSWORD` | Password of that test user |
| `AWS_DEFAULT_REGION` | AWS region (default: `eu-central-1`) |

**Setting variables locally (PowerShell):**
```powershell
$env:API_URL="https://<id>.execute-api.eu-central-1.amazonaws.com/prod"
$env:COGNITO_CLIENT_ID="<client-id>"
$env:TEST_USER_EMAIL="testuser@example.com"
$env:TEST_USER_PASSWORD="TestPass1!"
pytest app/tests/integration/ -v
```

---

## 14. Deployment

### Prerequisites
- Python 3.11+
- Node.js (for CDK CLI)
- AWS CLI configured with a named profile
- CDK CLI: `npm install -g aws-cdk`

### Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Bootstrap CDK (first time only)
```bash
cdk bootstrap --profile backend-test
```

### Deploy All Stacks
```bash
cdk deploy "FeedbackApp/**" --profile backend-test
```

### Diff (preview changes without deploying)
```bash
cdk diff "FeedbackApp/**" --profile backend-test
```

### Destroy All Stacks
```bash
cdk destroy "FeedbackApp/**" --profile backend-test
```

### Deploy Front-End (AWS Amplify Console)
The front-end is configured via `amplify.yml` at the project root. Connect the repository to Amplify Hosting in the AWS Console and set the build settings accordingly.

---

## 15. Environment Variables

### Lambda #1 — PostFeedbackFunction
| Variable | Set By | Description |
|---|---|---|
| `SNS_TOPIC_ARN` | CDK `LambdaStack` | ARN of FeedbackTopic |

### Lambda #2 — ProcessFeedbackFunction
| Variable | Set By | Default | Description |
|---|---|---|---|
| `TABLE_NAME` | CDK `LambdaStack` | — | DynamoDB table name |
| `BEDROCK_MODEL_ID` | CDK `LambdaStack` | `qwen.qwen3-32b-v1:0` | Primary model |
| `BEDROCK_FALLBACK_MODEL_ID` | CDK `LambdaStack` | `mistral.mistral-7b-instruct-v0:2` | Fallback model |
| `BEDROCK_INFERENCE_PROFILE_ID` | CDK `LambdaStack` | *(unset)* | Optional inference profile |

### Lambda #3 — GetRecommendationFunction
| Variable | Set By | Description |
|---|---|---|
| `TABLE_NAME` | CDK `LambdaStack` | DynamoDB table name |

---

## 16. CloudFormation Outputs

After deployment, the following outputs are available in the CloudFormation console and via `cdk deploy` terminal output:

| Output Key | Stack | Description |
|---|---|---|
| `FeedbackUserPoolId` | CognitoStack | Cognito User Pool ID |
| `FeedbackUserPoolClientId` | CognitoStack | App Client ID (for Amplify config) |
| `RecommendationsTableName` | DatabaseStack | DynamoDB table name |
| `RecommendationsTableArn` | DatabaseStack | DynamoDB table ARN |
| `FeedbackTopicArn` | MessagingStack | SNS Topic ARN |
| `FeedbackQueueUrl` | MessagingStack | SQS Queue URL |
| `ApiUrl` | ApiStack | Base URL for all API calls |

---

## 17. Error Handling & Observability

### Lambda Error Handling Strategy

| Lambda | On Error | Reason |
|---|---|---|
| Lambda #1 | Returns HTTP 4xx/5xx | Synchronous API path — must return a response |
| Lambda #2 | Re-raises exception | SQS retry mechanism requires exception propagation |
| Lambda #3 | Returns HTTP 4xx/5xx | Synchronous API path — must return a response |

### Observability
- **X-Ray tracing** enabled on all Lambda functions and API Gateway stage
- **CloudWatch Logs** retained for 1 week per function
- **Cold start config** logged at INFO level in Lambda #2
- **DLQ monitoring** — set a CloudWatch alarm on `FeedbackDLQ` `ApproximateNumberOfMessagesVisible`

---

## 18. Security

| Concern | Mitigation |
|---|---|
| API Authentication | All endpoints require valid Cognito JWT (Cognito Authorizer) |
| IAM Least Privilege | Lambda #1: SNS publish only; Lambda #2: DynamoDB R/W + scoped Bedrock; Lambda #3: DynamoDB read only |
| No wildcard IAM | All IAM policies scoped to specific resource ARNs |
| No hardcoded credentials | All resource identifiers passed via CDK environment variables |
| Data access isolation | Users can only read their own items (`user_id` = Cognito `sub`) |
| SPA token security | JWT not stored in `localStorage` — managed by Amplify session |
| Sensitive data logging | `data_trace_enabled=False` on API Gateway (prevents request body logging) |
| CORS | Configured with explicit allowed headers (`Authorization`, `Content-Type`) |
| DynamoDB | Point-in-Time Recovery enabled; TTL support for data expiry |
