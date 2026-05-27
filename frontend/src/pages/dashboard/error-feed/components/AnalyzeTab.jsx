// AnalyzeTab — Cluster RCA agent live-stream demo.
//
// Triggers POST /cluster-rca/stream/<cluster_id>/ which Server-Sent-Events
// every tool_call / tool_result / finding / synthesis / done / error event
// from the agent's loop. Renders them chronologically while the run is in
// flight. No persistence — closing the tab kills the run.
//
// Production shape (run history, reconnect-after-close, chat surface) lands
// when the designer hands over the real UI.

import React, { useEffect, useRef, useState } from "react";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Stack,
  Typography,
  alpha,
  useTheme,
} from "@mui/material";
import PropTypes from "prop-types";
import Iconify from "src/components/iconify";
import { HOST_API } from "src/config-global";
import { getAccessToken } from "src/auth/context/jwt/utils";

const STATUS = {
  IDLE: "idle",
  RUNNING: "running",
  DONE: "done",
  ERROR: "error",
};

const TYPE_COLORS = {
  tool_call: "info.main",
  tool_result: "text.secondary",
  finding: "warning.main",
  synthesis: "success.main",
  error: "error.main",
  done: "primary.main",
};

export default function AnalyzeTab({ error }) {
  const theme = useTheme();
  const [status, setStatus] = useState(STATUS.IDLE);
  const [events, setEvents] = useState([]);
  const [synthesis, setSynthesis] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [doneMeta, setDoneMeta] = useState(null);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);

  // Auto-scroll to the latest event whenever the list grows.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  // Cleanup on unmount — abort the in-flight fetch.
  useEffect(
    () => () => {
      if (abortRef.current) abortRef.current.abort();
    },
    [],
  );

  const handleEvent = (evt) => {
    if (evt.type === "stream_end") {
      setStatus((prev) => (prev === STATUS.RUNNING ? STATUS.DONE : prev));
      return;
    }
    setEvents((prev) => [...prev, evt]);
    if (evt.type === "synthesis") setSynthesis(evt.payload);
    if (evt.type === "done") setDoneMeta(evt.payload);
    if (evt.type === "error") {
      setErrorMsg(evt.payload?.message ?? "Unknown error");
      setStatus(STATUS.ERROR);
    }
  };

  const startRun = async () => {
    setEvents([]);
    setSynthesis(null);
    setErrorMsg(null);
    setDoneMeta(null);
    setStatus(STATUS.RUNNING);

    const controller = new AbortController();
    abortRef.current = controller;

    const clusterId = error.clusterId || error.cluster_id || error.id;
    if (!clusterId) {
      setErrorMsg("No cluster_id on the row — cannot start analysis.");
      setStatus(STATUS.ERROR);
      return;
    }

    try {
      const token = getAccessToken();
      const response = await fetch(
        `${HOST_API}/cluster-rca/stream/${clusterId}/`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({}),
          signal: controller.signal,
        },
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // SSE frames are separated by \n\n; data lines start with "data: ".
      // We accumulate, split on the frame separator, and parse each complete
      // frame's JSON payload.
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const frames = buffer.split("\n\n");
        buffer = frames.pop(); // last (possibly incomplete) frame

        for (const frame of frames) {
          const dataLine = frame
            .split("\n")
            .find((l) => l.startsWith("data:"));
          if (!dataLine) continue;
          const json = dataLine.slice(5).trim();
          if (!json) continue;
          try {
            handleEvent(JSON.parse(json));
          } catch (e) {
            // eslint-disable-next-line no-console
            console.warn("SSE parse error:", e, json);
          }
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") {
        setErrorMsg(e.message ?? String(e));
        setStatus(STATUS.ERROR);
      }
    }
  };

  const stop = () => {
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = null;
    setStatus(STATUS.IDLE);
  };

  const isRunning = status === STATUS.RUNNING;
  const isDone = status === STATUS.DONE;
  const isError = status === STATUS.ERROR;

  return (
    <Box
      sx={{
        p: 2,
        display: "flex",
        flexDirection: "column",
        height: "100%",
        gap: 1.5,
      }}
    >
      {/* ── Header ── */}
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
      >
        <Stack direction="row" alignItems="center" gap={1}>
          <Typography typography="m3" fontWeight="fontWeightSemiBold">
            Cluster Analysis
          </Typography>
          <Chip
            label="Demo"
            size="small"
            sx={{ height: 18, fontSize: 10, bgcolor: "action.hover" }}
          />
          {isRunning && (
            <Chip
              size="small"
              label="Running"
              color="primary"
              icon={
                <CircularProgress
                  size={12}
                  sx={{ ml: 0.5, color: "inherit" }}
                />
              }
              sx={{ height: 22 }}
            />
          )}
          {isDone && (
            <Chip
              size="small"
              label="Done"
              color="success"
              icon={<Iconify icon="mdi:check" width={14} />}
              sx={{ height: 22 }}
            />
          )}
          {isError && (
            <Chip
              size="small"
              label="Error"
              color="error"
              icon={<Iconify icon="mdi:alert" width={14} />}
              sx={{ height: 22 }}
            />
          )}
        </Stack>
        <Stack direction="row" gap={1}>
          {isRunning ? (
            <Button
              size="small"
              variant="outlined"
              color="warning"
              onClick={stop}
              startIcon={<Iconify icon="mdi:stop" width={14} />}
            >
              Stop
            </Button>
          ) : (
            <Button
              size="small"
              variant="contained"
              onClick={startRun}
              startIcon={<Iconify icon="mdi:play" width={14} />}
            >
              {isDone || isError ? "Re-run" : "Start Analysis"}
            </Button>
          )}
        </Stack>
      </Stack>

      {/* ── Error banner ── */}
      {errorMsg && (
        <Box
          sx={{
            p: 1.5,
            bgcolor: alpha(theme.palette.error.main, 0.08),
            borderRadius: 1,
            border: "1px solid",
            borderColor: alpha(theme.palette.error.main, 0.3),
          }}
        >
          <Typography variant="caption" color="error.main">
            {errorMsg}
          </Typography>
        </Box>
      )}

      {/* ── Synthesis card (when present) ── */}
      {synthesis && (
        <Box
          sx={{
            p: 2,
            border: "1px solid",
            borderColor: "success.main",
            borderRadius: 1,
            bgcolor: alpha(theme.palette.success.main, 0.05),
          }}
        >
          <Stack direction="row" alignItems="center" gap={1} mb={1}>
            <Iconify
              icon="mdi:check-circle"
              width={18}
              sx={{ color: "success.main" }}
            />
            <Typography typography="m3" fontWeight="fontWeightSemiBold">
              Synthesis
            </Typography>
            <Chip
              size="small"
              label={`confidence: ${synthesis.confidence}`}
              sx={{ height: 18, fontSize: 10 }}
            />
          </Stack>
          <Typography variant="body2" mb={1}>
            {synthesis.synthesis}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            <strong>Fix:</strong> {synthesis.fix}
          </Typography>
          {Array.isArray(synthesis.evidence_trace_ids) &&
            synthesis.evidence_trace_ids.length > 0 && (
              <Typography variant="caption" color="text.disabled" mt={1}>
                Evidence: {synthesis.evidence_trace_ids.length} trace(s)
              </Typography>
            )}
        </Box>
      )}

      {/* ── Done meta ── */}
      {doneMeta && !synthesis && (
        <Box
          sx={{
            p: 1.5,
            bgcolor: alpha(theme.palette.primary.main, 0.05),
            borderRadius: 1,
          }}
        >
          <Typography variant="caption" color="text.secondary">
            Run ended — {doneMeta.terminated_reason} after{" "}
            {doneMeta.turn_count} turns, {doneMeta.finding_count} finding(s),
            no synthesis.
          </Typography>
        </Box>
      )}

      {/* ── Event stream ── */}
      <Box
        ref={scrollRef}
        sx={{
          flex: 1,
          overflow: "auto",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          p: 1.25,
          fontFamily:
            "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
          fontSize: 12,
          bgcolor: "background.default",
        }}
      >
        {events.length === 0 ? (
          <Typography variant="caption" color="text.disabled">
            {status === STATUS.IDLE
              ? "Click Start Analysis to run the agent against this cluster."
              : "Waiting for events…"}
          </Typography>
        ) : (
          <Stack gap={0.5}>
            {events.map((evt, idx) => (
              <EventRow key={idx} event={evt} />
            ))}
          </Stack>
        )}
      </Box>
    </Box>
  );
}

AnalyzeTab.propTypes = {
  error: PropTypes.shape({
    // The FE row uses `clusterId` (camelCased from `cluster_id` CharField) —
    // that's the per-project label like "C01". We fall back to `cluster_id`
    // or `id` for forward-compat.
    clusterId: PropTypes.string,
    cluster_id: PropTypes.string,
    id: PropTypes.string,
  }).isRequired,
};

// ── Single event row ────────────────────────────────────────────────────────
function EventRow({ event }) {
  const { type, payload = {} } = event;
  const color = TYPE_COLORS[type] ?? "text.primary";

  let preview;
  if (type === "tool_call") {
    const args = JSON.stringify(payload.args ?? {});
    preview = `${payload.tool}(${args.length > 80 ? `${args.slice(0, 80)}…` : args})`;
  } else if (type === "tool_result") {
    const res = payload.result ?? {};
    preview = res.is_error
      ? `← ${payload.tool}  [error: ${res.code}] ${res.message ?? ""}`
      : `← ${payload.tool}  [ok]`;
  } else if (type === "finding") {
    preview = `📌  ${payload.title}  (${payload.confidence}, ${payload.finding_type})`;
  } else if (type === "synthesis") {
    const s = payload.synthesis ?? "";
    preview = `✅  ${s.length > 100 ? `${s.slice(0, 100)}…` : s}`;
  } else if (type === "error") {
    preview = `❌  ${payload.message}`;
  } else if (type === "done") {
    preview = `🏁  ${payload.terminated_reason}  (${payload.turn_count} turns, ${payload.finding_count} findings)`;
  } else {
    preview = JSON.stringify(payload);
  }

  return (
    <Stack direction="row" gap={1} alignItems="flex-start">
      <Box
        sx={{
          minWidth: 80,
          color,
          fontWeight: 600,
          flexShrink: 0,
          fontSize: 11,
        }}
      >
        {type}
        {payload.turn ? ` t${payload.turn}` : ""}
      </Box>
      <Box
        sx={{
          flex: 1,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          fontSize: 12,
        }}
      >
        {preview}
      </Box>
    </Stack>
  );
}

EventRow.propTypes = {
  event: PropTypes.shape({
    type: PropTypes.string.isRequired,
    payload: PropTypes.object,
  }).isRequired,
};
