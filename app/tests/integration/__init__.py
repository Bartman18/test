"""
Integration tests package.

Tests here run against a real deployed AWS environment.
They require the stacks to be deployed and the following environment variables set:

    API_URL              = https://<id>.execute-api.<region>.amazonaws.com/prod
    COGNITO_USER_POOL_ID = <FeedbackUserPoolId output>
    COGNITO_CLIENT_ID    = <FeedbackUserPoolClientId output>
    TEST_USER_EMAIL      = a valid Cognito user email
    TEST_USER_PASSWORD   = that user's password

Run with:
    pytest tests/integration/ -v
"""
