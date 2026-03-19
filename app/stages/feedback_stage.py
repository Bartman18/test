"""
FeedbackAppStage — single deployable unit for the entire backend.

A CDK Stage bundles multiple stacks into one logical application.
All cross-stack wiring (API routes, IAM grants, event sources) is
declared here so callers only need to instantiate this one class.

Deploy everything at once (from project root):
    cdk deploy "FeedbackApp/**" --profile backend-test

Individual stacks inside the stage:
    FeedbackApp/Database   — DynamoDB Recommendations table
    FeedbackApp/Messaging  — SNS topic, SQS queue, DLQ
    FeedbackApp/Cognito    — User Pool, App Client, Identity Pool
    FeedbackApp/Lambda     — 3 Lambda functions + IAM grants + SQS event source
    FeedbackApp/Api        — API Gateway REST API + Cognito authorizer + routes
"""
import aws_cdk as cdk
from constructs import Construct

from stacks.database_stack import DatabaseStack
from stacks.messaging_stack import MessagingStack
from stacks.cognito_stack import CognitoStack
from stacks.lambda_stack import LambdaStack
from stacks.api_stack import ApiStack


class FeedbackAppStage(cdk.Stage):
    """Bundles all backend stacks into one deployable application stage."""

    def __init__(self, scope: Construct, stage_id: str, **kwargs) -> None:
        super().__init__(scope, stage_id, **kwargs)

        # ── Stateful infrastructure (no upstream dependencies) ───────────────
        database = DatabaseStack(self, "Database")
        messaging = MessagingStack(self, "Messaging")

        # ── Cognito ──────────────────────────────────────────────────────────
        # Created before Lambda/API so the User Pool exists when the authorizer
        # and Identity Pool DynamoDB grant are wired in.
        cognito = CognitoStack(self, "Cognito")

        # ── Compute layer ────────────────────────────────────────────────────
        lambdas = LambdaStack(
            self,
            "Lambda",
            table=database.table,
            topic=messaging.topic,
            queue=messaging.queue,
        )

        # ── API Gateway ──────────────────────────────────────────────────────
        api = ApiStack(self, "Api")
        api.configure(
            user_pool=cognito.user_pool,
            post_feedback_fn=lambdas.post_feedback_fn,
            get_recommendation_fn=lambdas.get_recommendation_fn,
        )

        # ── Identity Pool → DynamoDB read grant ──────────────────────────────
        cognito.configure_grants(table=database.table)

        # ── Explicit deployment order ─────────────────────────────────────────
        # CDK infers most ordering from cross-stack refs but declaring it
        # explicitly makes the intent clear and prevents accidental reordering.
        cognito.add_dependency(database)
        lambdas.add_dependency(database)
        lambdas.add_dependency(messaging)
        api.add_dependency(cognito)
        api.add_dependency(lambdas)
