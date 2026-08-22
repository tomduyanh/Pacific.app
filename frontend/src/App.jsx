import { useState, useEffect, useCallback, useMemo } from "react";
import { api } from "./api.js";
import { CurrentContext } from "./components/CurrentContext.jsx";
import { SuggestedContext } from "./components/SuggestedContext.jsx";
import { RawContextTable } from "./components/RawContextTable.jsx";
import { AttachModal } from "./components/AttachModal.jsx";
import { UploadContextModal } from "./components/UploadContextModal.jsx";
import { KindSquare, KindBadge } from "./components/KindBadge.jsx";
import { ActivityLog } from "./components/ActivityLog.jsx";
import { ScreenCapture } from "./components/ScreenCapture.jsx";
import { Companion } from "./components/Companion.jsx";
import { OverlayButton } from "./components/OverlayButton.jsx";
import { companionState } from "./companionState.js";

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
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState(null);
  const [suggestReason, setSuggestReason] = useState("");
  // Short-lived companion reaction to a direct action ("attaching" -> "done").
  const [transient, setTransient] = useState(null);

  const suggestions = useMemo(() => pool.filter((i) => i.status === "suggested"), [pool]);
  const pct = tokenBudget > 0 ? Math.min(100, Math.round((tokensUsed / tokenBudget) * 100)) : 0;

  // Relevance is shown as a percentile against every scored item in the pool,
  // which is self-normalizing — raw scores are weighted cosine sums and have no
  // meaningful absolute scale to show a user.
  const percentileOf = useMemo(() => {
    const scores = pool.map((i) => i.score ?? 0);
    const scored = scores.filter((s) => s !== 0).length;
    return (score) => {
      if (!scored || !score) return null;
      const below = scores.filter((s) => s < score).length;
      return Math.round((below / Math.max(1, scores.length - 1)) * 100);
    };
  }, [pool]);

  // Every mutating endpoint returns the authoritative state, so one round trip
  // per action replaces the old mutate-then-refetch pair.
  const applyState = useCallback((s) => {
    if (!s) return;
    if (s.pool) setPool(s.pool);
    if (s.attached) setAttached(s.attached);
    if (typeof s.tokens_used === "number") setTokensUsed(s.tokens_used);
    if (typeof s.token_budget === "number") setTokenBudget(s.token_budget);
    if (s.session_events) setSessionEvents(s.session_events);
    if ("suggest_diag" in s) setSuggestReason(s.suggest_diag?.reason || "");
  }, []);

  const loadState = useCallback(async () => {
    try {
      applyState(await api.getState());
      setError(null);
    } catch {
      setError("Failed to connect to backend. Is the server running?");
    }
  }, [applyState]);

  useEffect(() => {
    loadState();
  }, [loadState]);

  // Paint the expected result immediately, then reconcile with the server's
  // response. A failure falls back to a full refetch, which un-does the guess.
  const runAction = useCallback(
    async (optimistic, call, failMessage) => {
      optimistic?.();
      try {
        applyState(await call());
      } catch {
        setError(failMessage);
        loadState();
      }
    },
    [applyState, loadState]
  );

  const handleAttach = useCallback(
    (id) => {
      const item = pool.find((i) => i.id === id);
      setTransient("attaching");
      return runAction(
        () => {
          setPool((p) => p.map((i) => (i.id === id ? { ...i, status: "active" } : i)));
          if (item) {
            setAttached((a) => (a.some((x) => x.id === id) ? a : [...a, { ...item, status: "active" }]));
            setTokensUsed((t) => t + Math.floor((item.size_bytes || 0) / 4));
          }
        },
        () => api.attach(id),
        "Attach failed."
      ).then(() => setTransient("done"));
    },
    [pool, runAction]
  );

  const handleDetach = useCallback(
    (id) => {
      const item = attached.find((i) => i.id === id);
      return runAction(
        () => {
          setPool((p) => p.map((i) => (i.id === id ? { ...i, status: "idle" } : i)));
          setAttached((a) => a.filter((x) => x.id !== id));
          if (item) setTokensUsed((t) => Math.max(0, t - Math.floor((item.size_bytes || 0) / 4)));
        },
        () => api.detach(id),
        "Detach failed."
      );
    },
    [attached, runAction]
  );

  const handleDismiss = useCallback(
    (id) =>
      runAction(
        () => setPool((p) => p.map((i) => (i.id === id ? { ...i, status: "idle" } : i))),
        () => api.dismiss(id),
        "Dismiss failed."
      ),
    [runAction]
  );

  useEffect(() => {
    if (!transient) return undefined;
    const ms = transient === "done" ? 2200 : 6000;   // "attaching" is a safety net
    const timer = setTimeout(() => setTransient(null), ms);
    return () => clearTimeout(timer);
  }, [transient]);

  const companion = companionState({
    scoring,
    transient,
    suggestions,
    topPercentile: suggestions.length ? percentileOf(suggestions[0].score) : null,
    attachedCount: attached.length,
    sessionActive: sessionEvents.length > 0 || attached.length > 0,
    suggestReason,
  });

  const runScoring = useCallback(
    async (call, failMessage) => {
      setScoring(true);
      try {
        applyState(await call());
        setError(null);
      } catch {
        setError(failMessage);
      } finally {
        setScoring(false);
      }
    },
    [applyState]
  );

  const handleSendMessage = () => {
    const text = message.trim();
    if (!text) return;
    setMessage("");
    return runScoring(() => api.postMessage(text), "Rescore failed.");
  };

  const handleRefresh = () => runScoring(() => api.rescore(), "Refresh failed.");

  const handleClearSession = () =>
    runScoring(async () => {
      const res = await api.clearSession();
      setViewingFile(null);
      return res;
    }, "Clear session failed.");

  return (
    <div className="layout-main">
      <div className="ctx-app">
        <div className="ctx-top">
          <div className="ctx-top-left">
            <h2 className="ctx-title">Context dashboard</h2>
            <div className="ctx-toolbar">
              <button
                className="ctx-mock-btn"
                onClick={handleClearSession}
                disabled={scoring}
                title="Reset all session events, history, and scores"
              >
                Clear session
              </button>
              <button
                className="ctx-mock-btn"
                onClick={() => setShowUploadModal(true)}
                title="Upload a new context block to the pool"
              >
                + Upload context
              </button>
              <OverlayButton />
            </div>
          </div>
          <Companion emote={companion.emote} line={companion.line} size={64} positionKey="pacific.companion.position" />
          <div className="ctx-meter">
            <div className="ctx-meter-label">Context loaded</div>
            <div className="ctx-meter-val">
              {tokensUsed.toLocaleString()} / {tokenBudget.toLocaleString()} tokens
            </div>
            <div className="ctx-meter-bar">
              <div className={`ctx-meter-fill ${pct > 80 ? "is-over" : ""}`} style={{ width: `${pct}%` }} />
            </div>
          </div>
        </div>

        {error && (
          <div className="ctx-error" role="alert">
            <span>{error}</span>
            <button onClick={() => setError(null)} aria-label="Dismiss error">
              ×
            </button>
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
          loading={scoring}
          onItemClick={setViewingFile}
          percentileOf={percentileOf}
          suggestReason={suggestReason}
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
          <button className="ctx-controls-btn" onClick={handleSendMessage} disabled={scoring || !message.trim()}>
            {scoring ? "Scoring…" : "Rescore Context"}
          </button>
        </div>
      </div>

      {showAttachModal && (
        <AttachModal pool={pool} onAttach={handleAttach} onClose={() => setShowAttachModal(false)} />
      )}

      {showUploadModal && (
        <UploadContextModal onClose={() => setShowUploadModal(false)} onUploaded={loadState} />
      )}

      <div className="ctx-side-panel">
        {viewingFile && (
          <div className="ctx-viewer">
            <div className="ctx-side-panel-header ctx-viewer-header">
              <div className="ctx-side-panel-title">
                <KindSquare kind={viewingFile.kind} />
                <span className="ctx-viewer-name">{viewingFile.display_name}</span>
              </div>
              <button onClick={() => setViewingFile(null)} className="modal-close" aria-label="Close preview">
                ×
              </button>
            </div>
            <div className="ctx-side-panel-content">
              <div className="ctx-viewer-meta">
                <KindBadge kind={viewingFile.kind} />
                <span className="ctx-viewer-desc">{viewingFile.description}</span>
              </div>
              <pre className="ctx-viewer-body">{viewingFile.content}</pre>
            </div>
          </div>
        )}
        <div className="ctx-side-stack">
          <ScreenCapture onAnalyzed={loadState} onState={applyState} />
          <ActivityLog events={sessionEvents} onRefresh={loadState} />
        </div>
      </div>
    </div>
  );
}
