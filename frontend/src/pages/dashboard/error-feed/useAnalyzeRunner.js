import { useCallback, useEffect, useRef } from "react";
import { useErrorFeedStore } from "./store";

// Mock run sequence — replace once BE streams real sub-agent steps.
// Lives in this hook (not the AnalyzeTab component) so a run can be
// kicked off and continue progressing even when the user is not on
// the Analyze tab. ClusterHeadlineCard observes the same thread state
// from the store, so the two views stay in lockstep.
// Each step carries a collapsed `detail` one-liner plus an expandable
// `details` block (the agent's reasoning + the data/tools it looked at) —
// rendered like Claude Code's expandable tool/thinking blocks.
const RUN_STEPS = [
  {
    title: "Sampling representative calls",
    detail: "Picked 3 traces · centroid · outlier · p95 latency",
    chips: ["centroid", "outlier", "p95"],
    runDelayMs: 600,
    doneDelayMs: 800,
    details: [
      {
        kind: "reasoning",
        text: "To keep this cheap and representative, I sampled three traces that span the cluster's behaviour instead of reading all 32 — the most typical failure, the most divergent one, and the slowest.",
      },
      {
        kind: "tool",
        name: "sample_cluster_traces",
        input: "cluster_id, strategy=[centroid, outlier, p95_latency]",
        output: "3 traces selected",
      },
      {
        kind: "list",
        title: "Sampled traces",
        items: [
          "04ad94ec · centroid · most typical · eval 0.50",
          "c308e2c3 · outlier · most divergent embedding · eval 0.31",
          "78c2e5ff · p95 latency · slowest call · 4.4s",
        ],
      },
      {
        kind: "reasoning",
        text: "All three are failures on the same pii_task eval config, so the cluster is cohesive — not a mix of unrelated issues.",
      },
    ],
  },
  {
    title: "Reading conversation transcripts",
    detail: "Average prompt drift in turn 2; ~700-token system prompt steady.",
    chips: [],
    runDelayMs: 500,
    doneDelayMs: 700,
    details: [
      {
        kind: "reasoning",
        text: "I read each sampled transcript turn-by-turn, watching for where the agent's behaviour diverged from the user's intent.",
      },
      {
        kind: "list",
        title: "Turn-by-turn observations",
        items: [
          "Turn 1 — user supplies the user_id and the field they want fetched.",
          "Turn 2 — agent re-requests the user_id it was already given (context dropped).",
          "Turn 3 — agent proceeds on a guessed value, returning the wrong record.",
        ],
      },
      {
        kind: "reasoning",
        text: "The system prompt is steady at ~700 tokens across all three traces, so the drift is behavioural — not a token-budget truncation.",
      },
    ],
  },
  {
    title: "Comparing against nearest passing call",
    detail:
      "Passing trace re-states user inputs before tool dispatch; failing traces skip.",
    chips: ["KNN match · cos 0.12"],
    runDelayMs: 700,
    doneDelayMs: 900,
    details: [
      {
        kind: "reasoning",
        text: "I pulled the nearest passing trace by embedding distance and diffed the two execution paths to isolate exactly what differs.",
      },
      {
        kind: "tool",
        name: "knn_passing_match",
        input: "cluster_id, root_input_embedding",
        output: "trace 9f3a · cosine 0.12 · eval 1.00",
      },
      {
        kind: "list",
        title: "Execution-path diff (failing → passing)",
        items: [
          "Passing re-states the user's inputs in a system turn before the tool call.",
          "Failing skips that restate → the tool runs without the prior-turn context.",
          "Tools available, model, and temperature are identical between the two.",
        ],
      },
    ],
  },
  {
    title: "Checking deploy timeline",
    detail: "First seen 4d after v2.4.1 (prompt rev). No matching infra event.",
    chips: ["v2.4.1"],
    runDelayMs: 600,
    doneDelayMs: 700,
    details: [
      {
        kind: "reasoning",
        text: "I correlated the cluster's first-seen timestamp against the deploy and prompt-revision history.",
      },
      {
        kind: "list",
        title: "Timeline",
        items: [
          "May 18 — v2.4.0 shipped (no change to this flow).",
          "May 22 14:02 — v2.4.1 prompt revision, system prompt shortened ~120 tokens.",
          "May 22 — cluster first seen; failures sustained for ~4 days after.",
        ],
      },
      {
        kind: "reasoning",
        text: "No infra/deploy event lines up — the regression tracks the prompt revision, not an infrastructure change.",
      },
    ],
  },
  {
    title: "Synthesizing",
    detail: "Drafting the cluster-level summary.",
    chips: [],
    runDelayMs: 500,
    doneDelayMs: 1200,
    details: [
      {
        kind: "reasoning",
        text: "Combining the findings: v2.4.1 dropped the line that restated user-supplied inputs, so the agent loses context across turns and re-asks for data it already has.",
      },
      {
        kind: "reasoning",
        text: "The fix is prompt-side and low-risk — restore the restate guard before tool dispatch. Confidence is high because the passing/failing diff isolates this single difference.",
      },
    ],
  },
];

function makeStepMessage(idx) {
  const step = RUN_STEPS[idx];
  return {
    id: `step-${Date.now()}-${idx}`,
    type: "step",
    status: "queued",
    title: step.title,
    detail: step.detail,
    chips: step.chips,
    details: step.details,
  };
}

function buildSynthesis(error) {
  const name = error?.error?.name ?? "this cluster";
  const count = error?.traceCount?.toLocaleString() ?? "—";
  return {
    id: `synth-${Date.now()}`,
    type: "synthesis",
    headline:
      `${name} occurs when the agent drops critical user context across turns. ` +
      `The model re-asks for already-provided inputs in ~31% of the ${count} affected traces.`,
    fix: "Add a one-line guard in the system prompt restating already-supplied user inputs before each tool dispatch.",
    confidence: "H",
    category: "fix in prompt",
  };
}

// ── Follow-up sub-agent templates ────────────────────────────────────────────
// Loose intent matching on the user's question → pick a template. Each
// template carries an intro line, a list of sub-agent steps (streamed one by
// one), the final answer, and suggestion chips for the next round.
//
// Replace with a real BE-driven sub-agent invocation once that endpoint
// lands; the message shape (`assistant_intro` + `subagent` + `suggestions`)
// is what the UI renders against, so the swap should be transparent.
const TRACE_ID_RE = /\b([0-9a-f]{6,8})\b/i;
const SHORT_DELAY = { runDelayMs: 500, doneDelayMs: 700 };
const MED_DELAY = { runDelayMs: 500, doneDelayMs: 850 };

function pickFollowUpTemplate(question, error) {
  const q = String(question).toLowerCase();
  const traceMatch = String(question).match(TRACE_ID_RE);

  if (
    traceMatch ||
    /this (trace|call|one)|different|differently|specific/.test(q)
  ) {
    const tid = (traceMatch?.[1] ?? "c99840e6").toLowerCase();
    return {
      intro: "Let me look at that specific call.",
      subagent: { title: "Per-trace investigator", traceShortId: tid },
      steps: [
        {
          title: `Read spans for ${tid}`,
          detail: "12 spans · 3 tool calls · 2 LLM turns · finish_reason=length",
          ...SHORT_DELAY,
          details: [
            {
              kind: "tool",
              name: "fetch_trace_spans",
              input: `trace_id=${tid}`,
              output:
                "12 spans · final span = llm.gpt-4o-mini · finish_reason=length",
            },
          ],
        },
        {
          title: "Compared with cluster's centroid call (9f3a)",
          detail:
            "Input length 4 sentences vs centroid 2 — token budget hit earlier.",
          ...SHORT_DELAY,
          details: [
            {
              kind: "reasoning",
              text:
                "Same prompt, same model, same temperature. The only material " +
                "difference is the customer's question length — this trace got " +
                "4 sentences of input where the centroid had 2. With the same " +
                "1024-token output budget, the agent runs out of room sooner.",
            },
          ],
        },
        {
          title: "Synthesising what's unique about this call",
          detail: "Same root cause; amplified by input length.",
          ...MED_DELAY,
          details: [],
        },
      ],
      answer:
        `This call hit the truncation earlier than most — the customer asked ` +
        `a longer question (4 sentences), so the agent's reply ran out of ` +
        `token budget faster. Same root cause as the cluster, just amplified ` +
        `by input length. **Fix is identical.**`,
      suggestions: [
        "why is gpt-4o-2024-08-06 not affected?",
        "show me an unaffected call",
        "how do I roll back to v23?",
      ],
    };
  }

  if (/gpt-?4o|model|version|not affected|2024-08-06/.test(q)) {
    return {
      intro: "Checking model-version coverage across the cluster.",
      subagent: { title: "Model-version comparator" },
      steps: [
        {
          title: "Grouped affected traces by model version",
          detail: "100% on gpt-4o-mini (default) · 0% on gpt-4o-2024-08-06.",
          ...SHORT_DELAY,
          details: [
            {
              kind: "tool",
              name: "group_by_model",
              input: "cluster_id, dimension=model_version",
              output:
                "gpt-4o-mini: 20/20 fail · gpt-4o-2024-08-06: 0/0 (no traces)",
            },
          ],
        },
        {
          title: "Read system-prompt handling notes for both",
          detail:
            "gpt-4o-2024-08-06 hard-coerces structured output even without " +
            "an explicit schema example; mini doesn't.",
          ...MED_DELAY,
          details: [
            {
              kind: "reasoning",
              text:
                "The dropped schema example only matters for models that don't " +
                "have aggressive structured-output coercion built in. The " +
                "2024-08-06 version of gpt-4o keeps JSON-mode-style behaviour " +
                "even without the example, so the regression doesn't reproduce.",
            },
          ],
        },
      ],
      answer:
        `**gpt-4o-2024-08-06 enforces structured output by default**, so it ` +
        `survives even without the JSON schema example in the system prompt. ` +
        `gpt-4o-mini drops the schema and plain-texts the reply, which then ` +
        `hits the length cap. Pinning to gpt-4o-2024-08-06 (or restoring the ` +
        `schema example) both unblock the fix.`,
      suggestions: [
        "what's the cost difference if we pin to gpt-4o-2024-08-06?",
        "are there other clusters with the same drift?",
        "show me an unaffected call",
      ],
    };
  }

  if (/unaffected|passing|good|working|baseline|example/.test(q)) {
    return {
      intro: "Pulling a representative passing call.",
      subagent: {
        title: "Working-trace fetcher",
        traceShortId: "9f3a47c2",
      },
      steps: [
        {
          title: "Selected nearest passing trace by embedding distance",
          detail: "trace 9f3a47c2 · cosine 0.12 · eval 1.00",
          ...SHORT_DELAY,
          details: [
            {
              kind: "tool",
              name: "knn_passing_match",
              input: "cluster_id, embedding_strategy=root_input",
              output: "1 match · trace 9f3a47c2 · cos 0.12 · eval 1.00",
            },
          ],
        },
        {
          title: "Diffed turn structure vs failing centroid",
          detail:
            "Passing call restates inputs before tool dispatch; failing centroid skips.",
          ...MED_DELAY,
          details: [
            {
              kind: "list",
              title: "Turn-by-turn diff",
              items: [
                "Turn 1 — identical user prompt across both",
                "Turn 2 — passing reasserts the user's inputs; failing skips",
                "Turn 3 — passing dispatches the tool with full context; failing guesses",
              ],
            },
          ],
        },
      ],
      answer:
        `Trace **9f3a47c2** is a clean passing call on the same task config. ` +
        `It restates the user's inputs in turn 2 before any tool dispatch — ` +
        `the line that v24's prompt revision dropped. Open the trace to see ` +
        `it side-by-side with the failing centroid.`,
      suggestions: [
        "open this trace in the Traces tab",
        "why is gpt-4o-2024-08-06 not affected?",
        "what's the smallest fix that ships today?",
      ],
    };
  }

  if (/roll ?back|revert|v23|previous prompt|undo/.test(q)) {
    return {
      intro: "Rolling back v24 → v23 is straightforward — here's the plan.",
      subagent: { title: "Rollback advisor" },
      steps: [
        {
          title: "Located the prompt revision in your prompt-store",
          detail: "v23 last shipped May 18 14:02 UTC. Currently archived.",
          ...SHORT_DELAY,
          details: [
            {
              kind: "tool",
              name: "fetch_prompt_revision",
              input: "name=turn_taking_and_flow, version=23",
              output: "revision found · 717 tokens · archived May 22",
            },
          ],
        },
        {
          title: "Checked downstream consumers for breakage",
          detail: "No other workflows pin v24 specifically — safe to flip.",
          ...MED_DELAY,
          details: [],
        },
      ],
      answer:
        `**Safe to roll back.** No downstream consumers pin v24 specifically.\n\n` +
        `**Option 1 · Quick (1 min)** — flip the prompt alias ` +
        `\`turn_taking_and_flow.current\` back to v23 in the prompt-store UI. ` +
        `Takes effect on the next deploy.\n\n` +
        `**Option 2 · Surgical (5 min)** — keep v24 but restore the dropped ` +
        `\`{response_schema}\` example in the system prompt. Same end-state, ` +
        `doesn't lose any other improvements v24 shipped.`,
      suggestions: [
        "draft the surgical fix as a Linear ticket",
        "show me an unaffected call",
        "why is gpt-4o-2024-08-06 not affected?",
      ],
    };
  }

  // Generic fallback — Falcon reflects the question back with the cluster's
  // current best understanding.
  const errName = error?.error?.name ?? "this cluster";
  return {
    intro: "Let me dig into that.",
    subagent: { title: "Cluster investigator" },
    steps: [
      {
        title: "Re-read the cluster summary + recent traces",
        detail:
          "8 spans · 2 representative traces · same root cause across both.",
        ...SHORT_DELAY,
        details: [],
      },
      {
        title: "Drafting a focused answer",
        detail: "—",
        ...MED_DELAY,
        details: [],
      },
    ],
    answer:
      `Based on what's known about **${errName}**: the regression is prompt-side ` +
      `(v24 dropped the schema example), low-risk to roll back, and reproduces ` +
      `on gpt-4o-mini only. Happy to dig into a specific angle — try one of ` +
      `the suggestions below or ask anything else.`,
    suggestions: [
      "why did this start happening?",
      "what's the smallest fix that ships today?",
      "show me an unaffected call",
    ],
  };
}

function makeSubagentStepMessage(idx, step, subagentMsgId) {
  return {
    id: `${subagentMsgId}-step-${idx}`,
    title: step.title,
    detail: step.detail,
    chips: step.chips ?? [],
    status: "queued",
    details: step.details ?? [],
  };
}

export function useAnalyzeRunner(clusterId, error) {
  const setAnalyzeThread = useErrorFeedStore((s) => s.setAnalyzeThread);
  const clearAnalyzePendingStart = useErrorFeedStore(
    (s) => s.clearAnalyzePendingStart,
  );
  const pendingStart = useErrorFeedStore(
    (s) => !!s.analyzePendingStartByCluster[clusterId],
  );

  const timersRef = useRef([]);
  const clearTimers = useCallback(() => {
    timersRef.current.forEach((t) => clearTimeout(t));
    timersRef.current = [];
  }, []);

  // Cancel pending timers when the user leaves this cluster.
  useEffect(() => () => clearTimers(), [clusterId, clearTimers]);

  const patch = useCallback(
    (mutator) => {
      const current =
        useErrorFeedStore.getState().analyzeThreadsByCluster[clusterId];
      const seed = current ?? { messages: [], runState: "idle", startedAt: null };
      setAnalyzeThread(clusterId, mutator(seed));
    },
    [clusterId, setAnalyzeThread],
  );

  const startRun = useCallback(() => {
    if (!clusterId) return;
    clearTimers();

    const now = new Date();
    const timeLabel = now.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    patch((t) => ({
      messages:
        t.messages.length > 0
          ? [
              ...t.messages,
              {
                id: `hdr-${Date.now()}`,
                type: "run_header",
                label: "Re-run",
                timestamp: timeLabel,
              },
            ]
          : [],
      runState: "streaming",
      startedAt: Date.now(),
    }));

    const enqueueNext = (i) => {
      const step = RUN_STEPS[i];
      if (!step) {
        const synth = buildSynthesis(error);
        const t1 = setTimeout(() => {
          patch((t) => ({
            ...t,
            messages: [...t.messages, synth],
            runState: "done",
          }));
        }, 250);
        timersRef.current.push(t1);
        return;
      }
      const msg = makeStepMessage(i);
      patch((t) => ({ ...t, messages: [...t.messages, msg] }));
      const tRun = setTimeout(() => {
        patch((t) => ({
          ...t,
          messages: t.messages.map((m) =>
            m.id === msg.id ? { ...m, status: "running" } : m,
          ),
        }));
        const tDone = setTimeout(() => {
          patch((t) => ({
            ...t,
            messages: t.messages.map((m) =>
              m.id === msg.id ? { ...m, status: "done" } : m,
            ),
          }));
          enqueueNext(i + 1);
        }, step.doneDelayMs);
        timersRef.current.push(tDone);
      }, step.runDelayMs);
      timersRef.current.push(tRun);
    };

    enqueueNext(0);
  }, [clusterId, error, clearTimers, patch]);

  // Auto-fire whenever the pending-start flag flips on for this cluster.
  // Single source of truth: any analyze button anywhere just sets the flag.
  useEffect(() => {
    if (!clusterId || !pendingStart) return;
    clearAnalyzePendingStart(clusterId);
    startRun();
  }, [clusterId, pendingStart, clearAnalyzePendingStart, startRun]);

  return { startRun, clearTimers };
}

// ── Follow-up runner ────────────────────────────────────────────────────────
// Separate hook so AnalyzeTab can own follow-up state independently of the
// parent's main analyze run. Both hooks patch the same per-cluster thread in
// the store; they don't share timers, which keeps timer cleanup simple.
export function useFollowUpRunner(clusterId, error) {
  const setAnalyzeThread = useErrorFeedStore((s) => s.setAnalyzeThread);

  const timersRef = useRef([]);
  const clearTimers = useCallback(() => {
    timersRef.current.forEach((t) => clearTimeout(t));
    timersRef.current = [];
  }, []);
  useEffect(() => () => clearTimers(), [clusterId, clearTimers]);

  const patch = useCallback(
    (mutator) => {
      const current =
        useErrorFeedStore.getState().analyzeThreadsByCluster[clusterId];
      if (!current) return; // no thread yet — nothing to patch
      setAnalyzeThread(clusterId, mutator(current));
    },
    [clusterId, setAnalyzeThread],
  );

  const runFollowUp = useCallback(
    (question) => {
      const text = String(question ?? "").trim();
      if (!clusterId || !text) return;

      const baseId = `fu-${Date.now()}`;
      const userMsgId = `${baseId}-q`;
      const introMsgId = `${baseId}-i`;
      const subagentMsgId = `${baseId}-sa`;
      const tpl = pickFollowUpTemplate(text, error);

      // Push the user question + assistant intro + an empty sub-agent shell.
      patch((t) => ({
        ...t,
        followUpRunState: "streaming",
        messages: [
          ...t.messages,
          { id: userMsgId, type: "user_question", text },
          { id: introMsgId, type: "assistant_intro", text: tpl.intro },
          {
            id: subagentMsgId,
            type: "subagent",
            title: tpl.subagent.title,
            traceShortId: tpl.subagent.traceShortId,
            status: "streaming",
            steps: tpl.steps.map((s, i) =>
              makeSubagentStepMessage(i, s, subagentMsgId),
            ),
            answer: null,
          },
        ],
      }));

      // Walk each sub-step queued → running → done. When all done, drop in
      // the final answer + a fresh suggestion-chip set.
      const enqueueStep = (i) => {
        const step = tpl.steps[i];
        if (!step) {
          const tDone = setTimeout(() => {
            patch((t) => ({
              ...t,
              followUpRunState: "done",
              messages: t.messages
                .map((m) =>
                  m.id === subagentMsgId
                    ? { ...m, status: "done", answer: tpl.answer }
                    : m,
                )
                .concat([
                  {
                    id: `${baseId}-sug`,
                    type: "suggestions",
                    items: tpl.suggestions,
                  },
                ]),
            }));
          }, 200);
          timersRef.current.push(tDone);
          return;
        }

        const stepId = `${subagentMsgId}-step-${i}`;
        const tRun = setTimeout(() => {
          patch((t) => ({
            ...t,
            messages: t.messages.map((m) =>
              m.id === subagentMsgId
                ? {
                    ...m,
                    steps: m.steps.map((s) =>
                      s.id === stepId ? { ...s, status: "running" } : s,
                    ),
                  }
                : m,
            ),
          }));
          const tDone = setTimeout(() => {
            patch((t) => ({
              ...t,
              messages: t.messages.map((m) =>
                m.id === subagentMsgId
                  ? {
                      ...m,
                      steps: m.steps.map((s) =>
                        s.id === stepId ? { ...s, status: "done" } : s,
                      ),
                    }
                  : m,
              ),
            }));
            enqueueStep(i + 1);
          }, step.doneDelayMs);
          timersRef.current.push(tDone);
        }, step.runDelayMs);
        timersRef.current.push(tRun);
      };

      enqueueStep(0);
    },
    [clusterId, error, patch],
  );

  return { runFollowUp, clearTimers };
}
