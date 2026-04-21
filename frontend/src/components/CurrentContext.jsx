import { KindChipIcon } from "./KindBadge.jsx";

export function CurrentContext({ attached, onDetach, onOpenAttachModal, onItemClick }) {
  return (
    <div className="ctx-section">
      <div className="ctx-section-head">
        <h3 className="ctx-section-title">
          <span className="ctx-live-dot"></span>Current context
        </h3>
        <div className="ctx-section-meta">
          {attached.length} pieces attached · editable
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
  return (
    <span className="ctx-chip" title={item.description} onClick={() => onItemClick?.(item)} style={{ cursor: 'pointer' }}>
      <KindChipIcon kind={item.kind} />
      <span className="ctx-chip-name">{item.display_name}</span>
      <span className="ctx-chip-type">{item.kind}</span>
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
