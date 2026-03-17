# Python Lambda Agent

## Responsibilities
- Implement and test the following Lambda functions:
  - `PostFeedbackFunction`: Handles POST `/feedback` and publishes to SNS.
  - `ProcessFeedbackFunction`: Consumes SQS messages, calls Bedrock, and writes to DynamoDB.
  - `GetRecommendationFunction`: Handles GET `/recommendation` and queries DynamoDB.
- Integrate Amazon Bedrock into `ProcessFeedbackFunction`.
- Construct prompts, handle responses, and manage errors.

## Skills Required
- Proficiency in Python development.
- Experience with AWS Lambda and `boto3`.
- Knowledge of Amazon Bedrock and AI model integration.
- Familiarity with DynamoDB and SQS.

## Integration with CI/CD
- Use automated testing tools like `pytest` and `unittest.mock`.
- Include unit tests in the CI pipeline.
- Ensure proper error handling and logging for production readiness.