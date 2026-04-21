import { useState, useEffect } from "react";
import { api } from "../api.js";

const KINDS = ["meta", "file", "data", "people"];
const CHANNELS = ["procedural", "semantic", "episodic"];

export function UploadContextModal({ onClose, onUploaded }) {
  const [form, setForm] = useState({
    display_name: "",
    kind: "meta",
    channel: "semantic",
    description: "",
    content: "",
    source: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.display_name.trim() || !form.content.trim()) {
      setError("Name and content are required.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.uploadContext(form);
      onUploaded(res.item);
      onClose();
    } catch (err) {
      setError(err.message || "Upload failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-content" style={{ maxWidth: 520 }}>
        <div className="modal-header">
          <div className="modal-header-top">
            <h2 className="modal-title">Upload context block</h2>
            <button onClick={onClose} className="modal-close">×</button>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 12, padding: "16px 20px" }}>
            {error && (
              <div style={{ color: "var(--color-error, #DC2626)", fontSize: 13 }}>{error}</div>
            )}
            <label style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
              Name
              <input
                className="modal-input"
                style={{ marginTop: 4 }}
                value={form.display_name}
                onChange={set("display_name")}
                placeholder="e.g. api_guide.md"
                autoFocus
              />
            </label>
            <div style={{ display: "flex", gap: 12 }}>
              <label style={{ flex: 1, fontSize: 12, color: "var(--color-text-tertiary)" }}>
                Kind
                <select
                  className="modal-input"
                  style={{ marginTop: 4, width: "100%" }}
                  value={form.kind}
                  onChange={set("kind")}
                >
                  {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                </select>
              </label>
              <label style={{ flex: 1, fontSize: 12, color: "var(--color-text-tertiary)" }}>
                Channel
                <select
                  className="modal-input"
                  style={{ marginTop: 4, width: "100%" }}
                  value={form.channel}
                  onChange={set("channel")}
                >
                  {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
            </div>
            <label style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
              Description
              <input
                className="modal-input"
                style={{ marginTop: 4 }}
                value={form.description}
                onChange={set("description")}
                placeholder="Short summary of what this context is"
              />
            </label>
            <label style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
              Content
              <textarea
                className="modal-input"
                style={{ marginTop: 4, minHeight: 160, resize: "vertical", fontFamily: "var(--font-mono)", fontSize: 13 }}
                value={form.content}
                onChange={set("content")}
                placeholder="Paste the full context text here..."
              />
            </label>
            <label style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
              Source <span style={{ opacity: 0.5 }}>(optional)</span>
              <input
                className="modal-input"
                style={{ marginTop: 4 }}
                value={form.source}
                onChange={set("source")}
                placeholder="e.g. docs/api_guide.md"
              />
            </label>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, padding: "12px 20px", borderTop: "1px solid var(--color-border-tertiary)" }}>
            <button type="button" className="ctx-mock-btn" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className="ctx-controls-btn" disabled={loading}>
              {loading ? "Uploading…" : "Upload"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
