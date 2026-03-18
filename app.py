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

# ── 2. Cognito — user pool that backs the API Gateway authorizer ─────────────
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

# ── 4. Connect Cognito authorizer + Lambda routes to the API Gateway ─────────
api_stack.configure(
    user_pool=cognito_stack.user_pool,
    post_feedback_fn=lambda_stack.post_feedback_fn,
    get_recommendation_fn=lambda_stack.get_recommendation_fn,
)

app.synth()
