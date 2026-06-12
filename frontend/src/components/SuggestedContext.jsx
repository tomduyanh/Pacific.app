import { KindChipIcon } from "./KindBadge.jsx";
import { Companion } from "./Companion.jsx";

export function SuggestedContext({
  suggestions,
  onAttach,
  onDismiss,
  onRefresh,
  loading,
  onItemClick,
  percentileOf,
  suggestReason,
}) {
  const showSkeleton = loading && suggestions.length === 0;

  return (
    <div className="ctx-section">
      <div className="ctx-section-head">
        <h3 className="ctx-section-title">Suggested context</h3>
        <div className="ctx-section-actions">
          <span className="ctx-section-meta">based on current task</span>
          <button onClick={onRefresh} disabled={loading} className="ctx-refresh-btn">
            {loading ? "Scoring…" : "Refresh"}
          </button>
        </div>
      </div>
      <div className={`ctx-suggest-grid ${loading ? "is-scoring" : ""}`}>
        {showSkeleton &&
          Array.from({ length: 3 }).map((_, i) => <div key={`skel-${i}`} className="ctx-suggest-skeleton" />)}

        {!showSkeleton && suggestions.length === 0 && (
          <div className="ctx-suggest-empty">
            <Companion emote="empty" size={96} showLine={false} />
            <p className="ctx-suggest-empty-title">
              {suggestReason === "no_clear_signal"
                ? "Nothing stands out right now"
                : "Nothing to suggest yet"}
            </p>
            <p className="ctx-suggest-empty-sub">
              {suggestReason === "no_clear_signal"
                ? "I scored everything and nothing clearly fits what you're doing. Tell me more, or keep working and I'll watch."
                : "Say what you're working on, or share your screen, and I'll pull what's relevant."}
            </p>
          </div>
        )}

        {suggestions.map((item, i) => (
          <SuggestionCard
            key={item.id}
            item={item}
            rank={i + 1}
            percentile={percentileOf?.(item.score)}
            onAttach={onAttach}
            onDismiss={onDismiss}
            onItemClick={onItemClick}
          />
        ))}

        {!showSkeleton &&
          suggestions.length > 0 &&
          suggestions.length < 3 &&
          Array.from({ length: 3 - suggestions.length }).map((_, i) => (
            <div key={`empty-${i}`} className="ctx-suggest-placeholder" />
          ))}
      </div>
    </div>
  );
}

function SuggestionCard({ item, rank, percentile, onAttach, onDismiss, onItemClick }) {
  return (
    <div
      className="ctx-suggest-card"
      onClick={() => onItemClick?.(item)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onItemClick?.(item);
        }
      }}
    >
      <div className="ctx-suggest-head" title={item.display_name}>
        <KindChipIcon kind={item.kind} />
        <span className="ctx-suggest-name">{item.display_name}</span>
        <span className="ctx-suggest-rank">#{rank}</span>
      </div>
      <p className="ctx-suggest-why" title={item.description}>
        {item.description}
      </p>
      {percentile !== null && percentile !== undefined && (
        <div
          className="ctx-suggest-relevance"
          title={`Scores above ${percentile}% of the context pool (raw score ${item.score?.toFixed(3)})`}
        >
          <div className="ctx-suggest-relevance-bar">
            <div className="ctx-suggest-relevance-fill" style={{ width: `${percentile}%` }} />
          </div>
          <span className="ctx-suggest-relevance-val">{percentile}%</span>
        </div>
      )}
      <div className="ctx-suggest-actions">
        <button
          className="ctx-suggest-attach"
          onClick={(e) => {
            e.stopPropagation();
            onAttach(item.id);
          }}
        >
          Attach
        </button>
        <button
          className="ctx-suggest-dismiss"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss(item.id);
          }}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
