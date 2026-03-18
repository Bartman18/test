/**
 * Shared AWS helpers
 * Used by both FeedbackForm (POST) and RecommendationsPage (GET via API Gateway).
 */
import { fetchAuthSession } from 'aws-amplify/auth';

export const API_URL    = (process.env.REACT_APP_API_URL    || '').replace(/\/$/, '');
export const AWS_REGION = process.env.REACT_APP_AWS_REGION  || 'eu-central-1';

// Debug: log resolved config on app load so you can verify env vars were baked
// in correctly during the build. Remove before production if desired.
console.log('[aws.js] resolved config →', {
  API_URL:    API_URL    || '⚠ EMPTY — REACT_APP_API_URL not set at build time',
  AWS_REGION,
});

if (!API_URL) {
  console.error(
    '[aws.js] REACT_APP_API_URL is not set.\n' +
    '  • Local dev:  copy front-end/.env.example → front-end/.env.local and fill values.\n' +
    '  • Amplify:    add REACT_APP_API_URL in Amplify Console → Environment variables,\n' +
    '                then trigger a new build (env vars are embedded at build time).'
  );
}

/** Returns Authorization header with the Cognito ID token (for API Gateway). */
export async function authHeader() {
  const session = await fetchAuthSession();
  const token   = session.tokens?.idToken?.toString();
  return { Authorization: token };
}
