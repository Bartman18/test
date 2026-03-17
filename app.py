#!/usr/bin/env python3
import aws_cdk as cdk

from stacks.cognito_stack import CognitoStack
from stacks.database_stack import DatabaseStack
from stacks.messaging_stack import MessagingStack
from stacks.lambda_stack import LambdaStack
from stacks.api_stack import ApiStack

app = cdk.App()

cognito_stack = CognitoStack(app, "CognitoStack")

database_stack = DatabaseStack(app, "DatabaseStack")

messaging_stack = MessagingStack(app, "MessagingStack")

lambda_stack = LambdaStack(
    app,
    "LambdaStack",
    table=database_stack.table,
    topic=messaging_stack.topic,
    queue=messaging_stack.queue,
)

api_stack = ApiStack(
    app,
    "ApiStack",
    user_pool=cognito_stack.user_pool,
    post_feedback_fn=lambda_stack.post_feedback_fn,
    get_recommendation_fn=lambda_stack.get_recommendation_fn,
)

app.synth()
