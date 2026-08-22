import { useLayoutEffect, useRef, useState } from "react";

export function useDraggableCompanion(storageKey) {
  const bodyRef = useRef(null);
  const dragRef = useRef(null);
  const [position, setPosition] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey));
      return storageKey && Number.isFinite(saved?.x) && Number.isFinite(saved?.y) ? saved : null;
    } catch { return null; }
  });
  const positionRef = useRef(position);
  const [dragging, setDragging] = useState(false);

  function place(next, persist = false) {
    if (next) {
      const rect = bodyRef.current.getBoundingClientRect();
      next = {
        x: Math.max(8, Math.min(next.x, window.innerWidth - rect.width - 8)),
        y: Math.max(8, Math.min(next.y, window.innerHeight - rect.height - 8)),
      };
    }
    positionRef.current = next;
    setPosition((old) => old?.x === next?.x && old?.y === next?.y ? old : next);
    if (persist && storageKey) {
      try {
        if (next) localStorage.setItem(storageKey, JSON.stringify(next));
        else localStorage.removeItem(storageKey);
      } catch { /* Moving still works when browser storage is unavailable. */ }
    }
  }

  useLayoutEffect(() => {
    const keepInView = () => {
      if (positionRef.current) place(positionRef.current, true);
    };
    keepInView();
    const observer = new ResizeObserver(keepInView);
    observer.observe(bodyRef.current);
    window.addEventListener("resize", keepInView);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", keepInView);
    };
  }, [storageKey]);

  function finish(event, cancel = false) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setDragging(false);
    if (drag.moved) place(cancel ? drag.origin : positionRef.current, true);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return {
    bodyRef,
    dragging,
    position,
    handleProps: {
      onPointerDown(event) {
        if (!event.isPrimary || event.button !== 0) return;
        event.preventDefault();
        event.currentTarget.focus({ preventScroll: true });
        const rect = bodyRef.current.getBoundingClientRect();
        dragRef.current = {
          pointerId: event.pointerId,
          startX: event.clientX, startY: event.clientY,
          offsetX: event.clientX - rect.left, offsetY: event.clientY - rect.top,
          origin: positionRef.current,
          moved: false,
        };
        event.currentTarget.setPointerCapture(event.pointerId);
      },
      onPointerMove(event) {
        const drag = dragRef.current;
        if (!drag || event.pointerId !== drag.pointerId) return;
        if (!drag.moved && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < 4) return;
        drag.moved = true;
        setDragging(true);
        place({ x: event.clientX - drag.offsetX, y: event.clientY - drag.offsetY });
      },
      onPointerUp: (event) => finish(event),
      onPointerCancel: (event) => finish(event, true),
      onLostPointerCapture: (event) => finish(event),
      onKeyDown(event) {
        if (event.key === "Escape" && dragRef.current) {
          finish({ currentTarget: event.currentTarget, pointerId: dragRef.current.pointerId }, true);
          event.preventDefault();
          return;
        }
        if (event.key === "Home") {
          event.preventDefault();
          if (dragRef.current) {
            finish({ currentTarget: event.currentTarget, pointerId: dragRef.current.pointerId }, true);
          }
          place(null, true);
          return;
        }
        const direction = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
        if (!direction || dragRef.current) return;
        event.preventDefault();
        const rect = bodyRef.current.getBoundingClientRect();
        const step = event.shiftKey ? 32 : 8;
        place({ x: rect.left + direction[0] * step, y: rect.top + direction[1] * step }, true);
      },
    },
  };
}
