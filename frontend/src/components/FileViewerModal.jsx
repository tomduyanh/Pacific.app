import { useEffect } from "react";
import { KindBadge, KindSquare } from "./KindBadge.jsx";

export function FileViewerModal({ item, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!item) return null;

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-content" style={{ maxWidth: '600px', width: '100%' }}>
        <div className="modal-header">
          <div className="modal-header-top">
            <h2 className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <KindSquare kind={item.kind} size="md" />
              {item.display_name}
            </h2>
            <button onClick={onClose} className="modal-close">×</button>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '4px' }}>
            <KindBadge kind={item.kind} />
            <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary)' }}>{item.description}</span>
          </div>
        </div>
        <div className="modal-body" style={{ padding: '16px' }}>
          <pre style={{ 
            fontFamily: 'var(--font-mono)', 
            fontSize: '13px', 
            whiteSpace: 'pre-wrap', 
            margin: 0,
            color: 'var(--color-text-primary)'
          }}>
            {item.content}
          </pre>
        </div>
      </div>
    </div>
  );
}
