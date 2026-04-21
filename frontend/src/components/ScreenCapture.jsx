import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const MAX_WIDTH = 1280;
const JPEG_QUALITY = 0.82;
const LIVE_INTERVAL_MS = 5000;

function frameToJpegBase64(video) {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return null;
  const scale = vw > MAX_WIDTH ? MAX_WIDTH / vw : 1;
  const w = Math.round(vw * scale);
  const h = Math.round(vh * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(video, 0, 0, w, h);
  const dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  return { base64: dataUrl.split(",")[1] || "", mime_type: "image/jpeg" };
}

export function ScreenCapture({ onAnalyzed }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const tickBusyRef = useRef(false);
  const [sharing, setSharing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState(null);
  const [liveOn, setLiveOn] = useState(false);
  const [commentary, setCommentary] = useState([]);

  const stopShare = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setSharing(false);
    setLiveOn(false);
    setCommentary([]);
  }, []);

  const startShare = async () => {
    setHint(null);
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: { ideal: 4, max: 30 } },
        audio: false,
      });
      streamRef.current = stream;
      stream.getVideoTracks()[0]?.addEventListener("ended", stopShare);
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setSharing(true);
    } catch (e) {
      setHint("Screen share was cancelled or not allowed.");
    }
  };

  const captureAndAnalyze = async () => {
    const video = videoRef.current;
    if (!video || !sharing) {
      setHint("Start screen share first.");
      return;
    }
    setBusy(true);
    setHint(null);
    try {
      const shot = frameToJpegBase64(video);
      if (!shot?.base64) {
        setHint("Could not read video frame yet — wait a second and try again.");
        return;
      }
      const res = await api.analyzeScreen({
        image_base64: shot.base64,
        mime_type: shot.mime_type,
        apply: true,
      });
      if (onAnalyzed) onAnalyzed(res);
      setHint(
        res.events?.length
          ? `Recorded ${res.events.length} action(s) from screen.`
          : "Model returned no actions (try a clearer frame)."
      );
    } catch (e) {
      setHint(e?.message || "Screen analyze failed. Is GEMINI_API_KEY set on the server?");
    } finally {
      setBusy(false);
    }
  };

  const runLiveTick = useCallback(async () => {
    const video = videoRef.current;
    if (!video || !sharing || tickBusyRef.current) return;
    const shot = frameToJpegBase64(video);
    if (!shot?.base64) return;

    tickBusyRef.current = true;
    try {
      const res = await api.liveScreenTick({
        image_base64: shot.base64,
        mime_type: shot.mime_type,
        apply: true,
      });
      const text =
        res.live_commentary ||
        res.commentary ||
        "[tick] (empty response)";
      const line = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        text,
        ts: new Date().toLocaleTimeString(),
      };
      setCommentary((c) => [line, ...c].slice(0, 50));
      if (onAnalyzed && res.applied) onAnalyzed(res);
    } catch (e) {
      if (e instanceof TypeError) {
        setLiveOn(false);
        setHint("Backend offline — live stopped.");
      } else {
        setHint(e?.message || "Live screen tick failed.");
      }
    } finally {
      tickBusyRef.current = false;
    }
  }, [sharing, onAnalyzed]);

  useEffect(() => {
    if (!liveOn || !sharing) return undefined;
    const id = window.setInterval(() => {
      void runLiveTick();
    }, LIVE_INTERVAL_MS);
    void runLiveTick();
    return () => window.clearInterval(id);
  }, [liveOn, sharing, runLiveTick]);

  return (
    <div className="screen-capture-panel">
      <div className="activity-log-header" style={{ marginBottom: "8px" }}>
        <h3 className="activity-log-title">Screen → VLM → FileGram</h3>
      </div>
      <p className="screen-capture-help">
        One-shot capture maps a frame to session events. <strong>Live</strong> sends frames on a timer; the VLM
        is instructed to treat visible text/code/terminal changes as meaningful even when layout is stable.
        Live ticks always send the frame to the server (no coarse pixel prefilter—letterboxed captures made that
        unreliable for scroll and typing).
      </p>
      <video ref={videoRef} className="screen-capture-video" playsInline muted />
      <div className="activity-mock-actions" style={{ marginTop: "10px", flexWrap: "wrap" }}>
        {!sharing ? (
          <button type="button" className="ctx-mock-btn" onClick={startShare} disabled={busy}>
            Share screen
          </button>
        ) : (
          <>
            <button type="button" className="ctx-mock-btn" onClick={captureAndAnalyze} disabled={busy || liveOn}>
              {busy ? "Analyzing…" : "One-shot capture"}
            </button>
            <button
              type="button"
              className={`ctx-mock-btn ${liveOn ? "ctx-mock-btn-live" : ""}`}
              onClick={() => {
                setLiveOn((v) => {
                  const next = !v;
                  if (!next) setCommentary([]);
                  return next;
                });
                setHint(null);
              }}
              disabled={busy}
            >
              {liveOn ? "Stop live" : "Start live"}
            </button>
            <button type="button" className="ctx-mock-btn" onClick={stopShare} disabled={busy}>
              Stop share
            </button>
          </>
        )}
      </div>
      {liveOn && sharing && (
        <div className="screen-capture-live-hint">
          Live: ~{Math.round(LIVE_INTERVAL_MS / 100) / 10}s cadence (≤12 RPM, Gemini Flash free tier limit is 15 RPM) · server rate limit + VLM novelty gate
        </div>
      )}
      {liveOn && sharing && (
        <div className="screen-capture-commentary">
          <div className="screen-capture-commentary-title">Live commentary</div>
          {commentary.length === 0 ? (
            <div className="screen-capture-commentary-empty">Waiting for first tick…</div>
          ) : (
            <ul className="screen-capture-commentary-list">
              {commentary.map((row) => (
                <li key={row.id}>
                  <span className="screen-capture-commentary-ts">{row.ts}</span>
                  {row.text}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {hint && <div className="screen-capture-hint">{hint}</div>}
    </div>
  );
}
