/**
 * Recommendation — expandable accordion card
 *
 * Collapsed: shows feedback preview + date
 * Expanded:  shows full feedback quote + full AI recommendation
 */
import { useState } from 'react';

export default function Recommendation({ item }) {
  const [expanded, setExpanded] = useState(false);

  const date = item.timestamp
    ? new Date(item.timestamp).toLocaleString('en-US', {
        month:  'short',
        day:    'numeric',
        year:   'numeric',
        hour:   '2-digit',
        minute: '2-digit',
      })
    : null;

  // Truncate feedback for the collapsed preview
  const preview = item.feedback_text
    ? item.feedback_text.length > 90
      ? item.feedback_text.slice(0, 90).trimEnd() + '…'
      : item.feedback_text
    : null;

  return (
    <div className={`rec-accordion ${expanded ? 'rec-accordion--open' : ''}`}>
      {/* ── Clickable header (always visible) ── */}
      <button
        className="rec-accordion-header"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
      >
        <div className="rec-accordion-meta">
          {preview && (
            <span className="rec-accordion-preview">“{preview}”</span>
          )}
          {date && <span className="rec-date">{date}</span>}
        </div>
        <span className="rec-accordion-chevron">{expanded ? '▲' : '▼'}</span>
      </button>

      {/* ── Expanded body ── */}
      {expanded && (
        <div className="rec-accordion-body">
          {item.feedback_text && (
            <div className="rec-feedback">“{item.feedback_text}”</div>
          )}
          <div className="rec-text">{item.recommendation}</div>
        </div>
      )}
    </div>
  );
}
