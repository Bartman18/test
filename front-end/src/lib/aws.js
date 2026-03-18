/**
 * Shared AWS helpers
 * Used by both SubmitFeedbackPage (POST) and RecommendationsPage (DynamoDB read).
 */
import { fetchAuthSession } from 'aws-amplify/auth';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient } from '@aws-sdk/lib-dynamodb';

export const API_URL    = (process.env.REACT_APP_API_URL    || '').replace(/\/$/, '');
export const TABLE_NAME = process.env.REACT_APP_TABLE_NAME  || 'Recommendations';
export const AWS_REGION = process.env.REACT_APP_AWS_REGION  || 'eu-central-1';

if (!API_URL) {
  console.error(
    '[aws.js] REACT_APP_API_URL is not set. ' +
    'Copy front-end/.env.example to front-end/.env and fill in your CDK outputs.'
  );
}

/** Returns Authorization header with the Cognito ID token (for API Gateway). */
export async function authHeader() {
  const session = await fetchAuthSession();
  const token   = session.tokens?.idToken?.toString();
  return { Authorization: token };
}

/**
 * Returns a DynamoDBDocumentClient and the authenticated userId (Cognito sub).
 * Credentials come from the Cognito Identity Pool — no API Gateway involved.
 */
export async function getDynamoContext() {
  const session     = await fetchAuthSession();
  const credentials = session.credentials;
  const userId      = session.tokens?.idToken?.payload?.sub;

  const client    = new DynamoDBClient({ region: AWS_REGION, credentials });
  const docClient = DynamoDBDocumentClient.from(client, {
    marshallOptions:   { removeUndefinedValues: true },
    unmarshallOptions: { wrapNumbers: false },
  });

  return { docClient, userId };
}
