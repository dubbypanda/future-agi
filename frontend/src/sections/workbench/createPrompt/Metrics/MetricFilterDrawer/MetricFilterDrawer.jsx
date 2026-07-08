import React, {
  useMemo,
  useCallback,
  useState,
  useEffect,
  useRef,
} from "react";
import { Drawer, Box, IconButton, Typography, Button } from "@mui/material";
import Iconify from "src/components/iconify";
import { useWorkbenchMetrics } from "../context/WorkbenchMetricsContext";
import { getRandomId } from "src/utils/utils";
import { buildFilterDefinitions, defaultFilterBase } from "../common";
import LLMFilterBox from "src/sections/projects/LLMTracing/LLMFilterBox";

const MetricFilterDrawer = React.memo(() => {
  const {
    isFilterDrawerOpen,
    setIsFilterDrawerOpen,
    columns,
    filters,
    setFilters,
    activeTab,
  } = useWorkbenchMetrics();

  const getDefaultFilter = () => [{ ...defaultFilterBase, id: getRandomId() }];

  const prevTabRef = useRef(activeTab);

  const [filterDefs, setFilterDefs] = useState([]);

  const normalizeFilterObj = useCallback((f) => {
    if (!f) return f;
    const nf = { ...f };
    if (nf.column_id && !nf.columnId) {
      nf.columnId = nf.column_id;
    }
    if (nf.filter_config && !nf.filterConfig) {
      nf.filterConfig = {
        filterType: nf.filter_config.filter_type || "",
        filterOp: nf.filter_config.filter_op || "",
        filterValue: nf.filter_config.filter_value ?? "",
        col_type: nf.filter_config.col_type,
      };
    }
    return nf;
  }, []);

  const normalizeFilters = useCallback((arr) => arr.map(normalizeFilterObj), [normalizeFilterObj]);

  const [tempFilters, setTempFiltersRaw] = useState(() =>
    filters?.length ? normalizeFilters(filters) : getDefaultFilter(),
  );
  const [tempFilterDefs, setTempFilterDefs] = useState([]);

  const setTempFilters = useCallback((val) => {
    setTempFiltersRaw((prev) => {
      const next = typeof val === "function" ? val(prev) : val;
      return Array.isArray(next) ? normalizeFilters(next) : next;
    });
  }, [normalizeFilters]);

  useEffect(() => {
    if (columns?.length) {
      setFilterDefs(buildFilterDefinitions(columns, activeTab === "Metrics"));
    }
  }, [columns, activeTab]);

  useEffect(() => {
    if (prevTabRef.current !== activeTab) {
      setFilters(getDefaultFilter());
      prevTabRef.current = activeTab;
    }
  }, [activeTab, setFilters]);

  useEffect(() => {
    if (isFilterDrawerOpen) {
      const normalizedFilters = filters.map((f) => {
        const newFilter = { ...f };

        // ✅ Normalize number filters into string arrays
        if (newFilter.filterConfig?.filterType === "number") {
          const value = newFilter.filterConfig.filterValue;

          if (typeof value === "number") {
            newFilter.filterConfig.filterValue = [String(value), ""];
          } else if (Array.isArray(value)) {
            newFilter.filterConfig.filterValue = value.map((v) =>
              v === "" ? "" : String(v),
            );
          }
        }

        // ✅ Normalize date filters into array form for the drawer
        if (newFilter.filterConfig?.filterType === "date" && newFilter.filterConfig?.filterValue) {
          const value = newFilter.filterConfig.filterValue;

          if (typeof value === "string") {
            // single-value ops → wrap into array
            newFilter.filterConfig.filterValue = [value, "0"];
          } else if (Array.isArray(value)) {
            // already array, just keep as is
            newFilter.filterConfig.filterValue = value;
          }
        }

        return newFilter;
      });

      setTempFilters(normalizedFilters);
      setTempFilterDefs(filterDefs);
    }
  }, [isFilterDrawerOpen, filters, filterDefs]);

  const handleClose = useCallback(() => {
    setIsFilterDrawerOpen(false);
  }, [setIsFilterDrawerOpen]);

  const handleApplyFilters = useCallback(() => {
    const validFilters = tempFilters
      .filter(
        (f) =>
          f?.columnId ||
          (f?.filterConfig?.filterValue !== "" &&
            f?.filterConfig &&
            !(
              Array.isArray(f?.filterConfig?.filterValue) &&
              f?.filterConfig?.filterValue?.length === 0
            )),
      )
      .map((f) => {
        const newFilter = { ...f };

        const def =
          filterDefs.find((d) => d.propertyId === f.columnId) ||
          filterDefs
            .find((d) => d.propertyName === "Evaluation Metrics")
            ?.dependents.find((d) => d.propertyId === f.columnId);

        if (def?.filterType?.type) {
          if (def.filterType.type === "option") {
            newFilter.filterConfig.filterType = "array";
          } else if (
            newFilter.filterConfig.filterType !== "array" &&
            newFilter.filterConfig.filterType !== "option"
          ) {
            newFilter.filterConfig.filterType = def.filterType.type;
          }
        }

        // 🔹 Normalize number filter values
        if (newFilter.filterConfig?.filterType === "number" && newFilter.filterConfig?.filterValue) {
          const values = newFilter.filterConfig.filterValue;

          if (Array.isArray(values)) {
            const numericValues = values.filter((v) => v !== "").map(Number);

            if (numericValues.length === 1) {
              newFilter.filterConfig.filterValue = numericValues[0];
            } else {
              newFilter.filterConfig.filterValue = numericValues;
            }
          } else if (typeof values === "string" && values.trim() !== "") {
            newFilter.filterConfig.filterValue = Number(values);
          }
        }

        if (newFilter._meta?.parentProperty === "Evaluation Metrics") {
          newFilter.col_type = "PROMPT_METRIC";
        }

        return newFilter;
      });

    setFilters(validFilters.length ? validFilters : getDefaultFilter());
    handleClose();
  }, [tempFilters, setFilters, handleClose, filterDefs]);

  const hasValidFilters = useMemo(() => {
    return tempFilters.some(
      (f) =>
        f?.columnId ||
        (f?.filterConfig?.filterValue !== "" &&
          f?.filterConfig &&
          !(
            Array.isArray(f?.filterConfig?.filterValue) &&
            f?.filterConfig?.filterValue?.length === 0
          )),
    );
  }, [tempFilters]);

  const handleCancel = useCallback(() => {
    handleClose();
  }, [handleClose]);

  const resetFiltersAndClose = () => {
    setFilters(getDefaultFilter());
    handleClose();
  };

  const drawerStyles = useMemo(
    () => ({
      height: "100vh",
      position: "fixed",
      borderRadius: "0px !important",
      backgroundColor: "background.paper",
      width: "36vw",
      display: "flex",
      flexDirection: "column",
    }),
    [],
  );

  const drawerContentStyles = useMemo(
    () => ({
      padding: 2,
      flex: 1,
      display: "flex",
      height: "100%",
      flexDirection: "column",
    }),
    [],
  );

  const closeButtonStyles = useMemo(
    () => ({
      position: "absolute",
      top: "10px",
      right: "10px",
      color: "text.primary",
      zIndex: 10,
    }),
    [],
  );

  const actionButtonStyles = useMemo(
    () => ({
      pt: 2,
      display: "flex",
      gap: 2,
      justifyContent: "flex-end",
      borderTop: "1px solid",
      borderColor: "background.neutral",
      mt: "auto",
    }),
    [],
  );

  const scrollableContentStyles = useMemo(
    () => ({
      flex: 1,
      overflowY: "auto",
      pr: 1, // Padding for scrollbar
      display: "flex",
      flexDirection: "column",
    }),
    [],
  );

  return (
    <Drawer
      anchor="right"
      open={isFilterDrawerOpen}
      onClose={handleClose}
      variant="persistent"
      PaperProps={{ sx: drawerStyles }}
      ModalProps={{
        BackdropProps: { style: { backgroundColor: "transparent" } },
      }}
    >
      <Box sx={drawerContentStyles}>
        <IconButton onClick={handleClose} sx={closeButtonStyles}>
          <Iconify icon="akar-icons:cross" />
        </IconButton>

        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="center"
          mb={2}
        >
          <Typography variant="h6">Filters</Typography>
        </Box>
        <Box sx={scrollableContentStyles}>
          <LLMFilterBox
            filters={tempFilters}
            setFilters={setTempFilters}
            filterDefinition={tempFilterDefs}
            setFilterDefinition={setTempFilterDefs}
            defaultFilter={defaultFilterBase}
            resetFiltersAndClose={resetFiltersAndClose}
          />
        </Box>
        <Box sx={actionButtonStyles}>
          <Button
            variant="outlined"
            aria-label="cancel"
            size="small"
            onClick={handleCancel}
            sx={{ width: 140, px: 1, borderColor: "text.disabled" }}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            aria-label="apply-filters"
            color="primary"
            size="small"
            onClick={handleApplyFilters}
            sx={{ width: 140, px: 1 }}
            disabled={!hasValidFilters}
          >
            Apply Filters
          </Button>
        </Box>
      </Box>
    </Drawer>
  );
});

MetricFilterDrawer.displayName = "MetricFilterDrawer";

export default MetricFilterDrawer;
