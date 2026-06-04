import React from "react";
import PropTypes from "prop-types";
import { Box, IconButton, Stack, Typography } from "@mui/material";
import Iconify from "src/components/iconify";

/**
 * Sticky in-content header for the chat compare view. Renders a back
 * arrow, the page title, and an optional subtitle (scenario name and
 * session id). Same `background.default` + `divider` token combo as
 * `ChatDetailsBar` so the two surfaces visually rhyme.
 *
 * Replaces the legacy breadcrumb pattern in
 * `BasLineCompare/Header.jsx`. The drawer's outer chrome
 * (VoiceDrawerHeader with Close / Prev / Next / Fullscreen) stays
 * mounted, so this bar only owns the back-to-chat affordance and the
 * compare-mode label.
 */
const CompareHeaderBar = ({ onBack, scenarioName, sessionId }) => {
  const subtitleParts = [];
  if (scenarioName) subtitleParts.push(scenarioName);
  if (sessionId) subtitleParts.push(`Session ${sessionId}`);
  const subtitle = subtitleParts.join("  ·  ");

  return (
    <Box
      sx={{
        position: "sticky",
        top: 0,
        zIndex: 2,
        px: 1.5,
        py: 1,
        borderBottom: "1px solid",
        borderColor: "divider",
        bgcolor: "background.default",
        flexShrink: 0,
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1}>
        <IconButton
          onClick={onBack}
          size="small"
          aria-label="Back to chat"
          sx={{
            color: "text.primary",
            border: "1px solid",
            borderColor: "divider",
            borderRadius: "4px",
            width: 24,
            height: 24,
            p: 0,
            "&:hover": { bgcolor: "action.hover" },
          }}
        >
          <Iconify icon="mdi:arrow-left" width={14} />
        </IconButton>

        <Stack sx={{ minWidth: 0, flex: 1 }}>
          <Typography
            sx={{
              fontSize: 13,
              fontWeight: 600,
              color: "text.primary",
              lineHeight: 1.2,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            Compare baseline vs replay
          </Typography>
          {subtitle && (
            <Typography
              sx={{
                fontSize: 11,
                color: "text.secondary",
                lineHeight: 1.4,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {subtitle}
            </Typography>
          )}
        </Stack>
      </Stack>
    </Box>
  );
};

CompareHeaderBar.propTypes = {
  onBack: PropTypes.func.isRequired,
  scenarioName: PropTypes.string,
  sessionId: PropTypes.string,
};

export default CompareHeaderBar;
