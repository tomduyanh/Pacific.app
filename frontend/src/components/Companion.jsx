import { useEffect, useRef, useState } from "react";
import { EMOTES, emoteSrc } from "../companionState.js";
import { useDraggableCompanion } from "../useDraggableCompanion.js";

// Warm the whole set once so switching emotes never shows a gap. All ten
// together are ~145 KB, cheaper than a single unoptimised frame was.
let preloaded = false;
function preloadEmotes() {
  if (preloaded || typeof Image === "undefined") return;
  preloaded = true;
  EMOTES.forEach((e) => {
    const img = new Image();
    img.src = emoteSrc(e);
  });
}

/**
 * The assistant's face. `size` is the rendered box in px; the art is 256px so
 * anything up to 128 stays crisp on a 2x display.
 */
export function Companion({ emote, line, size = 56, showLine = true, positionKey }) {
  const [current, setCurrent] = useState(emote);
  const [settling, setSettling] = useState(false);
  const previous = useRef(emote);
  const { bodyRef, position, dragging, handleProps } = useDraggableCompanion(positionKey);

  useEffect(preloadEmotes, []);

  // Re-trigger the entrance animation whenever the expression changes, so a
  // state change reads as the character reacting rather than a silent swap.
  useEffect(() => {
    if (previous.current === emote) return;
    previous.current = emote;
    setCurrent(emote);
    setSettling(true);
    const t = setTimeout(() => setSettling(false), 320);
    return () => clearTimeout(t);
  }, [emote]);

  return (
    <div className="companion" data-emote={current} style={{ minHeight: size }}>
      <div
        ref={bodyRef}
        className={`companion-body ${position ? "is-floating" : ""} ${dragging ? "is-dragging" : ""}`}
        style={position ? { transform: `translate3d(${position.x}px, ${position.y}px, 0)` } : undefined}
      >
        <button
          type="button"
          className="companion-handle"
          aria-label="Move Pacific character"
          title="Drag to move · Arrow keys to reposition · Home to reset"
          {...handleProps}
        >
          <img
            className={`companion-art ${settling ? "is-settling" : ""}`}
            src={emoteSrc(current)}
            width={size}
            height={size}
            alt=""
            draggable="false"
          />
        </button>
        {showLine && line && <p className="companion-line">{line}</p>}
      </div>
    </div>
  );
}
