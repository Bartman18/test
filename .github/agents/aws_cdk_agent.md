# AWS CDK Agent

## Responsibilities
- Initialize the CDK project.
- Set up the virtual environment and install dependencies.
- Configure `cdk.json` and `app.py` to load all stacks.
- Create and manage the following stacks:
  - Cognito Stack: User Pool and App Client.
  - DynamoDB Stack: Recommendations table.
  - Messaging Stack: SNS Topic, SQS Queue, and DLQ.
  - API Gateway Stack: REST API and Cognito Authorizer.

## Skills Required
- Proficiency in AWS CDK (Python).
- Knowledge of AWS services: Cognito, DynamoDB, SNS, SQS, API Gateway.
- Familiarity with infrastructure-as-code (IaC) principles.
- Experience with Python development and virtual environments.

## Integration with CI/CD
- Use AWS CodePipeline or GitHub Actions for automated deployment.
- Include `cdk synth` and `cdk deploy` steps in the pipeline.
- Use `cdk diff` to preview changes before deployment.