import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import TaskDetailPage from "../TaskDetailPage";
import { useGetTaskData } from "src/sections/common/EvalsTasks/common";

vi.mock("src/sections/common/EvalsTasks/common", async () => {
  const actual = await vi.importActual("src/sections/common/EvalsTasks/common");
  return {
    ...actual,
    useGetTaskData: vi.fn(),
  };
});

vi.mock("src/components/iconify", () => ({
  default: ({ icon }) => <span data-testid="icon">{icon}</span>,
}));

vi.mock("src/components/snackbar", () => ({
  enqueueSnackbar: vi.fn(),
}));

vi.mock("src/components/resizablePanels/ResizablePanels", () => ({
  default: () => <div>panels</div>,
}));

vi.mock("src/sections/common/EvalsTasks/TaskLogsView", () => ({
  default: () => <div>logs</div>,
}));

vi.mock("../components/TaskHeader", () => ({
  default: () => <div>task header</div>,
}));

vi.mock("../components/TaskConfigPanel", () => ({
  default: () => <div>task config</div>,
}));

vi.mock("../components/TaskLivePreview", () => ({
  default: React.forwardRef(() => <div>task preview</div>),
}));

vi.mock("../components/TaskUsageTab", () => ({
  default: () => <div>task usage</div>,
}));

vi.mock("src/sections/common/EvalsTasks/EditTaskDrawer/TaskConfirmBox", () => ({
  default: () => null,
}));

const renderTaskDetail = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/dashboard/tasks/missing-task"]}>
        <Routes>
          <Route
            path="/dashboard/tasks/:taskId"
            element={<TaskDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("TaskDetailPage", () => {
  it("shows a not-found state instead of an endless spinner when the task API fails", () => {
    useGetTaskData.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: {
        statusCode: 404,
        result: "Eval task not found",
      },
    });

    renderTaskDetail();

    expect(screen.getByText("Task not available")).toBeInTheDocument();
    expect(screen.getByText("Eval task not found")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Back to Tasks/i })).toBeEnabled();
  });
});
