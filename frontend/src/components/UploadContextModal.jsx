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
      <div className="modal-content modal-content-wide">
        <div className="modal-header">
          <div className="modal-header-top">
            <h2 className="modal-title">Upload context block</h2>
            <button type="button" onClick={onClose} className="modal-close" aria-label="Close">
              ×
            </button>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body modal-form">
            {error && <div className="modal-form-error">{error}</div>}

            <label className="modal-field">
              <span className="modal-field-label">Name</span>
              <input
                className="modal-input"
                value={form.display_name}
                onChange={set("display_name")}
                placeholder="e.g. api_guide.md"
                autoFocus
              />
            </label>

            <div className="modal-field-row">
              <label className="modal-field">
                <span className="modal-field-label">Kind</span>
                <select className="modal-input" value={form.kind} onChange={set("kind")}>
                  {KINDS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </label>
              <label className="modal-field">
                <span className="modal-field-label">Channel</span>
                <select className="modal-input" value={form.channel} onChange={set("channel")}>
                  {CHANNELS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="modal-field">
              <span className="modal-field-label">Description</span>
              <input
                className="modal-input"
                value={form.description}
                onChange={set("description")}
                placeholder="Short summary of what this context is"
              />
            </label>

            <label className="modal-field">
              <span className="modal-field-label">Content</span>
              <textarea
                className="modal-input modal-textarea"
                value={form.content}
                onChange={set("content")}
                placeholder="Paste the full context text here..."
              />
            </label>

            <label className="modal-field">
              <span className="modal-field-label">
                Source <span className="modal-field-optional">(optional)</span>
              </span>
              <input
                className="modal-input"
                value={form.source}
                onChange={set("source")}
                placeholder="e.g. docs/api_guide.md"
              />
            </label>
          </div>

          <div className="modal-footer">
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
