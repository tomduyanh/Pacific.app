import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { startLiveScreenLoop } from "../liveScreenLoop.js";

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

export function ScreenCapture({ onAnalyzed, onState }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [sharing, setSharing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState(null);
  const [liveOn, setLiveOn] = useState(false);
  const [commentary, setCommentary] = useState([]);
  const [timing, setTiming] = useState(null);
  const stopLiveRef = useRef(null);

  const stopShare = useCallback(() => {
    stopLiveRef.current?.();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setSharing(false);
    setLiveOn(false);
    setCommentary([]);
    setTiming(null);
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

  useEffect(() => {
    if (!liveOn || !sharing) return undefined;
    const stop = startLiveScreenLoop({
      intervalMs: LIVE_INTERVAL_MS,
      capture: () => {
        const shot = videoRef.current && frameToJpegBase64(videoRef.current);
        return shot?.base64 ? shot : null;
      },
      analyze: (shot, options) => api.liveScreenTick({
        image_base64: shot.base64,
        mime_type: shot.mime_type,
        apply: true,
        rescore: false,
      }, options),
      rescore: api.rescore,
      onFrame: (res, { elapsedMs }) => {
        setHint(null);
        setTiming((t) => ({ ...t, vision: elapsedMs }));
        setCommentary((c) => [{
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          text: res.live_commentary || res.commentary || "No activity detected.",
          ts: new Date().toLocaleTimeString(),
        }, ...c].slice(0, 50));
      },
      onScored: (state, { elapsedMs }) => {
        setTiming((t) => ({ ...t, ranking: elapsedMs }));
        onState?.(state);
      },
      onError: (error, phase) => {
        if (error.name === "AbortError") return;
        if (error instanceof TypeError) {
          setLiveOn(false);
          setHint("Backend offline — live stopped.");
        } else {
          setHint(`${phase === "vision" ? "Screen analysis" : "Recommendations"} failed. Retrying with the latest screen.`);
        }
      },
    });
    stopLiveRef.current = stop;
    return stop;
  }, [liveOn, sharing, onState]);

  useEffect(() => () => {
    stopLiveRef.current?.();
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  return (
    <div className="screen-capture-panel">
      <div className="activity-log-header" style={{ marginBottom: "8px" }}>
        <h3 className="activity-log-title">Screen → VLM → FileGram</h3>
      </div>
      <p className="screen-capture-help">
        Share the screen you’re working on to get relevant context. <strong>Live</strong> follows your
        activity and refreshes recommendations as you work.
      </p>
      <video ref={videoRef} className="screen-capture-video" playsInline muted />
      <div className="activity-mock-actions">
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
                if (liveOn) {
                  stopLiveRef.current?.();
                  setCommentary([]);
                } else {
                  setTiming(null);
                }
                setLiveOn(!liveOn);
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
          Checking the latest screen about every {LIVE_INTERVAL_MS / 1000}s; slower analyses may take longer.
          {timing && ` Last screen update: ${(timing.vision / 1000).toFixed(1)}s${timing.ranking != null ? ` · Recommendations: ${(timing.ranking / 1000).toFixed(1)}s` : ""}.`}
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
