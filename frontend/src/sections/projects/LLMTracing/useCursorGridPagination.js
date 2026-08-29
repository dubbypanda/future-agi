import { useCallback, useMemo, useRef, useState } from "react";
import {
  OBSERVE_LIST_DEFAULT_PAGE_SIZE,
  OBSERVE_LIST_PAGE_SIZE_OPTIONS,
} from "src/config/runtime_limits";
import { withLiveGridApi } from "src/utils/gridApi";

/**
 * Cursor-backed lists can expose only pages whose opaque cursor chain has
 * already been discovered. Keep AG Grid's synthetic row count and the visible
 * page controls aligned without publishing a guessed global total.
 */
export default function useCursorGridPagination(gridRef) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(OBSERVE_LIST_DEFAULT_PAGE_SIZE);
  const [pageCount, setPageCount] = useState(1);
  const [isPageLoading, setIsPageLoading] = useState(false);
  const discoveredRowCountRef = useRef(0);
  const hasPublishedPageRef = useRef(false);
  const publishedPagesRef = useRef(new Set());
  const pageLoadRequestRef = useRef(0);

  const beginPageLoad = useCallback((pageNumber) => {
    // The grids already own their initial-load presentation. This state is for
    // an explicit pagination transition, including a later uncached return to
    // page one after at least one page has been published.
    if (pageNumber === 0 && !hasPublishedPageRef.current) return null;
    const requestId = ++pageLoadRequestRef.current;
    setIsPageLoading(true);
    return requestId;
  }, []);

  const finishPageLoad = useCallback((requestId) => {
    if (requestId !== null && requestId === pageLoadRequestRef.current) {
      setIsPageLoading(false);
    }
  }, []);

  const resetPagination = useCallback(
    ({ moveGrid = true } = {}) => {
      pageLoadRequestRef.current += 1;
      setIsPageLoading(false);
      discoveredRowCountRef.current = 0;
      hasPublishedPageRef.current = false;
      publishedPagesRef.current.clear();
      setPage(1);
      setPageCount(1);
      if (moveGrid) {
        withLiveGridApi(gridRef?.current?.api, (api) =>
          api.paginationGoToFirstPage?.(),
        );
      }
    },
    [gridRef],
  );

  const publishPage = useCallback(({ request, rows, isLastPage }) => {
    hasPublishedPageRef.current = true;
    const requestPageSize = request.endRow - request.startRow;
    const terminalRowCount = request.startRow + rows.length;
    const nextPageSentinelRowCount = request.endRow + 1;
    const publishedPage = Math.floor(request.startRow / requestPageSize) + 1;
    publishedPagesRef.current.add(publishedPage);

    if (isLastPage) {
      discoveredRowCountRef.current = terminalRowCount;
    } else {
      discoveredRowCountRef.current = Math.max(
        discoveredRowCountRef.current,
        nextPageSentinelRowCount,
      );
    }

    const discoveredRowCount = discoveredRowCountRef.current;
    setPage(publishedPage);
    setPageCount(Math.max(1, Math.ceil(discoveredRowCount / requestPageSize)));
    return discoveredRowCount;
  }, []);

  const goToPage = useCallback(
    (nextPage) => {
      if (
        !Number.isSafeInteger(nextPage) ||
        nextPage < 1 ||
        nextPage > pageCount
      ) {
        return;
      }
      // A datasource read starts on AG Grid's next turn. Mark an unseen page
      // pending in the click handler so the current rows never disappear into
      // an unlabelled blank frame before getRows() begins.
      const navigationRequestId = publishedPagesRef.current.has(nextPage)
        ? null
        : beginPageLoad(nextPage - 1);
      const moved = withLiveGridApi(gridRef?.current?.api, (api) =>
        api.paginationGoToPage?.(nextPage - 1),
      );
      if (moved) {
        // Cursor pagination is driven exclusively by these controls. AG Grid
        // can briefly report page zero again when a terminal row count is
        // published, so keep the requested page authoritative until the
        // datasource confirms it in publishPage().
        setPage(nextPage);
      } else {
        finishPageLoad(navigationRequestId);
      }
    },
    [beginPageLoad, finishPageLoad, gridRef, pageCount],
  );

  const changePageSize = useCallback(
    (nextPageSize) => {
      if (
        nextPageSize === pageSize ||
        !OBSERVE_LIST_PAGE_SIZE_OPTIONS.includes(nextPageSize)
      ) {
        return;
      }
      resetPagination({ moveGrid: false });
      setPageSize(nextPageSize);
    },
    [pageSize, resetPagination],
  );

  return useMemo(
    () => ({
      beginPageLoad,
      page,
      pageCount,
      pageSize,
      changePageSize,
      finishPageLoad,
      goToPage,
      isPageLoading,
      publishPage,
      resetPagination,
    }),
    [
      beginPageLoad,
      changePageSize,
      finishPageLoad,
      goToPage,
      isPageLoading,
      page,
      pageCount,
      pageSize,
      publishPage,
      resetPagination,
    ],
  );
}
