import { useState, useEffect, useCallback } from "react";
import { api } from "./api.js";
import { CurrentContext } from "./components/CurrentContext.jsx";
import { SuggestedContext } from "./components/SuggestedContext.jsx";
import { RawContextTable } from "./components/RawContextTable.jsx";
import { AttachModal } from "./components/AttachModal.jsx";
import { UploadContextModal } from "./components/UploadContextModal.jsx";
import { KindSquare, KindBadge } from "./components/KindBadge.jsx";
import { ActivityLog } from "./components/ActivityLog.jsx";
import { ScreenCapture } from "./components/ScreenCapture.jsx";

export default function App() {
  const [pool, setPool] = useState([]);
  const [attached, setAttached] = useState([]);
  const [tokensUsed, setTokensUsed] = useState(0);
  const [tokenBudget, setTokenBudget] = useState(10000);
  const [message, setMessage] = useState("");
  const [showAttachModal, setShowAttachModal] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [viewingFile, setViewingFile] = useState(null);
  const [sessionEvents, setSessionEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const suggestions = pool.filter((i) => i.status === "suggested");
  const pct = tokenBudget > 0 ? Math.min(100, Math.round((tokensUsed / tokenBudget) * 100)) : 0;

  const loadState = useCallback(async () => {
    try {
      const state = await api.getState();
      setPool(state.pool);
      setAttached(state.attached);
      setTokensUsed(state.tokens_used);
      setTokenBudget(state.token_budget);
      setSessionEvents(state.session_events || []);
    } catch (e) {
      setError("Failed to connect to backend. Is the server running?");
    }
  }, []);

  useEffect(() => {
    loadState();
  }, [loadState]);

  const handleSendMessage = async () => {
    if (!message.trim()) return;
    setLoading(true);
    try {
      await api.postMessage(message.trim());
      setMessage("");
      await loadState();
    } catch (e) {
      setError("Rescore failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleClearSession = async () => {
    setLoading(true);
    try {
      await api.clearSession();
      await loadState();
    } catch (e) {
      setError("Clear session failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setLoading(true);
    try {
      await api.rescore();
      await loadState();
    } catch (e) {
      setError("Refresh failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleAttach = async (id) => {
    try {
      await api.attach(id);
      await loadState();
    } catch (e) {
      setError("Attach failed.");
    }
  };

  const handleDetach = async (id) => {
    try {
      await api.detach(id);
      await loadState();
    } catch (e) {
      setError("Detach failed.");
    }
  };

  const handleDismiss = async (id) => {
    try {
      await api.dismiss(id);
      await loadState();
    } catch (e) {
      setError("Dismiss failed.");
    }
  };

  return (
    <div className="layout-main">
      <div className="ctx-app">
        <div className="ctx-top">
          <div>
            <h2 className="ctx-title">Context dashboard</h2>
            <div className="ctx-session">
              <button
                className="ctx-mock-btn"
                style={{ marginLeft: "8px", fontSize: "12px", padding: "2px 10px" }}
                onClick={handleClearSession}
                disabled={loading}
                title="Reset all session events, history, and scores"
              >
                Clear session
              </button>
              <button
                className="ctx-mock-btn"
                style={{ marginLeft: "6px", fontSize: "12px", padding: "2px 10px" }}
                onClick={() => setShowUploadModal(true)}
                title="Upload a new context block to the pool"
              >
                + Upload context
              </button>
            </div>
          </div>
          <div className="ctx-meter">
            <div className="ctx-meter-label">Context loaded</div>
            <div className="ctx-meter-val">
              {tokensUsed.toLocaleString()} / {tokenBudget.toLocaleString()} tokens
            </div>
            <div className="ctx-meter-bar">
              <div
                className="ctx-meter-fill"
                style={{ width: `${pct}%`, background: pct > 80 ? '#D97706' : 'var(--color-text-primary)' }}
              ></div>
            </div>
          </div>
        </div>

        {error && (
          <div className="ctx-error">
            <span>{error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        <CurrentContext
          attached={attached}
          onDetach={handleDetach}
          onOpenAttachModal={() => setShowAttachModal(true)}
          onItemClick={setViewingFile}
        />

        <SuggestedContext
          suggestions={suggestions}
          onAttach={handleAttach}
          onDismiss={handleDismiss}
          onRefresh={handleRefresh}
          loading={loading}
          onItemClick={setViewingFile}
        />

        <RawContextTable
          pool={pool}
          onAttach={handleAttach}
          onDetach={handleDetach}
          onItemClick={setViewingFile}
        />

        <div className="ctx-controls">
          <input
            className="ctx-controls-input"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSendMessage()}
            placeholder="Simulate user request to rescore..."
          />
          <button
            className="ctx-controls-btn"
            onClick={handleSendMessage}
            disabled={loading || !message.trim()}
          >
            Rescore Context
          </button>
        </div>
      </div>

      {showAttachModal && (
        <AttachModal
          pool={pool}
          onAttach={handleAttach}
          onClose={() => setShowAttachModal(false)}
        />
      )}

      {showUploadModal && (
        <UploadContextModal
          onClose={() => setShowUploadModal(false)}
          onUploaded={() => loadState()}
        />
      )}
      
      <div className="ctx-side-panel">
        {viewingFile && (
          <div style={{ display: 'flex', flexDirection: 'column', maxHeight: '50%', borderBottom: '1px solid var(--color-border-tertiary)', overflowY: 'auto', flexShrink: 0 }}>
            <div className="ctx-side-panel-header" style={{ borderRadius: 0 }}>
              <div className="ctx-side-panel-title">
                <KindSquare kind={viewingFile.kind} size="md" />
                {viewingFile.display_name}
              </div>
              <button onClick={() => setViewingFile(null)} className="modal-close" style={{fontSize: '16px'}}>×</button>
            </div>
            <div className="ctx-side-panel-content">
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '16px' }}>
                <KindBadge kind={viewingFile.kind} />
                <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary)' }}>{viewingFile.description}</span>
              </div>
              <pre style={{ 
                fontFamily: 'var(--font-mono)', 
                fontSize: '13px', 
                whiteSpace: 'pre-wrap', 
                margin: 0,
                color: 'var(--color-text-primary)',
                lineHeight: '1.6'
              }}>
                {viewingFile.content}
              </pre>
            </div>
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: '220px', overflowY: 'auto' }}>
          <ScreenCapture onAnalyzed={() => loadState()} />
          <ActivityLog events={sessionEvents} onRefresh={loadState} />
        </div>
      </div>
    </div>
  );
}
