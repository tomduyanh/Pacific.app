import { useState, useEffect, useRef } from "react";
import { KindBadge, KindSquare } from "./KindBadge.jsx";

export function AttachModal({ pool, onAttach, onClose }) {
  const [search, setSearch] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const available = pool
    .filter((item) => item.status !== "active")
    .filter((item) => {
      if (!search) return true;
      const q = search.toLowerCase();
      return item.display_name.toLowerCase().includes(q) || item.description.toLowerCase().includes(q);
    })
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-content">
        <div className="modal-header">
          <div className="modal-header-top">
            <h2 className="modal-title">Route context block</h2>
            <button onClick={onClose} className="modal-close">×</button>
          </div>
          <input
            ref={inputRef}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search context..."
            className="modal-input"
          />
        </div>
        <div className="modal-body">
          {available.length === 0 && (
            <div style={{ padding: '32px 0', textAlign: 'center', fontSize: '13px', color: 'var(--color-text-tertiary)' }}>
              No context blocks found.
            </div>
          )}
          {available.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                onAttach(item.id);
                onClose();
              }}
              className="modal-item"
            >
              <div className="modal-item-icon">
                <KindSquare kind={item.kind} size="md" />
              </div>
              <div className="modal-item-content">
                <div className="modal-item-title-row">
                  <span className="modal-item-title">{item.display_name}</span>
                  <KindBadge kind={item.kind} />
                </div>
                <div className="modal-item-desc">{item.description}</div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
