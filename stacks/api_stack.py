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
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        user_pool: cognito.UserPool,
        post_feedback_fn: aws_lambda.Function,
        get_recommendation_fn: aws_lambda.Function,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── REST API ─────────────────────────────────────────────────────────
        api = apigw.RestApi(
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

        # ── Cognito Authorizer ───────────────────────────────────────────────
        authorizer = apigw.CognitoUserPoolsAuthorizer(
            self,
            "CognitoAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name="FeedbackCognitoAuthorizer",
            identity_source="method.request.header.Authorization",
        )

        # ── POST /feedback ───────────────────────────────────────────────────
        feedback_resource = api.root.add_resource("feedback")
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

        # ── GET /recommendation ──────────────────────────────────────────────
        recommendation_resource = api.root.add_resource("recommendation")
        recommendation_resource.add_method(
            "GET",
            apigw.LambdaIntegration(
                get_recommendation_fn,
                proxy=True,
            ),
            authorizer=authorizer,
            authorization_type=apigw.AuthorizationType.COGNITO,
            request_parameters={
                "method.request.querystring.feedback_id": False,  # optional param
            },
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
            value=api.url,
            description="API Gateway base URL — configure in Amplify front-end",
            export_name="FeedbackApiUrl",
        )
        CfnOutput(
            self,
            "PostFeedbackEndpoint",
            value=f"{api.url}feedback",
            description="POST /feedback endpoint",
        )
        CfnOutput(
            self,
            "GetRecommendationEndpoint",
            value=f"{api.url}recommendation",
            description="GET /recommendation endpoint",
        )
