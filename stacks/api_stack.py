import aws_cdk as cdk
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_apigateway as apigw,
    aws_cognito as cognito,
    aws_lambda,
)
from constructs import Construct


class ApiStack(Stack):
    """
    Phase 6 — AWS CDK Agent
    Creates the REST API Gateway with Cognito authorizer and Lambda integrations.
    Endpoints:
      POST /feedback       → PostFeedbackFunction (returns 202)
      GET  /recommendation → GetRecommendationFunction (returns 200/404)
    Both endpoints require a valid Cognito JWT in the Authorization header.

    Initialisation is intentionally split into two phases so that app.py can
    declare the API Gateway first (the public entry-point) and wire the Cognito
    authorizer and Lambda routes afterwards:

        api_stack     = ApiStack(...)                         # 1. API Gateway
        cognito_stack = CognitoStack(...)                     # 2. Cognito pool
        api_stack.configure(user_pool, post_fn, get_fn)      # 3. connect authorizer
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── REST API ─────────────────────────────────────────────────────────
        # Created first — this is the public entry-point for all requests.
        self.api = apigw.RestApi(
            self,
            "FeedbackApi",
            rest_api_name="FeedbackService",
            description="Serverless Feedback & Recommendation API",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                tracing_enabled=True,
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=False,  # avoid logging sensitive request bodies
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Authorization", "Content-Type"],
            ),
        )

    def configure(
        self,
        user_pool: cognito.UserPool,
        post_feedback_fn: aws_lambda.Function,
        get_recommendation_fn: aws_lambda.Function,
    ) -> None:
        """Wire the Cognito authorizer and all routes into the REST API.

        Endpoints:
          POST /feedback       → Lambda #1 → SNS → SQS → Lambda #2 → Bedrock → DynamoDB
          GET  /recommendation → Lambda #3 → DynamoDB Query
        Both routes require a valid Cognito JWT in the Authorization header.
        """
        # ── Branch 1: Cognito Authorizer ─────────────────────────────────────
        # Validates every JWT against the Cognito User Pool before any Lambda
        # is invoked. This is the auth branch shown in the architecture diagram.
        authorizer = apigw.CognitoUserPoolsAuthorizer(
            self,
            "CognitoAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name="FeedbackCognitoAuthorizer",
            identity_source="method.request.header.Authorization",
        )

        # ── Branch 2: POST /feedback ─────────────────────────────────────────
        # Triggers the async processing pipeline:
        # Lambda #1 → SNS → SQS → Lambda #2 → Bedrock → DynamoDB
        # Returns 202 Accepted immediately — processing continues asynchronously.
        feedback_resource = self.api.root.add_resource("feedback")
        feedback_resource.add_method(
            "POST",
            apigw.LambdaIntegration(
                post_feedback_fn,
                proxy=True,
            ),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO,
            method_responses=[
                apigw.MethodResponse(status_code="202"),
                apigw.MethodResponse(status_code="400"),
                apigw.MethodResponse(status_code="500"),
            ],
        )

        # ── GET /recommendation ───────────────────────────────────────────────
        # Returns all AI recommendations for the authenticated user (or one by
        # feedback_id if ?feedback_id=<id> is supplied as a query parameter).
        # Lambda #3 queries DynamoDB server-side using its own IAM role.
        recommendation_resource = self.api.root.add_resource("recommendation")
        recommendation_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                get_recommendation_fn,
                proxy=True,
            ),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO,
            method_responses=[
                apigw.MethodResponse(status_code="200"),
                apigw.MethodResponse(status_code="404"),
                apigw.MethodResponse(status_code="500"),
            ],
        )

        # ── Outputs ──────────────────────────────────────────────────────────
        CfnOutput(
            self,
            "ApiUrl",
            value=self.api.url,
            description="API Gateway base URL — configure in Amplify front-end",
            export_name="FeedbackApiUrl",
        )
        CfnOutput(
            self,
            "PostFeedbackEndpoint",
            value=f"{self.api.url}feedback",
            description="POST /feedback endpoint",
        )
        CfnOutput(
            self,
            "GetRecommendationEndpoint",
            value=f"{self.api.url}recommendation",
            description="GET /recommendation endpoint",
        )
