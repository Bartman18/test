import aws_cdk as cdk
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_cognito as cognito,
    aws_iam as iam,
)
from constructs import Construct


class CognitoStack(Stack):
    """
    Creates the Cognito User Pool, App Client, and Identity Pool.

    Exposes user_pool, app_client, identity_pool, and authenticated_role as
    public properties for dependent stacks.
    Call configure_grants(table) after DatabaseStack is created to grant the
    Identity Pool authenticated role read access to DynamoDB.
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
            generate_secret=False,  # SPAs cannot keep secrets; required for Amplify
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

        # ── Cognito Identity Pool ─────────────────────────────────────────────
        # Allows authenticated Cognito users to obtain temporary AWS credentials
        # so that Amplify (front-end) can query DynamoDB directly — no Lambda or
        # API Gateway needed for the read path (matches architecture diagram).
        self.identity_pool = cognito.CfnIdentityPool(
            self,
            "FeedbackIdentityPool",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[
                cognito.CfnIdentityPool.CognitoIdentityProviderProperty(
                    client_id=self.app_client.user_pool_client_id,
                    provider_name=self.user_pool.user_pool_provider_name,
                )
            ],
        )

        # IAM role assumed by authenticated Identity Pool users
        self.authenticated_role = iam.Role(
            self,
            "IdentityPoolAuthenticatedRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {
                        "cognito-identity.amazonaws.com:aud": self.identity_pool.ref,
                    },
                    "ForAnyValue:StringLike": {
                        "cognito-identity.amazonaws.com:amr": "authenticated",
                    },
                },
                assume_role_action="sts:AssumeRoleWithWebIdentity",
            ),
        )

        cognito.CfnIdentityPoolRoleAttachment(
            self,
            "IdentityPoolRoleAttachment",
            identity_pool_id=self.identity_pool.ref,
            roles={"authenticated": self.authenticated_role.role_arn},
        )

        CfnOutput(
            self,
            "IdentityPoolId",
            value=self.identity_pool.ref,
            description="Cognito Identity Pool ID — used by Amplify for direct DynamoDB reads",
            export_name="FeedbackIdentityPoolId",
        )

    def configure_grants(self, table) -> None:
        """Grant Identity Pool authenticated role read-only access to DynamoDB.

        Called after DatabaseStack so app.py reads in dependency order:
          1. API Gateway      (ApiStack.__init__)
          2. Cognito          (CognitoStack.__init__ — User Pool + Identity Pool)
          3. DynamoDB         (DatabaseStack)
          4. Messaging + Lambda
          5. api_stack.configure()        — POST /feedback + Cognito authorizer
          6. cognito_stack.configure_grants() — DynamoDB read grant for Amplify
        """
        # Amplify exchanges the Cognito JWT for short-lived AWS credentials via
        # the Identity Pool and uses them to query DynamoDB directly from the
        # browser — this is the "read current recommendations" branch in the
        # architecture diagram.
        table.grant_read_data(self.authenticated_role)
