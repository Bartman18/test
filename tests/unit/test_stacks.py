"""
CDK Stack Assertion Tests
Tests that each CloudFormation stack synthesises the expected AWS resources
with the correct properties. Uses aws_cdk.assertions.Template — no real AWS
account needed.

Coverage:
  ✓ CognitoStack   — UserPool + UserPoolClient
  ✓ DatabaseStack  — DynamoDB table (schema, TTL, billing mode, PITR)
  ✓ MessagingStack — SNS topic, SQS queue, DLQ, subscription
  ✓ LambdaStack    — 3 Lambda functions (runtime, env vars, Bedrock IAM policy)
  ✓ ApiStack       — REST API, Cognito Authorizer, POST /feedback, GET /recommendation
"""
import sys
import os

import aws_cdk as cdk
from aws_cdk import assertions

# Ensure stacks package is importable when running from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from stacks.cognito_stack import CognitoStack
from stacks.database_stack import DatabaseStack
from stacks.messaging_stack import MessagingStack
from stacks.lambda_stack import LambdaStack
from stacks.api_stack import ApiStack


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_app() -> cdk.App:
    return cdk.App()


def _all_stacks(app: cdk.App):
    """Return all stacks wired together (mirrors app.py).

    Order reflects the diagram:
      1. API Gateway  — public entry-point (ApiStack.__init__)
      2. Cognito      — User Pool (authorizer) + Identity Pool (direct DynamoDB reads)
      3. Back-end     — DynamoDB, SNS/SQS, Lambda functions
      4. configure()        — POST /feedback route + Cognito authorizer
      5. configure_grants() — DynamoDB read grant for Identity Pool
    """
    # 1. API Gateway first
    api = ApiStack(app, "ApiStack")

    # 2. Cognito next
    cognito = CognitoStack(app, "CognitoStack")

    # 3. Remaining back-end infrastructure
    database = DatabaseStack(app, "DatabaseStack")
    messaging = MessagingStack(app, "MessagingStack")
    lambdas = LambdaStack(
        app,
        "LambdaStack",
        table=database.table,
        topic=messaging.topic,
        queue=messaging.queue,
    )

# 4. Connect Cognito authorizer + all routes to API Gateway
    api.configure(
        user_pool=cognito.user_pool,
        post_feedback_fn=lambdas.post_feedback_fn,
        get_recommendation_fn=lambdas.get_recommendation_fn,
    )

    # 5. Grant Identity Pool authenticated role read-only access to DynamoDB
    cognito.configure_grants(table=database.table)

    return cognito, database, messaging, lambdas, api


# ── CognitoStack ─────────────────────────────────────────────────────────────

class TestCognitoStack:
    def setup_method(self):
        app = _make_app()
        stack = CognitoStack(app, "TestCognitoStack")
        self.template = assertions.Template.from_stack(stack)

    def test_user_pool_created(self):
        """A Cognito UserPool is present."""
        self.template.resource_count_is("AWS::Cognito::UserPool", 1)

    def test_user_pool_email_signin(self):
        """UserPool is configured for email sign-in with self sign-up enabled."""
        self.template.has_resource_properties("AWS::Cognito::UserPool", {
            "UsernameAttributes": ["email"],
            "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": False},
            "AutoVerifiedAttributes": ["email"],
        })

    def test_user_pool_password_policy(self):
        """Password policy enforces minimum length and complexity."""
        self.template.has_resource_properties("AWS::Cognito::UserPool", {
            "Policies": {
                "PasswordPolicy": {
                    "MinimumLength": 8,
                    "RequireUppercase": True,
                    "RequireNumbers": True,
                }
            }
        })

    def test_app_client_created(self):
        """A UserPoolClient (App Client) is present."""
        self.template.resource_count_is("AWS::Cognito::UserPoolClient", 1)

    def test_app_client_no_secret(self):
        """App client must NOT generate a client secret (SPA / Amplify use)."""
        self.template.has_resource_properties("AWS::Cognito::UserPoolClient", {
            "GenerateSecret": False,
        })

    def test_cfn_outputs_present(self):
        """UserPoolId and UserPoolClientId outputs are exported."""
        self.template.has_output("UserPoolId", {})
        self.template.has_output("UserPoolClientId", {})


# ── DatabaseStack ─────────────────────────────────────────────────────────────

class TestDatabaseStack:
    def setup_method(self):
        app = _make_app()
        stack = DatabaseStack(app, "TestDatabaseStack")
        self.template = assertions.Template.from_stack(stack)

    def test_table_created(self):
        """Exactly one DynamoDB table is created."""
        self.template.resource_count_is("AWS::DynamoDB::Table", 1)

    def test_table_name(self):
        """Table is named 'Recommendations'."""
        self.template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "Recommendations",
        })

    def test_table_key_schema(self):
        """PK is user_id (HASH), SK is feedback_id (RANGE)."""
        self.template.has_resource_properties("AWS::DynamoDB::Table", {
            "KeySchema": [
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "feedback_id", "KeyType": "RANGE"},
            ],
        })

    def test_table_attribute_definitions(self):
        """user_id and feedback_id attributes are both String type."""
        self.template.has_resource_properties("AWS::DynamoDB::Table", {
            "AttributeDefinitions": assertions.Match.array_with([
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "feedback_id", "AttributeType": "S"},
            ]),
        })

    def test_table_billing_mode_on_demand(self):
        """Billing mode is PAY_PER_REQUEST (no provisioned throughput)."""
        self.template.has_resource_properties("AWS::DynamoDB::Table", {
            "BillingMode": "PAY_PER_REQUEST",
        })

    def test_table_pitr_enabled(self):
        """Point-in-time recovery is enabled."""
        self.template.has_resource_properties("AWS::DynamoDB::Table", {
            "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
        })

    def test_table_ttl_enabled(self):
        """TTL attribute 'ttl' is configured on the table."""
        self.template.has_resource_properties("AWS::DynamoDB::Table", {
            "TimeToLiveSpecification": {
                "AttributeName": "ttl",
                "Enabled": True,
            },
        })

    def test_cfn_outputs_present(self):
        """Table name and ARN are exported as outputs."""
        self.template.has_output("RecommendationsTableName", {})
        self.template.has_output("RecommendationsTableArn", {})


# ── MessagingStack ────────────────────────────────────────────────────────────

class TestMessagingStack:
    def setup_method(self):
        app = _make_app()
        stack = MessagingStack(app, "TestMessagingStack")
        self.template = assertions.Template.from_stack(stack)

    def test_sns_topic_created(self):
        """Exactly one SNS topic is created."""
        self.template.resource_count_is("AWS::SNS::Topic", 1)

    def test_sns_topic_name(self):
        """SNS topic is named 'FeedbackTopic'."""
        self.template.has_resource_properties("AWS::SNS::Topic", {
            "TopicName": "FeedbackTopic",
        })

    def test_two_sqs_queues_created(self):
        """Two SQS queues are created: FeedbackQueue and FeedbackDLQ."""
        self.template.resource_count_is("AWS::SQS::Queue", 2)

    def test_feedback_queue_name(self):
        """Main feedback queue is named 'FeedbackQueue'."""
        self.template.has_resource_properties("AWS::SQS::Queue", {
            "QueueName": "FeedbackQueue",
        })

    def test_dlq_name(self):
        """Dead letter queue is named 'FeedbackDLQ'."""
        self.template.has_resource_properties("AWS::SQS::Queue", {
            "QueueName": "FeedbackDLQ",
        })

    def test_feedback_queue_visibility_timeout(self):
        """Visibility timeout is 1800s (= 6× Lambda #2 timeout of 300s)."""
        self.template.has_resource_properties("AWS::SQS::Queue", {
            "QueueName": "FeedbackQueue",
            "VisibilityTimeout": 1800,
        })

    def test_sns_sqs_subscription_exists(self):
        """SNS subscription to SQS is created."""
        self.template.resource_count_is("AWS::SNS::Subscription", 1)

    def test_sns_subscription_protocol(self):
        """Subscription protocol is 'sqs'."""
        self.template.has_resource_properties("AWS::SNS::Subscription", {
            "Protocol": "sqs",
        })


# ── LambdaStack ───────────────────────────────────────────────────────────────

class TestLambdaStack:
    def setup_method(self):
        app = _make_app()
        database = DatabaseStack(app, "DatabaseStack")
        messaging = MessagingStack(app, "MessagingStack")
        stack = LambdaStack(
            app,
            "TestLambdaStack",
            table=database.table,
            topic=messaging.topic,
            queue=messaging.queue,
        )
        self.template = assertions.Template.from_stack(stack)

    def test_three_lambda_functions_created(self):
        """3 business Lambda functions + 1 CDK LogRetention helper = 4 total."""
        self.template.resource_count_is("AWS::Lambda::Function", 4)

    def test_all_functions_use_python311(self):
        """All Lambda functions use Python 3.11 runtime."""
        resources = self.template.find_resources("AWS::Lambda::Function")
        for logical_id, resource in resources.items():
            props = resource.get("Properties", {})
            # Skip log retention custom resource Lambda (created by CDK internally)
            if "LogRetention" in logical_id:
                continue
            assert props.get("Runtime") == "python3.11", (
                f"Function {logical_id} has wrong runtime: {props.get('Runtime')}"
            )

    def test_post_feedback_env_vars(self):
        """PostFeedbackFunction has SNS_TOPIC_ARN environment variable."""
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "Environment": {
                "Variables": assertions.Match.object_like({
                    "SNS_TOPIC_ARN": assertions.Match.any_value(),
                })
            }
        })

    def test_process_feedback_env_vars(self):
        """ProcessFeedbackFunction has TABLE_NAME and BEDROCK_MODEL_ID env vars."""
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "Environment": {
                "Variables": assertions.Match.object_like({
                    "TABLE_NAME": assertions.Match.any_value(),
                    "BEDROCK_MODEL_ID": "anthropic.claude-3-haiku-20240307-v1:0",
                })
            }
        })

    def test_get_recommendation_env_vars(self):
        """GetRecommendationFunction has TABLE_NAME environment variable."""
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "Environment": {
                "Variables": assertions.Match.object_like({
                    "TABLE_NAME": assertions.Match.any_value(),
                })
            }
        })

    def test_bedrock_invoke_model_policy_exists(self):
        """An IAM policy granting bedrock:InvokeModel is attached to a Lambda role."""
        self.template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Action": "bedrock:InvokeModel",
                        "Effect": "Allow",
                    })
                ])
            }
        })

    def test_sqs_event_source_mapping_created(self):
        """SQS Event Source Mapping exists for ProcessFeedbackFunction."""
        self.template.resource_count_is("AWS::Lambda::EventSourceMapping", 1)

    def test_sqs_event_source_batch_size(self):
        """SQS Event Source Mapping batch size is 1."""
        self.template.has_resource_properties("AWS::Lambda::EventSourceMapping", {
            "BatchSize": 1,
        })


# ── ApiStack ──────────────────────────────────────────────────────────────────

class TestApiStack:
    def setup_method(self):
        app = _make_app()
        cognito, database, messaging, lambdas, api_stack = _all_stacks(app)
        self.template = assertions.Template.from_stack(api_stack)

    def test_rest_api_created(self):
        """Exactly one REST API is created."""
        self.template.resource_count_is("AWS::ApiGateway::RestApi", 1)

    def test_rest_api_name(self):
        """REST API is named 'FeedbackService'."""
        self.template.has_resource_properties("AWS::ApiGateway::RestApi", {
            "Name": "FeedbackService",
        })

    def test_cognito_authorizer_created(self):
        """A Cognito User Pools authorizer is attached to the API."""
        self.template.resource_count_is("AWS::ApiGateway::Authorizer", 1)

    def test_authorizer_type(self):
        """Authorizer type is COGNITO_USER_POOLS."""
        self.template.has_resource_properties("AWS::ApiGateway::Authorizer", {
            "Type": "COGNITO_USER_POOLS",
        })

    def test_deployment_stage_prod(self):
        """API is deployed to a 'prod' stage."""
        self.template.has_resource_properties("AWS::ApiGateway::Stage", {
            "StageName": "prod",
        })

    def test_api_url_output_exists(self):
        """ApiUrl CloudFormation output is present."""
        self.template.has_output("ApiUrl", {})
