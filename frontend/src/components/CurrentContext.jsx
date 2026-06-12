import { useEffect, useState } from "react";
import { KindChipIcon } from "./KindBadge.jsx";
import { relativeTime, absoluteTime } from "../format.js";

export function CurrentContext({ attached, onDetach, onOpenAttachModal, onItemClick }) {
  // Re-render once a minute so "2m" doesn't sit there reading "just now".
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="ctx-section">
      <div className="ctx-section-head">
        <h3 className="ctx-section-title">
          <span className="ctx-live-dot"></span>Current context
        </h3>
        <div className="ctx-section-meta">
          {attached.length} {attached.length === 1 ? "piece" : "pieces"} attached · editable
        </div>
      </div>
      <div className="ctx-current">
        <div className="ctx-chips">
          {attached.map((item) => (
            <Chip key={item.id} item={item} onDetach={onDetach} onItemClick={onItemClick} />
          ))}
          <button
            onClick={onOpenAttachModal}
            className="ctx-chip ctx-chip-add"
          >
            <span className="ctx-chip-name">+ attach</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function Chip({ item, onDetach, onItemClick }) {
  const since = relativeTime(item.attached_at, { short: true });
  const title = since
    ? `${item.description}

Attached ${relativeTime(item.attached_at)} (${absoluteTime(item.attached_at)})`
    : item.description;
  return (
    <span className="ctx-chip ctx-chip-clickable" title={title} onClick={() => onItemClick?.(item)}>
      <KindChipIcon kind={item.kind} />
      <span className="ctx-chip-name">{item.display_name}</span>
      <span className="ctx-chip-type">{item.kind}</span>
      {since && <span className="ctx-chip-since">{since}</span>}
      <span
        className="ctx-chip-x"
        onClick={(e) => { e.stopPropagation(); onDetach(item.id); }}
        aria-label={`Remove ${item.display_name}`}
      >
        ×
      </span>
    </span>
  );
}
