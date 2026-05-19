import React from "react";
import PropTypes from "prop-types";
import { Box } from "@mui/material";
import EvaluateCell from "../EvaluateCellRenderer/EvaluateCell";
import CustomTooltip from "src/components/tooltip";
import Iconify from "src/components/iconify";
import { tooltipSlotProp } from "./cellRendererHelper";

// Render a small yellow warning chip on cells where the eval ran with some
// inputs empty. Surfaced when the backend attaches a `partial_input`
// warning (see eval_runner._run_evaluation for the producer side).
const PartialInputWarningBadge = ({ warnings }) => {
  const partial = warnings?.find((w) => w?.type === "partial_input");
  if (!partial) return null;
  const emptyKeys = partial.empty_keys || [];
  const message =
    partial.message ||
    `Eval ran with some inputs empty (${emptyKeys.join(", ")}). Result may be less reliable. Ignore if this is intentional.`;
  return (
    <CustomTooltip title={message} arrow>
      <Box
        sx={{
          position: "absolute",
          top: 4,
          right: 4,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: 18,
          height: 18,
          borderRadius: "50%",
          backgroundColor: "warning.lighter",
          color: "warning.dark",
          cursor: "help",
        }}
        data-testid="partial-input-warning"
      >
        <Iconify
          icon="material-symbols:warning-rounded"
          width="14px"
          height="14px"
        />
      </Box>
    </CustomTooltip>
  );
};

PartialInputWarningBadge.propTypes = {
  warnings: PropTypes.array,
};

const EvaluateCellRendererWrapper = ({
  valueReason,
  formattedValueReason,
  cellData,
  value,
  dataType,
  originType,
  isFutureAgiEval,
  choicesMap,
  outputType,
  warnings,
}) => (
  <CustomTooltip
    show={Boolean(valueReason?.length)}
    title={formattedValueReason()}
    enterDelay={500}
    enterNextDelay={500}
    leaveDelay={100}
    arrow
    expandable
    slotProps={tooltipSlotProp}
  >
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        justifyContent: "center",
        position: "relative",
        // padding: "4px 8px",
      }}
    >
      <EvaluateCell
        cellData={cellData}
        value={value}
        dataType={dataType}
        meta={cellData?.metadata}
        isFutureAgiEval={isFutureAgiEval}
        originType={originType}
        choicesMap={choicesMap}
        outputType={outputType}
      />
      <PartialInputWarningBadge warnings={warnings} />
    </Box>
  </CustomTooltip>
);

EvaluateCellRendererWrapper.propTypes = {
  valueReason: PropTypes.any,
  formattedValueReason: PropTypes.func.isRequired,
  cellData: PropTypes.object,
  value: PropTypes.any,
  dataType: PropTypes.string,
  originType: PropTypes.string,
  isFutureAgiEval: PropTypes.bool,
  choicesMap: PropTypes.object,
  outputType: PropTypes.string,
  warnings: PropTypes.array,
};

export default React.memo(EvaluateCellRendererWrapper);
