import aws_cdk as cdk
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_cognito as cognito,
)
from constructs import Construct


class CognitoStack(Stack):
    """
    Phase 2 — AWS CDK Agent
    Creates the Cognito User Pool and App Client used for authentication.
    Exposes user_pool and app_client as public properties for dependent stacks.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── User Pool ────────────────────────────────────────────────────────
        self.user_pool = cognito.UserPool(
            self,
            "FeedbackUserPool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,  # dev/test only
        )

        # ── App Client (no secret — SPA / Amplify use) ───────────────────────
        self.app_client = self.user_pool.add_client(
            "AmplifyAppClient",
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
            ),
            prevent_user_existence_errors=True,
        )

        # ── Outputs for Amplify front-end configuration ──────────────────────
        CfnOutput(
            self,
            "UserPoolId",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID",
            export_name="FeedbackUserPoolId",
        )
        CfnOutput(
            self,
            "UserPoolClientId",
            value=self.app_client.user_pool_client_id,
            description="Cognito App Client ID",
            export_name="FeedbackUserPoolClientId",
        )
