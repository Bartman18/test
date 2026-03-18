/**
 * RecommendationsPage — read subpage
 *
 * READ path (direct DynamoDB):
 *   Amplify exchanges the Cognito JWT for short-lived AWS credentials via
 *   the Cognito Identity Pool, then queries DynamoDB directly — no API
 *   Gateway or Lambda involved.
 */
import { useState, useEffect, useCallback } from 'react';
import { QueryCommand } from '@aws-sdk/lib-dynamodb';
import { TABLE_NAME, getDynamoContext } from '../lib/aws';
import Recommendation from '../components/Recommendation';

export default function RecommendationsPage() {
  const [items,   setItems]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { docClient, userId } = await getDynamoContext();
      if (!userId) { setLoading(false); return; }

      const result = await docClient.send(new QueryCommand({
        TableName:                 TABLE_NAME,
        KeyConditionExpression:    'user_id = :uid',
        ExpressionAttributeValues: { ':uid': userId },
        ScanIndexForward:          false, // newest first
      }));

      setItems(result.Items || []);
    } catch (err) {
      setError('Failed to load recommendations. Please try again.');
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
