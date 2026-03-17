import aws_cdk as cdk
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_dynamodb as dynamodb,
)
from constructs import Construct


class DatabaseStack(Stack):
    """
    Phase 3 — AWS CDK Agent
    Creates the DynamoDB Recommendations table.
    PK: user_id (Cognito sub), SK: feedback_id (UUID).
    Exposes table as a public property for the Lambda stack.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Recommendations Table ────────────────────────────────────────────
        self.table = dynamodb.Table(
            self,
            "RecommendationsTable",
            table_name="Recommendations",
            partition_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="feedback_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.DESTROY,  # dev/test only; use RETAIN in prod
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        CfnOutput(
            self,
            "RecommendationsTableName",
            value=self.table.table_name,
            description="DynamoDB table name for recommendations",
            export_name="RecommendationsTableName",
        )
        CfnOutput(
            self,
            "RecommendationsTableArn",
            value=self.table.table_arn,
            description="DynamoDB table ARN",
            export_name="RecommendationsTableArn",
        )
