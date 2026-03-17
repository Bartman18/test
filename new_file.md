# Agents for Implementation

## Phase-by-Phase Agent Assignments

### Phase 1 — CDK Project Bootstrap
- **Agent**: AWS CDK Agent
  - Responsible for initializing the CDK project, setting up the virtual environment, and configuring the project structure.

### Phase 2 — Cognito Stack
- **Agent**: AWS CDK Agent
  - Creates the Cognito User Pool and App Client.
  - Configures email sign-up/sign-in and self-service sign-up.

### Phase 3 — DynamoDB Stack
- **Agent**: AWS CDK Agent
  - Creates the DynamoDB `Recommendations` table with the specified schema.

### Phase 4 — Messaging Stack
- **Agent**: AWS CDK Agent
  - Sets up the SNS Topic, SQS Queue, and Dead Letter Queue (DLQ).
  - Configures the subscription between SNS and SQS.

### Phase 5 — Lambda Stack
> ⚠️ **Dual-agent phase** — CDK infra and handler code are separate responsibilities.

- **Agent 1**: AWS CDK Agent → `stacks/lambda_stack.py`
  - Defines all 3 Lambda `Function` constructs with runtime, memory, timeout, X-Ray tracing.
  - Attaches SQS Event Source Mapping to `ProcessFeedbackFunction`.
  - Grants least-privilege IAM: `topic.grant_publish()`, `table.grant_read_write_data()`, `bedrock:InvokeModel` via PolicyStatement.
  - Passes environment variables (`SNS_TOPIC_ARN`, `TABLE_NAME`, `BEDROCK_MODEL_ID`) to each function.

- **Agent 2**: Python Lambda Agent → `lambda/*/handler.py`
  - **`PostFeedbackFunction`** (`lambda/post_feedback/handler.py`):
    Validates input, extracts `user_id` from Cognito claims, generates UUID, publishes to SNS, returns HTTP 202.
  - **`ProcessFeedbackFunction`** (`lambda/process_feedback/handler.py`):
    Unwraps SNS-over-SQS envelope, calls Amazon Bedrock (`bedrock-runtime`), saves recommendation to DynamoDB.
    ↳ **Bedrock sub-task** (previously Phase 8 — merged here): constructs career-coach prompt, parses model response, re-raises on error for SQS retry.
  - **`GetRecommendationFunction`** (`lambda/get_recommendation/handler.py`):
    Queries DynamoDB by `user_id` (+ optional `feedback_id`), returns HTTP 200/404.

### Phase 6 — API Gateway Stack
- **Agent**: AWS CDK Agent → `stacks/api_stack.py`
  - Creates the REST API in API Gateway.
  - Configures the Cognito User Pool Authorizer.
  - Defines resources and methods for `/feedback` (POST) and `/recommendation` (GET).
  - Enables CORS and deploys to `prod` stage.

### Phase 7 — Front-End (Amplify + React)
- **Agent**: React Front-End Agent → `front-end/`
  - Initializes the React app and configures Amplify with CDK outputs.
  - Builds `<Authenticator />`, `FeedbackForm`, and `Recommendation` components.
  - Implements 202 polling: POST → receive `feedback_id` → poll GET until recommendation appears.
  - Deploys the front-end via Amplify Console (connect to Git repo).

### Phase 9 — Testing
- **Agent**: Testing Agent → `tests/unit/`
  - Writes unit tests for all Lambda handlers using `pytest` and `unittest.mock`.
  - Tests: happy path, missing input (400), not-found (404), Bedrock error → re-raise.
  - Creates CDK snapshot/assertion tests for each stack using `aws_cdk.assertions.Template`.

### Phase 10 — Deployment
- **Agent**: Deployment Agent → CI/CD pipeline
  - Runs `cdk bootstrap` (once), `cdk synth`, `cdk deploy --all`.
  - Configures Amplify front-end with CDK `CfnOutput` values.
  - Runs integration tests post-deploy.
  - DevOps: integrates with GitHub Actions or AWS CodePipeline for automated CD.