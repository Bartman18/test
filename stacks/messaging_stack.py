import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    aws_sns as sns,
    aws_sqs as sqs,
    aws_sns_subscriptions as subs,
)
from constructs import Construct


class MessagingStack(Stack):
    """
    Phase 4 — AWS CDK Agent
    Creates the SNS Topic, SQS Queue, and Dead Letter Queue (DLQ).
    Subscribes SQS to SNS for the async feedback processing fan-out pattern.
    Exposes topic and queue as public properties for the Lambda stack.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Dead Letter Queue (DLQ) ──────────────────────────────────────────
        self.dlq = sqs.Queue(
            self,
            "FeedbackDLQ",
            queue_name="FeedbackDLQ",
            retention_period=Duration.days(14),
        )

        # ── Main Feedback Queue ──────────────────────────────────────────────
        # visibility_timeout must be >= 6x the Lambda #2 timeout (5 min → 360s min)
        self.queue = sqs.Queue(
            self,
            "FeedbackQueue",
            queue_name="FeedbackQueue",
            visibility_timeout=Duration.seconds(360),
            dead_letter_queue=sqs.DeadLetterQueue(
                queue=self.dlq,
                max_receive_count=3,
            ),
        )

        # ── SNS Topic ────────────────────────────────────────────────────────
        self.topic = sns.Topic(
            self,
            "FeedbackTopic",
            topic_name="FeedbackTopic",
            display_name="Feedback Processing Topic",
        )

        # ── Subscribe SQS to SNS ─────────────────────────────────────────────
        self.topic.add_subscription(
            subs.SqsSubscription(
                self.queue,
                raw_message_delivery=False,  # keep SNS envelope for Lambda unwrapping
            )
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        CfnOutput(
            self,
            "FeedbackTopicArn",
            value=self.topic.topic_arn,
            description="SNS Topic ARN for feedback submission",
            export_name="FeedbackTopicArn",
        )
        CfnOutput(
            self,
            "FeedbackQueueUrl",
            value=self.queue.queue_url,
            description="SQS Queue URL for feedback processing",
            export_name="FeedbackQueueUrl",
        )
        CfnOutput(
            self,
            "FeedbackDLQUrl",
            value=self.dlq.queue_url,
            description="Dead Letter Queue URL",
            export_name="FeedbackDLQUrl",
        )
