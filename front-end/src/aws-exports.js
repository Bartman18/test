/**
 * Amplify configuration
 *
 * Values come from CDK CfnOutputs after `cdk deploy`.
 * Set these as environment variables in Amplify Console:
 *   REACT_APP_USER_POOL_ID        → CognitoStack > UserPoolId
 *   REACT_APP_USER_POOL_CLIENT_ID → CognitoStack > UserPoolClientId
 *   REACT_APP_IDENTITY_POOL_ID    → CognitoStack > IdentityPoolId
 *   REACT_APP_API_URL             → ApiStack > ApiUrl  (strip trailing slash)
 *   REACT_APP_TABLE_NAME          → DatabaseStack > RecommendationsTableName
 *   REACT_APP_AWS_REGION          → e.g. eu-central-1
 */
const awsExports = {
  Auth: {
    Cognito: {
      userPoolId:       process.env.REACT_APP_USER_POOL_ID,
      userPoolClientId: process.env.REACT_APP_USER_POOL_CLIENT_ID,
      identityPoolId:   process.env.REACT_APP_IDENTITY_POOL_ID,
      loginWith: {
        email: true,
      },
    },
  },
};

export default awsExports;
