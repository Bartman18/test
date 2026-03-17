# GitHub Copilot Instructions — Serverless Feedback & Recommendation App

## Project Context

This is a **serverless AWS application** built with **AWS CDK (Python)**. Users authenticate via Amazon Cognito, submit feedback text through a REST API, and receive AI-generated career improvement recommendations powered by **Amazon Bedrock**. The infrastructure is defined entirely in Python using CDK constructs.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Infrastructure (IaC) | AWS CDK v2, Python 3.11+ |
| Front-End | React (JavaScript), AWS Amplify |
| Authentication | Amazon Cognito User Pool |
| REST API | Amazon API Gateway (REST) |
| Compute | AWS Lambda (Python 3.11) |
| Messaging | Amazon SNS → Amazon SQS |
| Database | Amazon DynamoDB |
| AI Model | Amazon Bedrock (`bedrock-runtime`) |
| Testing | pytest, unittest.mock, moto |

---

## General Coding Guidelines

- **Language**: All CDK infrastructure and Lambda handler code must be written in **Python 3.11+**.
- **Style**: Follow PEP 8. Use type hints on all function signatures.
- **Imports**: Always import from `aws_cdk` (v2). Never use the old `aws_cdk.aws_*` top-level packages separately — use `from aws_cdk import aws_lambda, aws_sns, aws_sqs, aws_dynamodb, aws_apigateway, aws_cognito, aws_iam` etc.
- **No hardcoded ARNs or Account IDs**: Always reference constructs directly (e.g., `topic.topic_arn`) or use CDK environment tokens.
- **Environment variables**: Pass all resource identifiers (table name, SNS ARN, etc.) to Lambda via `environment` dict in the CDK `Function` construct.
- **Least-privilege IAM**: Grant only the specific permissions needed. Use `.grant_*` helper methods on constructs where available (e.g., `table.grant_read_data(fn)`, `topic.grant_publish(fn)`). Only fall back to `aws_iam.PolicyStatement` when no grant helper exists.
- **No inline Lambda code**: Lambda code always lives in `lambda/<function_name>/handler.py`. Reference it with `aws_lambda.Code.from_asset("lambda/<function_name>")`.

---

## CDK Stack Conventions

### Stack class pattern
```python
from aws_cdk import Stack
from constructs import Construct

class MyStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        # resources here
```

### Passing values between stacks
- Expose resources as **public properties** on the stack class (not CfnOutput strings).
- Pass stack instances as constructor parameters to dependent stacks.
- Use `CfnOutput` only for values needed outside CDK (e.g., API URL, Cognito client ID for Amplify config).

### Stack files and responsibilities

| File | Responsibility |
|---|---|
| `stacks/cognito_stack.py` | Cognito User Pool, App Client |
| `stacks/database_stack.py` | DynamoDB `Recommendations` table |
| `stacks/messaging_stack.py` | SNS Topic, SQS Queue, DLQ, SNS→SQS subscription |
| `stacks/lambda_stack.py` | All 3 Lambda functions, Event Source Mapping, IAM grants |
| `stacks/api_stack.py` | API Gateway REST API, Cognito Authorizer, routes, CORS, deployment |

---

## DynamoDB Conventions

- **Table name**: `Recommendations`
- **Partition key**: `user_id` (String) — always the Cognito `sub` claim
- **Sort key**: `feedback_id` (String) — UUID v4 generated at POST time
- **Additional attributes**: `feedback_text`, `recommendation`, `timestamp` (ISO 8601 string)
- **Billing mode**: `PAY_PER_REQUEST` (on-demand)
- Always enable **Point-in-Time Recovery** (`point_in_time_recovery=True`).

```python
from aws_cdk import aws_dynamodb as dynamodb, RemovalPolicy

table = dynamodb.Table(
    self, "RecommendationsTable",
    table_name="Recommendations",
    partition_key=dynamodb.Attribute(name="user_id", type=dynamodb.AttributeType.STRING),
    sort_key=dynamodb.Attribute(name="feedback_id", type=dynamodb.AttributeType.STRING),
    billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
    point_in_time_recovery=True,
    removal_policy=RemovalPolicy.DESTROY,  # dev/test only; use RETAIN in prod
)
```

---

## Lambda Conventions

- **Runtime**: `aws_lambda.Runtime.PYTHON_3_11`
- **Timeout**: Default 30s; Lambda #2 (Bedrock) set to **5 minutes** (`Duration.minutes(5)`)
- **Memory**: 256 MB default; Lambda #2 may use 512 MB
- **Tracing**: Enable **X-Ray** tracing (`tracing=aws_lambda.Tracing.ACTIVE`)
- **Log retention**: Set to 1 week in non-prod (`aws_logs.RetentionDays.ONE_WEEK`)

```python
from aws_cdk import aws_lambda, Duration

fn = aws_lambda.Function(
    self, "PostFeedbackFunction",
    runtime=aws_lambda.Runtime.PYTHON_3_11,
    handler="handler.lambda_handler",
    code=aws_lambda.Code.from_asset("lambda/post_feedback"),
    timeout=Duration.seconds(30),
    memory_size=256,
    tracing=aws_lambda.Tracing.ACTIVE,
    environment={
        "SNS_TOPIC_ARN": topic.topic_arn,
    },
)
```

### Lambda handler signature
All handlers must follow this signature:
```python
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: dict, context) -> dict:
    ...
```

### Extracting authenticated user_id in Lambda
```python
user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
```

### Standard response helper
```python
def build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
```

---

## Lambda #1 — PostFeedbackFunction

**File**: `lambda/post_feedback/handler.py`

Responsibilities:
1. Parse `feedback_text` from `event["body"]` (JSON)
2. Validate input — return `400` if missing
3. Extract `user_id` from Cognito authorizer claims
4. Generate a `feedback_id` using `uuid.uuid4()`
5. Publish message to SNS (`boto3` `sns.publish`)
6. Return **HTTP 202** with `{ "feedback_id": "..." }`

```python
import boto3, json, os, uuid

sns = boto3.client("sns")
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]

def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}")
    feedback_text = body.get("feedback_text")
    if not feedback_text:
        return build_response(400, {"error": "feedback_text is required"})

    user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
    feedback_id = str(uuid.uuid4())

    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=json.dumps({
            "user_id": user_id,
            "feedback_id": feedback_id,
            "feedback_text": feedback_text,
        }),
    )
    return build_response(202, {"feedback_id": feedback_id})
```

---

## Lambda #2 — ProcessFeedbackFunction

**File**: `lambda/process_feedback/handler.py`

Responsibilities:
1. Receive SQS event (message body is SNS notification JSON — unwrap it)
2. Parse `user_id`, `feedback_id`, `feedback_text`
3. Call Amazon Bedrock with a structured prompt
4. Parse the model response
5. Save `{ user_id, feedback_id, feedback_text, recommendation, timestamp }` to DynamoDB

### Unwrapping SNS-over-SQS message
```python
import json

def parse_sqs_sns_message(record: dict) -> dict:
    sqs_body = json.loads(record["body"])          # SNS envelope
    return json.loads(sqs_body["Message"])          # actual payload
```

### Amazon Bedrock invocation pattern
- Use `boto3.client("bedrock-runtime")`
- Model ID stored in environment variable `BEDROCK_MODEL_ID`
- Default model: `amazon.titan-text-express-v1` (can be overridden)
- Always wrap Bedrock call in try/except; on exception re-raise to let SQS retry

```python
import boto3, json, os

bedrock = boto3.client("bedrock-runtime")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.titan-text-express-v1")

def get_recommendation(feedback_text: str) -> str:
    prompt = (
        f"You are a professional career coach.\n"
        f"A person received the following feedback from their manager:\n\n"
        f"\"{feedback_text}\"\n\n"
        f"Please provide:\n"
        f"1. Key areas for improvement\n"
        f"2. Specific actionable steps\n"
        f"3. Relevant training or certifications to consider\n"
    )
    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {"maxTokenCount": 512, "temperature": 0.7},
    })
    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    return result["results"][0]["outputText"]
```

> **Note**: If using Anthropic Claude models instead, the request/response body format differs. Adjust accordingly and document the model ID in `BEDROCK_MODEL_ID`.

---

## Lambda #3 — GetRecommendationFunction

**File**: `lambda/get_recommendation/handler.py`

Responsibilities:
1. Extract `user_id` from Cognito authorizer claims
2. Optionally read `feedback_id` from query string parameters
3. If `feedback_id` provided: `GetItem`; otherwise: `Query` all items for `user_id`
4. Return **HTTP 200** with results, or **404** if none found

```python
import boto3, json, os
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ["TABLE_NAME"]

def lambda_handler(event, context):
    user_id = event["requestContext"]["authorizer"]["claims"]["sub"]
    params = event.get("queryStringParameters") or {}
    feedback_id = params.get("feedback_id")

    table = dynamodb.Table(TABLE_NAME)

    if feedback_id:
        resp = table.get_item(Key={"user_id": user_id, "feedback_id": feedback_id})
        item = resp.get("Item")
        if not item:
            return build_response(404, {"error": "Recommendation not found"})
        return build_response(200, item)
    else:
        resp = table.query(KeyConditionExpression=Key("user_id").eq(user_id))
        return build_response(200, {"items": resp.get("Items", [])})
```

---

## SNS & SQS Conventions

```python
from aws_cdk import aws_sns as sns, aws_sqs as sqs, aws_sns_subscriptions as subs, Duration

dlq = sqs.Queue(self, "FeedbackDLQ", retention_period=Duration.days(14))

queue = sqs.Queue(
    self, "FeedbackQueue",
    visibility_timeout=Duration.seconds(360),   # must be >= 6x Lambda timeout
    dead_letter_queue=sqs.DeadLetterQueue(queue=dlq, max_receive_count=3),
)

topic = sns.Topic(self, "FeedbackTopic")
topic.add_subscription(subs.SqsSubscription(queue))
```

### SQS Event Source Mapping for Lambda #2
```python
from aws_cdk import aws_lambda_event_sources as event_sources

process_fn.add_event_source(
    event_sources.SqsEventSource(queue, batch_size=1)
)
```

---

## API Gateway Conventions

- **Type**: REST API (not HTTP API) — required for Cognito Authorizer
- **Authorizer type**: `COGNITO_USER_POOLS`
- **Authorization scopes**: none required (token validation only)
- Enable **CORS** with `default_cors_preflight_options`

```python
from aws_cdk import aws_apigateway as apigw

api = apigw.RestApi(
    self, "FeedbackApi",
    rest_api_name="FeedbackService",
    default_cors_preflight_options=apigw.CorsOptions(
        allow_origins=apigw.Cors.ALL_ORIGINS,
        allow_methods=apigw.Cors.ALL_METHODS,
        allow_headers=["Authorization", "Content-Type"],
    ),
)

authorizer = apigw.CognitoUserPoolsAuthorizer(
    self, "CognitoAuthorizer",
    cognito_user_pools=[user_pool],
)

feedback_resource = api.root.add_resource("feedback")
feedback_resource.add_method(
    "POST",
    apigw.LambdaIntegration(post_feedback_fn),
    authorizer=authorizer,
    authorization_type=apigw.AuthorizationType.COGNITO,
)

recommendation_resource = api.root.add_resource("recommendation")
recommendation_resource.add_method(
    "GET",
    apigw.LambdaIntegration(get_recommendation_fn),
    authorizer=authorizer,
    authorization_type=apigw.AuthorizationType.COGNITO,
)
```

---

## Cognito Conventions

```python
from aws_cdk import aws_cognito as cognito

user_pool = cognito.UserPool(
    self, "FeedbackUserPool",
    self_sign_up_enabled=True,
    sign_in_aliases=cognito.SignInAliases(email=True),
    auto_verify=cognito.AutoVerifiedAttrs(email=True),
    password_policy=cognito.PasswordPolicy(
        min_length=8,
        require_uppercase=True,
        require_digits=True,
    ),
    removal_policy=RemovalPolicy.DESTROY,
)

app_client = user_pool.add_client(
    "AmplifyAppClient",
    auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
    prevent_user_existence_errors=True,
)
```

---

## Error Handling Rules

- Lambda functions must **never swallow exceptions silently** — always log and re-raise unless it is a user input validation error.
- Lambda #2 (SQS consumer): re-raise exceptions so SQS retries the message and eventually routes to DLQ.
- Lambda #1 and #3: return appropriate HTTP status codes (`400`, `404`, `500`) — never let unhandled exceptions propagate (they produce `502` from API Gateway).
- Always log `event` at DEBUG level (redact sensitive fields like `feedback_text` in production).

---

## Testing Guidelines

- Use `pytest` as the test runner.
- Use `unittest.mock.patch` to mock `boto3` clients inside Lambda handlers.
- For CDK stack tests, use `aws_cdk.assertions.Template.from_stack(stack)`.
- Test file naming: `tests/unit/test_<lambda_name>.py`.
- Every Lambda handler must have tests for: happy path, missing input (400), and not-found (404).

```python
# Example unit test pattern
from unittest.mock import patch, MagicMock
import json

@patch("post_feedback.handler.sns")
def test_post_feedback_returns_202(mock_sns):
    mock_sns.publish.return_value = {}
    event = {
        "body": json.dumps({"feedback_text": "You need to communicate better"}),
        "requestContext": {"authorizer": {"claims": {"sub": "user-123"}}},
    }
    from post_feedback.handler import lambda_handler
    response = lambda_handler(event, {})
    assert response["statusCode"] == 202
    assert "feedback_id" in json.loads(response["body"])
```

---

## Front-End (Amplify + React) Guidelines

- Use `@aws-amplify/ui-react` `<Authenticator />` component — do not build custom auth UI.
- Configure Amplify once in `src/index.js` using values from CDK `CfnOutput`.
- All API calls must include the JWT: use `fetchAuthSession()` from `aws-amplify/auth` to get the token and pass it as `Authorization` header.
- Handle `202` response from `POST /feedback` by showing a "Processing…" message and polling `GET /recommendation?feedback_id=<id>` until a result appears.

---

## What NOT to Do

- Do **not** put business logic inside CDK stack files — only infrastructure definitions.
- Do **not** hardcode AWS region or account ID.
- Do **not** use `*` in IAM policies — always scope to specific resource ARNs.
- Do **not** call Bedrock synchronously from Lambda #1 — the async SNS→SQS→Lambda #2 pattern is mandatory.
- Do **not** store JWT tokens in `localStorage` — use Amplify's built-in session management.
- Do **not** use `RemovalPolicy.RETAIN` for DynamoDB/Cognito in dev/test environments — use `DESTROY` to allow clean teardown.
