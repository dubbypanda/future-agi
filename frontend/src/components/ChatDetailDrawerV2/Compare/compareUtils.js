// Pure helpers for the chat baseline-vs-replay compare view.
//
// Logic is lifted from the legacy
// `frontend/src/sections/test-detail/TestDetailDrawer/BasLineCompare/CompareConversation.jsx`
// (lines ~35-84 + the totals loop) and made theme-/role-agnostic so the
// new chat compare components can reuse it without depending on the
// legacy file. The legacy version stays in place — voice compare still
// uses its own copy — so this extraction has no side effects.
//
// Exports:
//   - `computeDiff(textA, textB, side?)` — word-level diff between two
//     strings using `diff.diffWordsWithSpace`. When `side` is "A" or "B"
//     the diff is filtered + merged so the caller can render one side
//     of the diff inline without iterating over removed-then-added
//     pairs.
//   - `countDiffs(matchedConversations)` — running totals of removals
//     and additions across every paired turn, used to populate the
//     "Removals (N) / Additions (N)" pill chips when Show Diff is on.

import { diffWordsWithSpace } from "diff";

/**
 * Word-level diff between two strings. Pass `side="A"` to retain only
 * the unchanged + removed parts (baseline column) or `side="B"` for
 * unchanged + added parts (replay column). Adjacent same-type parts
 * are merged so the render walks the smallest possible list.
 */
export const computeDiff = (textA, textB, side = null) => {
  if (!textA && !textB) return [];
  if (!textA) return [{ value: textB, added: true }];
  if (!textB) return [{ value: textA, removed: true }];

  const diff = diffWordsWithSpace(textA, textB);
  if (!side) return diff;

  const targetType = side === "A" ? "removed" : "added";
  const filtered = diff.filter((part) =>
    side === "A" ? !part.added : !part.removed,
  );

  // Merge adjacent same-type parts and stitch whitespace into a flanking
  // diff token of the target type so the highlighted run renders as one
  // contiguous span instead of breaking at every whitespace boundary.
  const merged = [];
  for (let i = 0; i < filtered.length; i++) {
    const current = filtered[i];
    const prev = merged[merged.length - 1];

    if (
      prev &&
      prev.added === current.added &&
      prev.removed === current.removed
    ) {
      prev.value += current.value;
      continue;
    }

    if (
      /^\s+$/.test(current.value) &&
      !current.added &&
      !current.removed &&
      prev?.[targetType]
    ) {
      const nextNonWhitespace = filtered
        .slice(i + 1)
        .find((p) => !/^\s+$/.test(p.value));
      if (nextNonWhitespace?.[targetType]) {
        prev.value += current.value;
        continue;
      }
    }

    merged.push({ ...current });
  }

  return merged;
};

/**
 * Count total removals / additions across an already-matched
 * conversation list (the shape `matchedConversations` from
 * `ChatCompareTranscript`: `[{ baseline, replayed }, …]`).
 */
export const countDiffs = (matchedConversations) => {
  let removals = 0;
  let additions = 0;

  for (const match of matchedConversations) {
    const baselineContent = match.baseline?.content || "";
    const replayedContent = match.replayed?.content || "";
    if (!baselineContent && !replayedContent) continue;

    const diffA = computeDiff(baselineContent, replayedContent, "A");
    const diffB = computeDiff(baselineContent, replayedContent, "B");
    for (const part of diffA) if (part.removed) removals++;
    for (const part of diffB) if (part.added) additions++;
  }

  return { removalsCount: removals, additionsCount: additions };
};

/**
 * Pair baseline + replay turns by index so the side-by-side view can
 * render them in lock-step. Missing turns on either side become `null`.
 *
 * @param {{ conversations: Array<object> }} baselineSession
 * @param {{ conversations: Array<object> }} replayedSession
 */
export const matchConversationsByIndex = (baselineSession, replayedSession) => {
  const baseline = baselineSession?.conversations || [];
  const replayed = replayedSession?.conversations || [];
  const maxLength = Math.max(baseline.length, replayed.length);
  const matched = [];
  for (let i = 0; i < maxLength; i++) {
    matched.push({
      baseline: baseline[i] || null,
      replayed: replayed[i] || null,
    });
  }
  return matched;
};
