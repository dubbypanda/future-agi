import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import axios from "src/utils/axios";
import { useDeletePromptTemplate } from "../prompt";

vi.mock("src/utils/axios", () => ({
  default: {
    delete: vi.fn(),
  },
  endpoints: {
    develop: {
      runPrompt: {
        promptTemplateId: (id) => `/model-hub/prompt-base-templates/${id}/`,
      },
    },
  },
}));

function wrapper({ children }) {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return React.createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("useDeletePromptTemplate", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("issues DELETE /model-hub/prompt-base-templates/{id}/ with the exact id", async () => {
    axios.delete.mockResolvedValueOnce({ data: {} });

    const { result } = renderHook(() => useDeletePromptTemplate(), { wrapper });

    result.current.mutate("template-123");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(axios.delete).toHaveBeenCalledTimes(1);
    expect(axios.delete).toHaveBeenCalledWith(
      "/model-hub/prompt-base-templates/template-123/",
    );
  });

  it("forwards onSuccess/onError options to the mutation", async () => {
    axios.delete.mockResolvedValueOnce({ data: {} });
    const onSuccess = vi.fn();

    const { result } = renderHook(
      () => useDeletePromptTemplate({ onSuccess }),
      { wrapper },
    );

    result.current.mutate("template-abc");

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
  });
});
