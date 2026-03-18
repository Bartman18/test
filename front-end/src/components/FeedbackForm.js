/**
 * FeedbackForm
 *
 * Architecture (matches diagram):
 *
 *   WRITE path (async):
 *     User submits → POST /feedback (API Gateway → Lambda #1 → SNS → SQS)
 *     Lambda #1 returns 202 + { feedback_id } immediately.
 *     Lambda #2 runs asynchronously: SQS → Bedrock → DynamoDB.
 *
 *   READ path (direct DynamoDB):
 *     Amplify exchanges the Cognito JWT for short-lived AWS credentials via
 *     the Cognito Identity Pool, then queries DynamoDB directly — no API
 *     Gateway or Lambda involved.
 *
 *   Polling:
 *     After receiving 202, poll DynamoDB directly every 3 s until the
 *     recommendation item appears (written by Lambda #2).
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchAuthSession } from 'aws-amplify/auth';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, QueryCommand, GetCommand } from '@aws-sdk/lib-dynamodb';
import Recommendation from './Recommendation';

const API_URL    = (process.env.REACT_APP_API_URL    || '').replace(/\/$/, '');
const TABLE_NAME = process.env.REACT_APP_TABLE_NAME  || 'Recommendations';
const AWS_REGION = process.env.REACT_APP_AWS_REGION  || 'eu-central-1';

const POLL_INTERVAL_MS = 3_000;
const POLL_TIMEOUT_MS  = 120_000; // 2 minutes max

// ── Auth helper — JWT for API Gateway (POST /feedback) ─────────────────────
async function authHeader() {
  const session = await fetchAuthSession();
  const token   = session.tokens?.idToken?.toString();
  return { Authorization: token };
}

// ── DynamoDB client — Identity Pool credentials for direct reads ───────────
async function getDynamoContext() {
  const session     = await fetchAuthSession();
  const credentials = session.credentials;              // from Identity Pool
  const userId      = session.tokens?.idToken?.payload?.sub;

  const client    = new DynamoDBClient({ region: AWS_REGION, credentials });
  const docClient = DynamoDBDocumentClient.from(client, {
    marshallOptions:   { removeUndefinedValues: true },
    unmarshallOptions: { wrapNumbers: false },
  });

  return { docClient, userId };
}

// ── Component ────────────────────────────────────────────────────────────────
export default function FeedbackForm() {
  const [text,            setText]            = useState('');
  const [status,          setStatus]          = useState('idle');
  // idle | submitting | polling | done | error
  const [errorMsg,        setErrorMsg]        = useState('');
  const [recommendations, setRecommendations] = useState([]);

  const intervalRef  = useRef(null);
  const startTimeRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  // ── On mount: load all existing recommendations directly from DynamoDB ───
  useEffect(() => {
    (async () => {
      try {
        const { docClient, userId } = await getDynamoContext();
        if (!userId) return;

        const result = await docClient.send(new QueryCommand({
          TableName:                 TABLE_NAME,
          KeyConditionExpression:    'user_id = :uid',
          ExpressionAttributeValues: { ':uid': userId },
          ScanIndexForward:          false, // newest first
        }));

        setRecommendations(result.Items || []);
      } catch (_) {
        // Silent fail — user may have no data yet
      }
    })();

    return () => stopPolling();
  }, [stopPolling]);

  // ── Submit: POST /feedback → API Gateway → Lambda #1 → SNS (returns 202) ─
  async function handleSubmit(e) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;

    setStatus('submitting');
    setErrorMsg('');

    try {
      const res = await fetch(`${API_URL}/feedback`, {
        method:  'POST',
        headers: { ...(await authHeader()), 'Content-Type': 'application/json' },
        body:    JSON.stringify({ feedback_text: trimmed }),
      });

      if (res.status === 202) {
        const { feedback_id } = await res.json();
        setText('');
        setStatus('polling');
        startPolling(feedback_id); // Lambda #2 will write to DynamoDB async
      } else {
        const err = await res.json().catch(() => ({}));
        setErrorMsg(err.error || `Unexpected status ${res.status}`);
        setStatus('error');
      }
    } catch {
      setErrorMsg('Network error — please try again.');
      setStatus('error');
    }
  }

  // ── Poll DynamoDB directly until Lambda #2 writes the recommendation ──────
  function startPolling(feedback_id) {
    startTimeRef.current = Date.now();

    intervalRef.current = setInterval(async () => {
      if (Date.now() - startTimeRef.current > POLL_TIMEOUT_MS) {
        stopPolling();
        setStatus('error');
        setErrorMsg('Still processing — check back in a moment.');
        return;
      }

      try {
        const { docClient, userId } = await getDynamoContext();
        if (!userId) return;

        const result = await docClient.send(new GetCommand({
          TableName: TABLE_NAME,
          Key:       { user_id: userId, feedback_id },
        }));

        if (result.Item) {
          stopPolling();
          setRecommendations(prev => [result.Item, ...prev]);
          setStatus('done');
        }
        // Item not yet written by Lambda #2 → keep polling
      } catch {
        // Credential or network hiccup → keep polling
      }
    }, POLL_INTERVAL_MS);
  }

  const isSubmitting = status === 'submitting';
  const isPolling    = status === 'polling';
  const isDisabled   = isSubmitting || isPolling;

  return (
    <div>
      {/* ── Form card ── */}
      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="feedback-text">
              Feedback you received
            </label>
            <textarea
              id="feedback-text"
              className="form-textarea"
              value={text}
              onChange={e => setText(e.target.value)}
              placeholder="e.g. You need to improve communication with the team and take more ownership in meetings…"
              disabled={isDisabled}
              rows={4}
            />
          </div>

          <div className="status-row">
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!text.trim() || isDisabled}
            >
              {isSubmitting ? 'Submitting…' : 'Get AI Recommendation'}
            </button>

            {isPolling && (
              <span className="status-polling">
                <span className="spinner" />
                Generating recommendation…
              </span>
            )}

            {status === 'done' && (
              <span className="status-done">✓ Recommendation ready</span>
            )}
          </div>

          {status === 'error' && (
            <p className="error-msg">{errorMsg}</p>
          )}
        </form>
      </div>

      {/* ── Recommendations list (read directly from DynamoDB) ── */}
      {recommendations.length > 0 ? (
        <>
          <p className="section-title">
            Recommendations ({recommendations.length})
          </p>
          {recommendations.map(item => (
            <Recommendation key={item.feedback_id} item={item} />
          ))}
        </>
      ) : (
        !isPolling && status !== 'submitting' && (
          <p className="empty-state">
            No recommendations yet — submit your first feedback above.
          </p>
        )
      )}
    </div>
  );
}
