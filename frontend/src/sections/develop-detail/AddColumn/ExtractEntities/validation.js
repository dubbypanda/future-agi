import { z } from "zod";

// Field names match the snake_case shape the backend returns from
// `GET /model-hub/columns/{id}/operation-config/` → `result.metadata`, so
// `reset(initialData)` on edit hydrates the form directly without a
// snake↔camel transform. Same pattern PR #1309 established for extract_json.
export const ExtractEntitiesValidationSchema = (
  isConditioalNode = false,
  isEdit,
) => {
  return z.object({
    type: z.string().optional(),
    column_id: z
      .string({
        required_error: "Column ID is required",
      })
      .min(1, {
        message: "Column is required",
      }),
    instruction: z
      .string({
        required_error: "Instruction is required",
      })
      .min(1, {
        message: "Instruction is required",
      }),
    language_model_id: z
      .string({
        required_error: "Language Model is required",
      })
      .min(1, {
        message: "Language Model is required",
      }),
    concurrency: z.number().positive("Concurrency must be a positive integer"),
    new_column_name:
      isConditioalNode || isEdit
        ? z.string().optional()
        : z
            .string({
              required_error: "New Column Name is required",
            })
            .min(1, {
              message: "New Column Name is required",
            }),
  });
};
