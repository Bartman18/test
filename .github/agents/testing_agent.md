# Testing Agent

## Responsibilities
- Write unit tests for each Lambda handler using `pytest` and `unittest.mock`.
- Create CDK snapshot tests for each stack.
- Develop integration tests for the deployed environment.
- Ensure test coverage for the following scenarios:
  - Happy path.
  - Missing input (400 errors).
  - Not-found scenarios (404 errors).

## Skills Required
- Proficiency in Python testing frameworks (`pytest`, `unittest.mock`).
- Experience with AWS CDK testing using `aws_cdk.assertions`.
- Knowledge of integration testing for serverless applications.

## Integration with CI/CD
- Include unit and integration tests in the CI pipeline.
- Use coverage tools to ensure high test coverage.
- Automate test execution on pull requests and merges.