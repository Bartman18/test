# Serverless Feedback & Recommendation App

A serverless AWS application where authenticated users submit manager feedback and receive **AI-generated career improvement recommendations** powered by Amazon Bedrock.

---

## Architecture

```
Browser → Cognito (Auth) → API Gateway → Lambda #1 → SNS → SQS → Lambda #2 → Bedrock
                                       ↘                                      ↓
                                        Lambda #3 ← GET ←─────── DynamoDB ←──┘
```

| Layer | Service |
|---|---|
| Auth | Amazon Cognito User Pool |
| REST API | Amazon API Gateway (REST) + Cognito Authorizer |
| Async ingestion | Lambda #1 → SNS Topic → SQS Queue |
| AI processing | Lambda #2 → Amazon Bedrock (`mistral.mistral-7b-instruct-v0:2`) |
| Storage | Amazon DynamoDB (`Recommendations` table) |
| Retrieval | Lambda #3 → DynamoDB |
| IaC | AWS CDK v2 (Python) |
| CI/CD | GitHub Actions |

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| AWS CDK CLI | latest | `npm install -g aws-cdk` |
| AWS CLI | v2 | [docs.aws.amazon.com](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) |
| AWS credentials | configured | `aws configure` |

---

## Local Setup

```bash
# 1. Clone the repository
git clone https://github.com/BartekIwanicki/Test.git
cd Test

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Install CDK CLI (requires Node.js)
npm install -g aws-cdk
```

---

## Running Tests

```bash
# Unit tests (no AWS account needed — all boto3 calls are mocked)
pytest -v

# Unit tests with coverage report
pytest --cov=lambda --cov-report=term-missing -v

# CDK stack assertion tests only
pytest tests/unit/test_stacks.py -v

# Integration tests (requires deployed stacks — see Integration Tests section)
pytest tests/integration/ -v
```

---

## Deployment

### 1. Enable Bedrock model access (one-time manual step)
> ⚠️ CDK **cannot** automate this. Without it, Lambda #2 will fail silently.

1. Go to **AWS Console → Amazon Bedrock → Model access**
2. Click **Manage model access**
3. Enable **Mistral 7B Instruct**
4. Save changes

### 2. Bootstrap CDK (first time per account/region only)

```bash
cdk bootstrap aws://<AWS_ACCOUNT_ID>/<AWS_REGION>
# Example:
cdk bootstrap aws://123456789012/eu-central-1
```

> If bootstrap fails with `UPDATE_ROLLBACK_FAILED`, delete the `CDKToolkit` stack
> in CloudFormation console and re-run.

### 3. Synthesise (validate)

```bash
cdk synth
```

### 4. Deploy all stacks

```bash
cdk deploy --all --require-approval never
```

Stacks are deployed in dependency order:
`CognitoStack → DatabaseStack → MessagingStack → LambdaStack → ApiStack`

### 5. Note the CloudFormation outputs

After a successful deploy, copy these values:

| Output | Description | Used for |
|---|---|---|
| `FeedbackApiUrl` | API Gateway base URL | Front-end `Amplify.configure()` |
| `FeedbackUserPoolId` | Cognito User Pool ID | Front-end auth config |
| `FeedbackUserPoolClientId` | Cognito App Client ID | Front-end auth config |

---

## CI/CD (GitHub Actions)

### Deploy workflow
Triggers automatically on every push to `main`:
1. **test** — runs `pytest --cov` (blocks deploy on failure)
2. **cdk-diff** — runs `cdk synth` + `cdk diff --all` (preview changes)
3. **deploy** — bootstraps CDK, deploys each stack in order

### Destroy workflow
Triggered manually via **Actions → Destroy Infrastructure → Run workflow**.
Requires typing `destroy` as a confirmation to prevent accidents.

### Required GitHub Secrets

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM user/role access key |
| `AWS_SECRET_ACCESS_KEY` | IAM user/role secret key |
| `AWS_REGION` | e.g. `eu-central-1` |
| `AWS_ACCOUNT_ID` | 12-digit AWS account ID |

---

## Integration Tests

Set the following environment variables then run `pytest tests/integration/ -v`:

```bash
export API_URL="https://<id>.execute-api.eu-central-1.amazonaws.com/prod"
export COGNITO_CLIENT_ID="<FeedbackUserPoolClientId>"
export TEST_USER_EMAIL="testuser@example.com"
export TEST_USER_PASSWORD="TestPass123!"
```

Tests are **automatically skipped** when these variables are not set, so they never block the CI unit-test job.

---

## Project Structure

```
.
├── app.py                           # CDK App entry point — wires all stacks
├── cdk.json                         # CDK configuration
├── requirements.txt                 # Python dependencies
│
├── stacks/
│   ├── cognito_stack.py             # Cognito User Pool + App Client
│   ├── database_stack.py            # DynamoDB Recommendations table + TTL
│   ├── messaging_stack.py           # SNS Topic + SQS Queue + DLQ
│   ├── lambda_stack.py              # 3 Lambda functions + IAM + event source
│   └── api_stack.py                 # API Gateway + Cognito Authorizer + CORS
│
├── lambda/
│   ├── post_feedback/handler.py     # POST /feedback → validate → SNS → 202
│   ├── process_feedback/handler.py  # SQS → Bedrock → DynamoDB
│   └── get_recommendation/handler.py# GET /recommendation → DynamoDB → 200/404
│
├── tests/
│   ├── conftest.py                  # Sets AWS_DEFAULT_REGION before any import
│   ├── unit/
│   │   ├── conftest.py              # Isolates handler module per test file
│   │   ├── test_post_feedback.py    # 6 unit tests
│   │   ├── test_process_feedback.py # 4 unit tests
│   │   ├── test_get_recommendation.py # 7 unit tests
│   │   └── test_stacks.py           # CDK stack assertion tests
│   └── integration/
│       └── test_e2e.py              # End-to-end tests (requires deployed env)
│
└── .github/
    └── workflows/
        ├── deploy.yml               # CI/CD: test → diff → deploy on push to main
        └── destroy.yml              # Teardown: manual, requires "destroy" confirmation
```

---

## DynamoDB Schema

**Table name**: `Recommendations`

| Attribute | Key | Type | Description |
|---|---|---|---|
| `user_id` | Partition key | String | Cognito `sub` claim |
| `feedback_id` | Sort key | String | UUID v4 generated at POST time |
| `feedback_text` | — | String | Original feedback submitted |
| `recommendation` | — | String | AI-generated recommendation from Bedrock |
| `timestamp` | — | String | ISO 8601 UTC timestamp |
| `ttl` | — | Number | Unix epoch seconds for DynamoDB TTL auto-expiry |

---

## Teardown

```bash
# Destroy all stacks (reverse dependency order)
cdk destroy ApiStack LambdaStack MessagingStack DatabaseStack CognitoStack --force
# Or destroy all at once:
cdk destroy --all --force
```