/**
 * Recommendation
 * Displays a single AI recommendation card.
 */
export default function Recommendation({ item }) {
  const date = item.timestamp
    ? new Date(item.timestamp).toLocaleString('en-US', {
        month: 'short',
        day:   'numeric',
        year:  'numeric',
        hour:  '2-digit',
        minute: '2-digit',
      })
    : null;

  return (
    <div className="card">
      <div className="rec-header">
        <span className="rec-title">AI Recommendation</span>
        {date && <span className="rec-date">{date}</span>}
      </div>

      {item.feedback_text && (
        <div className="rec-feedback">"{item.feedback_text}"</div>
      )}

      <div className="rec-text">{item.recommendation}</div>
    </div>
  );
}
