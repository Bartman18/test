#!/usr/bin/env python3
import aws_cdk as cdk

from stacks.cognito_stack import CognitoStack
from stacks.database_stack import DatabaseStack
from stacks.messaging_stack import MessagingStack
from stacks.lambda_stack import LambdaStack
from stacks.api_stack import ApiStack

app = cdk.App()

# ── 1. API Gateway — the public entry-point for all client requests ──────────
api_stack = ApiStack(app, "ApiStack")

# ── 2. Cognito — User Pool (API authorizer) + Identity Pool (direct DynamoDB reads)
cognito_stack = CognitoStack(app, "CognitoStack")

# ── 3. Remaining back-end infrastructure ────────────────────────────────────
database_stack = DatabaseStack(app, "DatabaseStack")

messaging_stack = MessagingStack(app, "MessagingStack")

lambda_stack = LambdaStack(
    app,
    "LambdaStack",
    table=database_stack.table,
    topic=messaging_stack.topic,
    queue=messaging_stack.queue,
)

# ── 4. Branch 1+2: Cognito authorizer + POST /feedback route → async pipeline
#       API Gateway → Authorizer → Cognito        (Branch 1 — auth)
#       API Gateway → Lambda #1 → SNS → SQS → Lambda #2 → Bedrock → DynamoDB
#                                              (Branch 2 — compute)
api_stack.configure(
    user_pool=cognito_stack.user_pool,
    post_feedback_fn=lambda_stack.post_feedback_fn,
)

# ── 5. Read path: grant Identity Pool authenticated role read-only DynamoDB access
#       Amplify reads recommendations directly from DynamoDB (no API Gateway)
cognito_stack.configure_grants(table=database_stack.table)

app.synth()
