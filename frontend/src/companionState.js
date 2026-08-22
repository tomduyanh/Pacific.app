/**
 * Maps what Pacific currently knows into one of the character's ten emotes.
 *
 * The character is the assistant, so its expression has to be *earned* by real
 * state — never decorative. Two rules keep it honest:
 *
 *   - It only looks confident ("found") when the top suggestion genuinely
 *     outranks the pool, using the same percentile the card shows.
 *   - When scoring can't differentiate, it shrugs ("empty") rather than
 *     presenting three arbitrary documents with a smile.
 *
 * Kept free of React so the Electron overlay can import the same logic.
 */

export const EMOTES = [
  "idle", "watching", "searching", "offering", "presenting",
  "found", "attaching", "done", "connected", "empty",
];

export const emoteSrc = (emote, base = "") => `${base}/character/${emote}.webp`;

const STRONG_MATCH_PERCENTILE = 90;
const WELL_STOCKED = 3;

export function companionState({
  scoring = false,
  transient = null,
  suggestions = [],
  topPercentile = null,
  attachedCount = 0,
  sessionActive = false,
  suggestReason = "",
} = {}) {
  // Transient beats everything: the user just did something and deserves to
  // see it land.
  if (transient === "attaching") {
    return { emote: "attaching", line: "Clipping that in…" };
  }
  if (transient === "done") {
    return { emote: "done", line: "Added — I'll keep it in mind." };
  }

  if (scoring) {
    return { emote: "searching", line: "Reading the room…" };
  }

  if (suggestions.length > 0) {
    if (topPercentile !== null && topPercentile >= STRONG_MATCH_PERCENTILE) {
      return { emote: "found", line: "This one looks like a strong match." };
    }
    if (suggestions.length === 1) {
      return { emote: "offering", line: "One thing might help here." };
    }
    return {
      emote: "presenting",
      line: `${suggestions.length} things might help here.`,
    };
  }

  // No suggestions is a real answer, not a failure — say so plainly.
  if (suggestReason === "no_clear_signal") {
    return {
      emote: "empty",
      line: "Nothing stands out yet — tell me what you're working on.",
    };
  }

  if (attachedCount >= WELL_STOCKED) {
    return {
      emote: "connected",
      line: `Holding ${attachedCount} pieces of context for you.`,
    };
  }
  if (sessionActive) {
    return { emote: "watching", line: "Following along." };
  }
  return { emote: "idle", line: "Here when you need me." };
}
