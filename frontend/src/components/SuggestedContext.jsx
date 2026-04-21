import { KindChipIcon } from "./KindBadge.jsx";

export function SuggestedContext({ suggestions, onAttach, onDismiss, onRefresh, loading, onItemClick }) {
  return (
    <div className="ctx-section">
      <div className="ctx-section-head">
        <h3 className="ctx-section-title">Suggested context</h3>
        <div className="ctx-section-actions">
          <span className="ctx-section-meta">based on current task</span>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="ctx-refresh-btn"
          >
            {loading ? "Scoring..." : "Refresh"}
          </button>
        </div>
      </div>
      <div className="ctx-suggest-grid">
        {suggestions.length === 0 && (
          <div className="ctx-suggest-empty">
            Simulate a user request or refresh scoring to get context recommendations.
          </div>
        )}
        {suggestions.map((item) => (
          <SuggestionCard key={item.id} item={item} onAttach={onAttach} onDismiss={onDismiss} onItemClick={onItemClick} />
        ))}
        {suggestions.length > 0 &&
          suggestions.length < 3 &&
          Array.from({ length: 3 - suggestions.length }).map((_, i) => (
            <div key={`empty-${i}`} className="ctx-suggest-placeholder" />
          ))}
      </div>
    </div>
  );
}

function SuggestionCard({ item, onAttach, onDismiss, onItemClick }) {
  return (
    <div className="ctx-suggest-card" onClick={() => onItemClick?.(item)} style={{ cursor: 'pointer' }}>
      <div className="ctx-suggest-head" title={item.display_name}>
        <KindChipIcon kind={item.kind} style={{ width: '22px', height: '22px' }} />
        <span className="ctx-suggest-name">{item.display_name}</span>
      </div>
      <p className="ctx-suggest-why" title={item.description}>{item.description}</p>
      <div className="ctx-suggest-actions">
        <button className="ctx-suggest-attach" onClick={(e) => { e.stopPropagation(); onAttach(item.id); }}>Attach</button>
        <span className="ctx-suggest-dismiss" onClick={(e) => { e.stopPropagation(); onDismiss(item.id); }}>Dismiss</span>
      </div>
    </div>
  );
}
