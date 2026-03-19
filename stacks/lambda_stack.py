import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_lambda,
    aws_logs,
    aws_iam as iam,
    aws_lambda_event_sources as event_sources,
    aws_dynamodb as dynamodb,
    aws_sns as sns,
    aws_sqs as sqs,
)
from constructs import Construct


class LambdaStack(Stack):
    """
    Phase 5 — AWS CDK Agent (infra) + Python Lambda Agent (handler code)
    Defines all 3 Lambda functions with runtime, IAM grants, and event sources.
    Handler code lives in lambda/<function_name>/handler.py.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        table: dynamodb.Table,
        topic: sns.Topic,
        queue: sqs.Queue,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Common Lambda config ─────────────────────────────────────────────
        common_props = dict(
            runtime=aws_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            tracing=aws_lambda.Tracing.ACTIVE,
            log_retention=aws_logs.RetentionDays.ONE_WEEK,
        )

        # ── Lambda #1 — PostFeedbackFunction ─────────────────────────────────
        self.post_feedback_fn = aws_lambda.Function(
            self,
            "PostFeedbackFunction",
            **common_props,
            code=aws_lambda.Code.from_asset("lambda/post_feedback"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "SNS_TOPIC_ARN": topic.topic_arn,
            },
            description="Receives POST /feedback, validates input, publishes to SNS, returns 202.",
        )
        # Least-privilege: only publish to this specific topic
        topic.grant_publish(self.post_feedback_fn)

        # ── Lambda #2 — ProcessFeedbackFunction ──────────────────────────────
        self.process_feedback_fn = aws_lambda.Function(
            self,
            "ProcessFeedbackFunction",
            **common_props,
            code=aws_lambda.Code.from_asset("lambda/process_feedback"),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "TABLE_NAME": table.table_name,
                "BEDROCK_MODEL_ID": "amazon.nova-micro-v1:0",
            },
            description="Consumes SQS, calls Bedrock, saves recommendation to DynamoDB.",
        )
        # Read + write on the Recommendations table
        table.grant_read_write_data(self.process_feedback_fn)

        # Bedrock InvokeModel — Amazon Nova Micro is natively available in eu-central-1,
        # no cross-region inference profile needed.
        self.process_feedback_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-micro-v1:0"
                ],
            )
        )

        # SQS Event Source Mapping — batch_size=1 ensures one feedback per invocation
        self.process_feedback_fn.add_event_source(
            event_sources.SqsEventSource(queue, batch_size=1)
        )

        # ── Lambda #3 — GetRecommendationFunction ────────────────────────────
        self.get_recommendation_fn = aws_lambda.Function(
            self,
            "GetRecommendationFunction",
            **common_props,
            code=aws_lambda.Code.from_asset("lambda/get_recommendation"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "TABLE_NAME": table.table_name,
            },
            description="Handles GET /recommendation — queries DynamoDB for user's recommendations.",
        )
        # Read-only access to the Recommendations table
        table.grant_read_data(self.get_recommendation_fn)

        # ── Outputs ──────────────────────────────────────────────────────────
        CfnOutput(self, "PostFeedbackFnArn", value=self.post_feedback_fn.function_arn)
        CfnOutput(self, "ProcessFeedbackFnArn", value=self.process_feedback_fn.function_arn)
        CfnOutput(self, "GetRecommendationFnArn", value=self.get_recommendation_fn.function_arn)
