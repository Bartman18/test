/**
 * FeedbackForm
 *
 * Flow:
 *   1. User types feedback → POST /feedback (JWT in Authorization header)
 *   2. API returns 202 + { feedback_id }
 *   3. Poll GET /recommendation?feedback_id=<id> every 3 s until 200
 *   4. Add recommendation to the list and reset the form
 *
 * On mount, existing recommendations for the authenticated user are loaded.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchAuthSession } from 'aws-amplify/auth';
import Recommendation from './Recommendation';

const API_URL = (process.env.REACT_APP_API_URL || '').replace(/\/$/, '');
const POLL_INTERVAL_MS = 3_000;
const POLL_TIMEOUT_MS  = 120_000; // 2 minutes max

// ── Auth helper ─────────────────────────────────────────────────────────────
async function authHeader() {
  const session = await fetchAuthSession();
  const token   = session.tokens?.idToken?.toString();
  return { Authorization: token };
}

// ── Component ────────────────────────────────────────────────────────────────
export default function FeedbackForm() {
  const [text,            setText]           = useState('');
  const [status,          setStatus]         = useState('idle');
  // idle | submitting | polling | done | error
  const [errorMsg,        setErrorMsg]       = useState('');
  const [recommendations, setRecommendations] = useState([]);

  const intervalRef  = useRef(null);
  const startTimeRef = useRef(null);

  // ── Stop polling helper ────────────────────────────────────────────────
  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  // ── Load existing recommendations on mount ─────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_URL}/recommendation`, {
          headers: await authHeader(),
        });
        if (res.ok) {
          const data = await res.json();
          // Sort newest first
          const items = (data.items || []).sort(
            (a, b) => new Date(b.timestamp) - new Date(a.timestamp)
          );
          setRecommendations(items);
        }
      } catch (_) {
        // Silent fail — user may have no data yet
      }
    })();

    return () => stopPolling();
  }, [stopPolling]);

  // ── Submit ─────────────────────────────────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;

    setStatus('submitting');
    setErrorMsg('');

    try {
      const res = await fetch(`${API_URL}/feedback`, {
        method: 'POST',
        headers: {
          ...(await authHeader()),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ feedback_text: trimmed }),
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

  // ── Polling ────────────────────────────────────────────────────────────
  function startPolling(feedback_id) {
    startTimeRef.current = Date.now();

    intervalRef.current = setInterval(async () => {
      // Timeout guard
      if (Date.now() - startTimeRef.current > POLL_TIMEOUT_MS) {
        stopPolling();
        setStatus('error');
        setErrorMsg('Still processing — refresh the page in a moment to see your recommendation.');
        return;
      }

      try {
        const res = await fetch(
          `${API_URL}/recommendation?feedback_id=${encodeURIComponent(feedback_id)}`,
          { headers: await authHeader() }
        );

        if (res.ok) {
          const item = await res.json();
          stopPolling();
          setRecommendations(prev => [item, ...prev]);
          setStatus('done');
        }
        // 404 = Bedrock hasn't finished yet → keep polling
      } catch {
        // Network hiccup → keep polling, do not abort
      }
    }, POLL_INTERVAL_MS);
  }

  // ── Derived state ──────────────────────────────────────────────────────
  const isSubmitting = status === 'submitting';
  const isPolling    = status === 'polling';
  const isDisabled   = isSubmitting || isPolling;

  // ── Render ─────────────────────────────────────────────────────────────
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

      {/* ── Recommendations list ── */}
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
