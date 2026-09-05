import assert from "node:assert/strict";
import test from "node:test";
import { startLiveScreenLoop } from "./liveScreenLoop.js";

const flush = () => new Promise((resolve) => setImmediate(resolve));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function harness(overrides = {}) {
  let clock = 0;
  const timers = new Map();
  const frames = [], states = [], errors = [], sent = [];
  const stop = startLiveScreenLoop({
    intervalMs: 5000,
    now: () => clock,
    setTimer: (callback, delay) => {
      const id = Symbol();
      timers.set(id, { callback, at: clock + delay });
      return id;
    },
    clearTimer: (id) => timers.delete(id),
    capture: () => ({ capturedAt: clock }),
    analyze: async (frame) => {
      sent.push(frame);
      return { state_changed: true };
    },
    rescore: async () => ({ pool: [] }),
    onFrame: (frame) => frames.push(frame),
    onScored: (state) => states.push(state),
    onError: (error, phase) => errors.push({ error, phase }),
    ...overrides,
  });
  return {
    frames, states, errors, sent, timers, stop,
    setTime: (time) => { clock = time; },
    next: async () => {
      const [id, timer] = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
      timers.delete(id);
      clock = timer.at;
      timer.callback();
      await flush();
    },
  };
}

test("slow ranking cannot delay fresh captures; ranking requests coalesce", async () => {
  const firstRanking = deferred();
  let rankingCalls = 0;
  const h = harness({ rescore: () => ++rankingCalls === 1 ? firstRanking.promise : Promise.resolve({}) });
  try {
    await flush();
    await h.next();
    await h.next();
    assert.deepEqual(h.sent.map((frame) => frame.capturedAt), [0, 5000, 10000]);
    assert.equal(h.frames.length, 3);
    assert.equal(rankingCalls, 1);
    firstRanking.resolve({});
    await flush();
    assert.equal(rankingCalls, 2); // One latest-state pass, not two queued frames.
  } finally { h.stop(); }
});

test("a slow vision call has no queued frames or extra interval afterward", async () => {
  const vision = deferred();
  const h = harness({ analyze: () => vision.promise });
  try {
    assert.equal(h.timers.size, 0);
    h.setTime(7000);
    vision.resolve({ state_changed: false });
    await flush();
    assert.equal([...h.timers.values()][0].at, 7000);
    assert.equal(h.frames.length, 1);
  } finally { h.stop(); }
});

test("server throttling waits without adding fake commentary", async () => {
  const h = harness({ analyze: async () => ({ skipped: true, retry_after_sec: 8 }) });
  try {
    await flush();
    assert.equal(h.frames.length, 0);
    assert.equal([...h.timers.values()][0].at, 8000);
  } finally { h.stop(); }
});

test("stopping aborts the request and ignores late analysis", async () => {
  const vision = deferred();
  let signal;
  const h = harness({ analyze: (_, options) => { signal = options.signal; return vision.promise; } });
  h.stop();
  assert.equal(signal.aborted, true);
  vision.resolve({ state_changed: true });
  await flush();
  assert.equal(h.frames.length, 0);
  assert.equal(h.states.length, 0);
  assert.equal(h.timers.size, 0);
});

test("stopping ignores late ranking results", async () => {
  const ranking = deferred();
  const h = harness({ rescore: () => ranking.promise });
  await flush();
  h.stop();
  ranking.resolve({});
  await flush();
  assert.equal(h.states.length, 0);
  assert.equal(h.timers.size, 0);
});

test("analysis-only changes still refresh recommendations", async () => {
  const h = harness({ analyze: async () => ({ state_changed: true, applied: false, events: [] }) });
  try {
    await flush();
    assert.equal(h.states.length, 1);
  } finally { h.stop(); }
});

test("restarting live refreshes rankings even when the scene is unchanged", async () => {
  const h = harness({ analyze: async () => ({ state_changed: false }) });
  try {
    await flush();
    assert.equal(h.states.length, 1);
    await h.next();
    assert.equal(h.states.length, 1);
  } finally { h.stop(); }
});

test("failed ranking retries on the next frame even if the scene is unchanged", async () => {
  let frames = 0, rankings = 0;
  const h = harness({
    analyze: async () => ({ state_changed: ++frames === 1 }),
    rescore: async () => {
      if (++rankings === 1) throw new Error("temporary failure");
      return {};
    },
  });
  try {
    await flush();
    assert.equal(h.errors[0].phase, "ranking");
    assert.equal(rankings, 1);
    await h.next();
    assert.equal(rankings, 2);
    assert.equal(h.states.length, 1);
  } finally { h.stop(); }
});
