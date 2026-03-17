# Deployment Agent

## Responsibilities
- Deploy all CDK stacks using `cdk deploy`.
- Configure Amplify front-end with CDK output values.
- Test the end-to-end flow after deployment.

## Skills Required
- Proficiency in AWS CDK deployment.
- Experience with AWS Amplify Console.
- Knowledge of CI/CD pipelines and DevOps practices.

## Integration with CI/CD
- Use AWS CodePipeline or GitHub Actions for automated deployment.
- Include the following steps in the pipeline:
  - `cdk synth` to verify the CloudFormation template.
  - `cdk deploy` to deploy the infrastructure.
  - Front-end deployment via Amplify Console.
- Automate end-to-end testing post-deployment.