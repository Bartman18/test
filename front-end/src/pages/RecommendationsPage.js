/**
 * RecommendationsPage — read subpage
 *
 * READ path (via API Gateway):
 *   GET /recommendation  →  API Gateway (Cognito authorizer)
 *   →  Lambda #3  →  DynamoDB Query  →  { items: [...] }
 *
 *   Uses the same Cognito ID-token JWT already in the browser session.
 *   No Identity Pool or DynamoDB SDK credentials needed.
 */
import { useState, useEffect, useCallback } from 'react';
import { API_URL, authHeader } from '../lib/aws';
import Recommendation from '../components/Recommendation';

export default function RecommendationsPage() {
  const [items,   setItems]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_URL}/recommendation`, {
        headers: await authHeader(),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }

      const data = await res.json();
      // Sort newest-first by timestamp (Lambda returns in DynamoDB scan order)
      const sorted = (data.items || []).sort((a, b) =>
        (b.timestamp || '').localeCompare(a.timestamp || '')
      );
      setItems(sorted);
    } catch (err) {
      console.error('[RecommendationsPage] load error', err);
      setError(`Failed to load recommendations: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <div className="page-header">
        <div className="page-header-row">
          <div>
            <h2 className="page-title">My Recommendations</h2>
            <p className="page-desc">
              All AI-generated career action plans from your submitted feedback.
            </p>
          </div>
          <button
            className="btn btn-ghost"
            onClick={load}
            disabled={loading}
            title="Refresh"
          >
            {loading ? 'Loading…' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {error && <p className="error-msg">{error}</p>}

      {loading && !error && (
        <div className="loading-row">
          <span className="spinner" />
          <span style={{ color: '#64748b', fontSize: '0.875rem' }}>Loading…</span>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <p className="empty-state">
          No recommendations yet — go to <strong>Submit Feedback</strong> to get started.
        </p>
      )}

      {!loading && items.length > 0 && (
        <>
          <p className="section-title">
            {items.length} recommendation{items.length !== 1 ? 's' : ''}
          </p>
          {items.map(item => (
            <Recommendation key={item.feedback_id} item={item} />
          ))}
        </>
      )}
    </div>
  );
}
