import { useCallback, useEffect, useState } from "react";
import { emoteSrc } from "../companionState.js";

/**
 * Summons the floating assistant. Only meaningful inside the desktop shell —
 * `window.pacificDesktop` is injected by preload-dashboard.js, so in a plain
 * browser tab this renders nothing rather than a button that can't work.
 */
export function OverlayButton() {
  const bridge = typeof window !== "undefined" ? window.pacificDesktop : null;
  const [visible, setVisible] = useState(null);

  useEffect(() => {
    if (!bridge) return;
    bridge.isOverlayVisible?.().then(setVisible).catch(() => setVisible(null));
  }, [bridge]);

  const toggle = useCallback(async () => {
    if (!bridge) return;
    try {
      if (visible) {
        await bridge.hideOverlay?.();
        setVisible(false);
      } else {
        await bridge.showOverlay?.();
        setVisible(true);
      }
    } catch {
      /* the shell went away; leave the button as-is */
    }
  }, [bridge, visible]);

  if (!bridge) return null;

  return (
    <button
      className="ctx-mock-btn ctx-overlay-btn"
      onClick={toggle}
      title={visible ? "Hide the floating assistant" : "Show the floating assistant on top of your other apps"}
    >
      <img className="ctx-overlay-btn-art" src={emoteSrc("offering")} width="18" height="18" alt="" />
      {visible ? "Hide assistant" : "Open assistant"}
    </button>
  );
}
