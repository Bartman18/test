/**
 * FeedbackForm  — Submit subpage
 *
 * WRITE path (async):
 *   POST /feedback → API Gateway → Lambda #1 → SNS → SQS → Lambda #2 → Bedrock → DynamoDB
 *   Lambda #1 returns 202 + { feedback_id } immediately.
 *
 * Polling:
 *   After 202, polls DynamoDB directly every 3 s until Lambda #2 writes the item.
 *   Once found, shows the result inline. Full history is on the Recommendations page.
 */
import { useState, useRef, useCallback } from 'react';
import { GetCommand } from '@aws-sdk/lib-dynamodb';
import { API_URL, TABLE_NAME, authHeader, getDynamoContext } from '../lib/aws';
import Recommendation from './Recommendation';

const POLL_INTERVAL_MS = 3_000;
const POLL_TIMEOUT_MS  = 120_000; // 2 minutes

export default function FeedbackForm() {
  const [text,     setText]     = useState('');
  const [status,   setStatus]   = useState('idle');
  // idle | submitting | polling | done | error
  const [errorMsg, setErrorMsg] = useState('');
  const [result,   setResult]   = useState(null); // the recommendation item once ready

  const intervalRef  = useRef(null);
  const startTimeRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  // ── Submit: POST /feedback → API Gateway ──────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;

    setStatus('submitting');
    setErrorMsg('');
    setResult(null);

    if (!API_URL) {
      setErrorMsg(
        'REACT_APP_API_URL is not configured. ' +
        'If running locally: copy .env.example to .env.local and fill in the value. ' +
        'If deployed on Amplify: add REACT_APP_API_URL in Amplify Console → Environment variables, ' +
        'then redeploy (env vars are baked in at build time — a new build is required).'
      );
      setStatus('error');
      return;
    }

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
        startPolling(feedback_id);
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

  // ── Poll DynamoDB until Lambda #2 writes the recommendation ───────────────
  function startPolling(feedback_id) {
    startTimeRef.current = Date.now();

    intervalRef.current = setInterval(async () => {
      if (Date.now() - startTimeRef.current > POLL_TIMEOUT_MS) {
        stopPolling();
        setStatus('error');
        setErrorMsg('Still processing — check back in Recommendations.');
        return;
      }

      try {
        const { docClient, userId } = await getDynamoContext();
        if (!userId) return;

        const res = await docClient.send(new GetCommand({
          TableName: TABLE_NAME,
          Key:       { user_id: userId, feedback_id },
        }));

        if (res.Item) {
          stopPolling();
          setResult(res.Item);
          setStatus('done');
        }
      } catch {
        // Network/credential hiccup — keep polling
      }
    }, POLL_INTERVAL_MS);
  }

  const isSubmitting = status === 'submitting';
  const isPolling    = status === 'polling';
  const isDisabled   = isSubmitting || isPolling;

  return (
    <div>
      <div className="page-header">
        <h2 className="page-title">Submit Feedback</h2>
        <p className="page-desc">
          Paste feedback you received and get an AI-generated career action plan.
        </p>
      </div>

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
              rows={5}
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

      {/* ── Inline result for the just-submitted item ── */}
      {result && (
        <>
          <p className="section-title">Your new recommendation</p>
          <Recommendation item={result} />
        </>
      )}
    </div>
  );
}
