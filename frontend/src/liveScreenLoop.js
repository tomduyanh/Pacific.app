// Capture and ranking have independent, single-flight loops. Each capture reads
// the video at send time; while ranking is busy, requests collapse into one
// follow-up pass over the latest server state instead of accumulating a queue.
export function startLiveScreenLoop({
  capture, analyze, rescore, onFrame, onScored, onError,
  intervalMs = 5000,
  now = () => performance.now(),
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  const controller = new AbortController();
  const { signal } = controller;
  let timer;
  let stopped = false;
  let scoring = false;
  // A previous live session may have stopped before its ranking completed.
  let scorePending = true;

  async function requestScores() {
    scorePending = true;
    if (scoring) return;
    scoring = true;
    try {
      while (scorePending && !stopped) {
        scorePending = false;
        const started = now();
        try {
          const state = await rescore({ signal });
          if (!stopped) onScored(state, { elapsedMs: now() - started });
        } catch (error) {
          if (!stopped) {
            scorePending = true;
            onError(error, "ranking");
          }
          break; // Retry on the next frame, without a tight retry loop.
        }
      }
    } finally {
      scoring = false;
    }
  }

  async function tick() {
    if (stopped) return;
    const started = now();
    let retryMs = 0;
    try {
      const frame = capture();
      if (frame) {
        const result = await analyze(frame, { signal });
        if (stopped) return;
        if (result.skipped) {
          retryMs = Math.max(0, Number(result.retry_after_sec) || 0) * 1000;
        } else {
          onFrame(result, { elapsedMs: now() - started });
          if (result.state_changed || scorePending) void requestScores();
        }
      }
    } catch (error) {
      retryMs = intervalMs;
      if (!stopped) onError(error, "vision");
    } finally {
      if (!stopped) {
        timer = setTimer(tick, Math.max(retryMs, intervalMs - (now() - started), 0));
      }
    }
  }

  void tick();
  return () => {
    stopped = true;
    scorePending = false;
    clearTimer(timer);
    controller.abort();
  };
}
