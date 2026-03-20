# Implementation Analysis — Serverless Feedback & Recommendation App

> A living reference of **what is implemented**, **where it lives**, and **how all pieces connect**.

---

## Table of Contents

1. [High-Level Flow](#1-high-level-flow)
2. [Infrastructure Stacks](#2-infrastructure-stacks)
3. [Lambda Functions](#3-lambda-functions)
4. [Front-End](#4-front-end)
5. [Messaging Pipeline](#5-messaging-pipeline)
6. [Security & IAM](#6-security--iam)
7. [Tests](#7-tests)
8. [CI/CD Workflows](#8-cicd-workflows)
9. [Configuration & Environment Variables](#9-configuration--environment-variables)
10. [File Map](#10-file-map)

---

## 1. High-Level Flow

```
Browser (React / AWS Amplify)
  │
  │  1. User signs up / signs in
  │     → Cognito User Pool issues a JWT (ID token)
  │
  │  2. POST /feedback  (Authorization: Bearer <JWT>)
  │     → API Gateway validates JWT via Cognito Authorizer
  │     → Lambda #1 (PostFeedbackFunction)
  │        ├─ validates feedback_text
  │        ├─ extracts user_id from JWT sub claim
  │        ├─ generates feedback_id (UUID v4)
  │        ├─ publishes JSON to SNS FeedbackTopic
  │        └─ returns HTTP 202 { "feedback_id": "..." }
  │
  │  3. SNS → SQS → Lambda #2 (async, no user waiting)
  │     → Lambda #2 (ProcessFeedbackFunction)
  │        ├─ unwraps SNS-over-SQS envelope
  │        ├─ calls Amazon Bedrock (Converse API)
  │        │    primary:  qwen.qwen3-32b-v1:0
  │        │    fallback: mistral.mistral-7b-instruct-v0:2
  │        ├─ saves { user_id, feedback_id, feedback_text,
  │        │          recommendation, timestamp, ttl } to DynamoDB
  │        └─ on error: re-raises → SQS retries (max 3) → DLQ
  │
  └─  4. GET /recommendation?feedback_id=<id>  (Authorization: Bearer <JWT>)
        → API Gateway validates JWT via Cognito Authorizer
        → Lambda #3 (GetRecommendationFunction)
           ├─ extracts user_id from JWT sub claim
           ├─ if feedback_id param → DynamoDB GetItem → 200 / 404
           └─ if no param          → DynamoDB Query all for user → 200
```

---

## 2. Infrastructure Stacks

All stacks are bundled inside **`FeedbackAppStage`** and deployed with:
```bash
cdk deploy "FeedbackApp/**"
```

### Stack dependency order
```
FeedbackApp/Database
FeedbackApp/Messaging
FeedbackApp/Cognito   ← depends on Database (add_dependency)
FeedbackApp/Lambda    ← depends on Database + Messaging
FeedbackApp/Api       ← depends on Cognito + Lambda
```

---

### `DatabaseStack`
**File:** `app/stacks/database_stack.py`

| Resource | Detail |
|---|---|
| DynamoDB Table | Name: `Recommendations` |
| Partition key | `user_id` (String) — Cognito `sub` claim |
| Sort key | `feedback_id` (String) — UUID v4 |
| Billing | `PAY_PER_REQUEST` (on-demand) |
| PITR | Enabled (point-in-time recovery) |
| TTL | Attribute: `ttl` (Unix epoch — auto-expires old items) |
| Removal policy | `DESTROY` (dev/test) |

**Outputs:** `RecommendationsTableName`, `RecommendationsTableArn`

---

### `MessagingStack`
**File:** `app/stacks/messaging_stack.py`

| Resource | Detail |
|---|---|
| SNS Topic | `FeedbackTopic` — entry point for async pipeline |
| SQS Queue | `FeedbackQueue` — visibility timeout: 1800 s (30 min = 6× Lambda #2 timeout) |
| DLQ | `FeedbackDLQ` — triggered after 3 failed receive attempts, retention: 14 days |
| SNS→SQS | SQS subscribed to SNS; `raw_message_delivery=False` (SNS envelope kept for Lambda unwrapping) |

**Outputs:** `FeedbackTopicArn`, `FeedbackQueueUrl`, `FeedbackDLQUrl`, `FeedbackDLQArn`

---

### `CognitoStack`
**File:** `app/stacks/cognito_stack.py`

| Resource | Detail |
|---|---|
| User Pool | Email sign-up/in, auto-verify email, self sign-up enabled |
| Password policy | Min 8 chars, uppercase + digits required, symbols optional |
| Account recovery | Email only |
| App Client | `AmplifyAppClient` — no secret, `USER_PASSWORD_AUTH` + `USER_SRP_AUTH` flows |
| Identity Pool | `FeedbackIdentityPool` — issues temporary AWS credentials to authenticated users |
| Identity Pool IAM role | `IdentityPoolAuthenticatedRole` — **no DynamoDB permissions** (all DB access via API Gateway) |
| Removal policy | `DESTROY` (dev/test) |

> ⚠️ The Identity Pool exists and issues AWS credentials, but its IAM role has **no DynamoDB grants**. All database reads/writes go through API Gateway → Lambda.

**Outputs:** `FeedbackUserPoolId`, `FeedbackUserPoolClientId`, `FeedbackIdentityPoolId`

---

### `LambdaStack`
**File:** `app/stacks/lambda_stack.py`

| Function | Runtime | Timeout | Memory | Trigger |
|---|---|---|---|---|
| `PostFeedbackFunction` | Python 3.11 | 30 s | 256 MB | API Gateway POST /feedback |
| `ProcessFeedbackFunction` | Python 3.11 | 5 min | 512 MB | SQS Event Source (batch=1) |
| `GetRecommendationFunction` | Python 3.11 | 30 s | 256 MB | API Gateway GET /recommendation |

All functions have: **X-Ray tracing active**, **CloudWatch log retention 1 week**.

**IAM grants (least-privilege):**

| Function | Grant |
|---|---|
| `PostFeedbackFunction` | `sns:Publish` on `FeedbackTopic` only |
| `ProcessFeedbackFunction` | `dynamodb:GetItem/PutItem/Query/UpdateItem/DeleteItem` on `Recommendations` table |
| `ProcessFeedbackFunction` | `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` on Qwen3-32B, Mistral 7B, inference profiles |
| `GetRecommendationFunction` | `dynamodb:GetItem/Query` (read-only) on `Recommendations` table |

**Outputs:** `PostFeedbackFnArn`, `ProcessFeedbackFnArn`, `GetRecommendationFnArn`

---

### `ApiStack`
**File:** `app/stacks/api_stack.py`

| Resource | Detail |
|---|---|
| REST API | `FeedbackService`, stage: `prod` |
| Cognito Authorizer | `FeedbackCognitoAuthorizer` — validates JWT from `Authorization` header against User Pool |
| `POST /feedback` | → `PostFeedbackFunction`, requires valid JWT, returns 202/400/500 |
| `GET /recommendation` | → `GetRecommendationFunction`, requires valid JWT, optional `?feedback_id=` param, returns 200/404/500 |
| CORS | All origins, all methods, headers: `Authorization`, `Content-Type` |
| X-Ray | Tracing enabled on prod stage |

**Outputs:** `FeedbackApiUrl`, `PostFeedbackEndpoint`, `GetRecommendationEndpoint`

---

## 3. Lambda Functions

### Lambda #1 — `PostFeedbackFunction`
**File:** `app/lambda/post_feedback/handler.py`

```
Input:  API Gateway proxy event (POST /feedback)
Output: HTTP 202 { "feedback_id": "<uuid>" }
        HTTP 400 if feedback_text missing or empty
        HTTP 500 if Cognito sub claim absent

Steps:
  1. json.loads(event["body"])
  2. validate feedback_text (non-empty string)
  3. user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
  4. feedback_id = str(uuid.uuid4())
  5. sns_client.publish(TopicArn, Message=JSON payload)
  6. return 202
```

Environment variables: `SNS_TOPIC_ARN`

---

### Lambda #2 — `ProcessFeedbackFunction`
**File:** `app/lambda/process_feedback/handler.py`

```
Input:  SQS event (SNS envelope wrapping JSON payload)
Output: None (saves to DynamoDB); re-raises on error → SQS retry → DLQ

Steps:
  1. Unwrap: json.loads(record["body"]) → json.loads(sqs_body["Message"])
  2. Extract user_id, feedback_id, feedback_text
  3. Build career-coach prompt
  4. bedrock_client.converse(modelId, messages)
     - primary:  qwen.qwen3-32b-v1:0
     - fallback: mistral.mistral-7b-instruct-v0:2  (on ThrottlingException / ModelNotReadyException)
  5. table.put_item({ user_id, feedback_id, feedback_text,
                      recommendation, timestamp (ISO 8601), ttl (epoch+90d) })
```

Environment variables: `TABLE_NAME`, `BEDROCK_MODEL_ID`, `BEDROCK_FALLBACK_MODEL_ID`, `BEDROCK_INFERENCE_PROFILE_ID` (optional)

---

### Lambda #3 — `GetRecommendationFunction`
**File:** `app/lambda/get_recommendation/handler.py`

```
Input:  API Gateway proxy event (GET /recommendation)
Output: HTTP 200 { item }           — single item (when ?feedback_id= provided)
        HTTP 200 { "items": [...] } — all items for user
        HTTP 404 if item not found
        HTTP 500 on DynamoDB error

Steps:
  1. user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
  2. feedback_id = event["queryStringParameters"]["feedback_id"] (optional)
  3a. feedback_id present → table.get_item(Key={user_id, feedback_id})
  3b. no feedback_id      → table.query(KeyConditionExpression=Key("user_id").eq(user_id))
```

Environment variables: `TABLE_NAME`

---

## 4. Front-End

**Root:** `front-end/src/`

| File | Purpose |
|---|---|
| `index.js` | Amplify `configure(awsExports)` + React root render |
| `aws-exports.js` | Amplify config: `userPoolId`, `userPoolClientId`, `identityPoolId` (from env vars) |
| `App.js` | `<Authenticator>` wrapper, routing (`/submit`, `/recommendations`), sign-out |
| `lib/aws.js` | `authHeader()` helper (fetches Cognito ID token), `API_URL` constant |
| `pages/RecommendationsPage.js` | `GET /recommendation` → renders all recommendations, sorted newest-first |
| `components/FeedbackForm.js` | `POST /feedback` → polls `GET /recommendation?feedback_id=<id>` until result ready |
| `components/Recommendation.js` | Single recommendation card UI |

**Auth flow:** `<Authenticator loginMechanisms={['email']}>` — one email field on sign-up (no duplicate), no custom auth UI.

**API calls:** All requests include `Authorization: <Cognito ID token>` via `authHeader()`.  
**No direct DynamoDB calls from the browser** — all reads/writes go through API Gateway.

---

## 5. Messaging Pipeline

```
POST /feedback
    │
    ▼
Lambda #1
    │  sns.publish(TopicArn, Message=JSON)
    ▼
SNS FeedbackTopic
    │  SqsSubscription (raw_message_delivery=False → SNS envelope preserved)
    ▼
SQS FeedbackQueue
    │  visibility_timeout=1800s (30 min)
    │  SqsEventSource(batch_size=1)
    ▼
Lambda #2
    │  on success → item saved to DynamoDB
    │  on failure → re-raise → message returns to queue
    │              after 3 receive attempts → moved to DLQ
    ▼
SQS FeedbackDLQ  (retention: 14 days)
```

**Why 1800 s visibility timeout?**  
Lambda #2 can run up to 5 minutes (300 s). AWS recommends visibility timeout ≥ 6× function timeout → 6 × 300 = 1800 s. Without this, SQS would re-deliver the message while Lambda is still processing, exhausting the `max_receive_count=3` retries prematurely.

---

## 6. Security & IAM

| Boundary | Mechanism |
|---|---|
| User authentication | Cognito User Pool JWT (email + password) |
| API authorization | Cognito Authorizer on every API Gateway method — rejects requests without a valid JWT |
| user_id scoping | Lambda extracts `sub` claim from JWT — users can only read their own recommendations |
| Lambda #1 → SNS | `sns:Publish` scoped to `FeedbackTopic` ARN only |
| Lambda #2 → DynamoDB | `dynamodb:GetItem/PutItem/Query/UpdateItem/DeleteItem` scoped to `Recommendations` ARN only |
| Lambda #2 → Bedrock | `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` scoped to specific model ARNs |
| Lambda #3 → DynamoDB | Read-only (`dynamodb:GetItem/Query`) scoped to `Recommendations` ARN only |
| Identity Pool | Issues temporary AWS credentials but **authenticated role has NO DynamoDB permissions** |
| No wildcard `*` in IAM | All policies scoped to specific resource ARNs |
| No secrets in code | All ARNs/names passed via Lambda environment variables |

---

## 7. Tests

**Test runner:** `pytest`  
**Location:** `app/tests/`

### Unit tests — `app/tests/unit/`

| File | Covers | Mocking |
|---|---|---|
| `test_post_feedback.py` | Lambda #1: happy path (202), missing body, empty text, missing sub claim | `boto3` SNS client mocked |
| `test_process_feedback.py` | Lambda #2: happy path, SNS unwrap, Bedrock response parsing, DynamoDB save | `boto3` Bedrock + DynamoDB mocked |
| `test_get_recommendation.py` | Lambda #3: single item (200), all items (200), not found (404), missing sub | `boto3` DynamoDB mocked |
| `test_stacks.py` | CDK assertions: table exists, SNS/SQS config, Cognito pool, API Gateway, authorizer | `aws_cdk.assertions.Template` |

### Integration tests — `app/tests/integration/`

| File | Covers |
|---|---|
| `test_e2e.py` | Full end-to-end: sign in → POST /feedback → poll GET /recommendation → assert result |

> Integration tests are **skipped automatically** when `API_URL`, `COGNITO_CLIENT_ID`, `TEST_USER_EMAIL`, `TEST_USER_PASSWORD` are not set.

---

## 8. CI/CD Workflows

### Deploy — `.github/workflows/deploy.yml`
Triggers on every push to `main`.

| Step | Action |
|---|---|
| `test` | `pytest --cov` — blocks deploy on any failure |
| `cdk-diff` | `cdk synth` + `cdk diff "FeedbackApp/**"` — previews infrastructure changes |
| `deploy` | `cdk bootstrap` + `cdk deploy "FeedbackApp/**" --require-approval never` |

### Destroy — `.github/workflows/destroy.yml`
Manual trigger only (`workflow_dispatch`). Requires typing `destroy` as confirmation input.

Runs: `cdk destroy "FeedbackApp/**" --force`

### Required GitHub Secrets

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM access key |
| `AWS_SECRET_ACCESS_KEY` | IAM secret key |
| `AWS_REGION` | e.g. `eu-central-1` |
| `AWS_ACCOUNT_ID` | 12-digit account ID |

---

## 9. Configuration & Environment Variables

### Lambda environment variables (set by CDK `LambdaStack`)

| Variable | Lambda | Value source |
|---|---|---|
| `SNS_TOPIC_ARN` | #1 PostFeedback | `topic.topic_arn` |
| `TABLE_NAME` | #2 ProcessFeedback, #3 GetRecommendation | `table.table_name` |
| `BEDROCK_MODEL_ID` | #2 ProcessFeedback | Hardcoded: `qwen.qwen3-32b-v1:0` |
| `BEDROCK_FALLBACK_MODEL_ID` | #2 ProcessFeedback | Hardcoded: `mistral.mistral-7b-instruct-v0:2` |
| `BEDROCK_INFERENCE_PROFILE_ID` | #2 ProcessFeedback | Optional override (cross-region profile) |

### Front-end environment variables (Amplify Console / `.env.local`)

| Variable | Value source |
|---|---|
| `REACT_APP_USER_POOL_ID` | `FeedbackUserPoolId` CDK output |
| `REACT_APP_USER_POOL_CLIENT_ID` | `FeedbackUserPoolClientId` CDK output |
| `REACT_APP_IDENTITY_POOL_ID` | `FeedbackIdentityPoolId` CDK output |
| `REACT_APP_API_URL` | `FeedbackApiUrl` CDK output (no trailing slash) |
| `REACT_APP_AWS_REGION` | e.g. `eu-central-1` |

---

## 10. File Map

```
.
├── cdk.json                              # CDK app entry: "python app/app.py"
├── requirements.txt                      # aws-cdk-lib, boto3, pytest, moto, etc.
├── pytest.ini                            # testpaths = app/tests
├── amplify.yml                           # Amplify Console build spec
│
├── app/
│   ├── app.py                            # CDK entry — instantiates FeedbackAppStage
│   ├── stages/
│   │   └── feedback_stage.py             # Bundles all 5 stacks + wiring
│   ├── stacks/
│   │   ├── database_stack.py             # DynamoDB Recommendations table
│   │   ├── messaging_stack.py            # SNS + SQS FeedbackQueue + DLQ
│   │   ├── cognito_stack.py              # User Pool + App Client + Identity Pool
│   │   ├── lambda_stack.py               # 3 Lambdas + IAM grants + SQS event source
│   │   └── api_stack.py                  # REST API + Cognito Authorizer + routes
│   ├── lambda/
│   │   ├── post_feedback/
│   │   │   ├── handler.py                # Lambda #1: POST /feedback → SNS → 202
│   │   │   └── requirements.txt
│   │   ├── process_feedback/
│   │   │   ├── handler.py                # Lambda #2: SQS → Bedrock → DynamoDB
│   │   │   └── requirements.txt
│   │   └── get_recommendation/
│   │       ├── handler.py                # Lambda #3: GET /recommendation → DynamoDB
│   │       └── requirements.txt
│   └── tests/
│       ├── conftest.py                   # AWS_DEFAULT_REGION fixture
│       ├── unit/
│       │   ├── conftest.py               # Module isolation per test file
│       │   ├── test_post_feedback.py
│       │   ├── test_process_feedback.py
│       │   ├── test_get_recommendation.py
│       │   └── test_stacks.py            # CDK assertion tests
│       └── integration/
│           └── test_e2e.py               # End-to-end (skipped if env vars absent)
│
├── front-end/
│   └── src/
│       ├── index.js                      # Amplify.configure + React root
│       ├── aws-exports.js                # Amplify config (env vars)
│       ├── App.js                        # Authenticator + router + nav
│       ├── App.css                       # Global styles
│       ├── lib/
│       │   └── aws.js                    # authHeader() + API_URL
│       ├── components/
│       │   ├── FeedbackForm.js           # POST /feedback + polling
│       │   └── Recommendation.js        # Single recommendation card
│       └── pages/
│           └── RecommendationsPage.js   # GET /recommendation list view
│
└── .github/
    └── workflows/
        ├── deploy.yml                    # test → diff → deploy on push to main
        └── destroy.yml                   # manual teardown with confirmation
```
