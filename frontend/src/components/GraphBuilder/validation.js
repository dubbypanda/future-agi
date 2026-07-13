import z from "zod";
import { NODE_TYPES } from "./store/graphStore";

const PositionSchema = z.object({
  x: z.number(),
  y: z.number(),
});

export const ValidateAndTransformNodeSchema = () =>
  z
    .discriminatedUnion("type", [
      z.object({
        type: z.literal(NODE_TYPES.CONVERSATION),
        data: z.object({
          name: z.string().min(1, "Conversation node needs a name"),
          prompt: z.string().min(1, "Conversation node needs a prompt"),
          isStart: z.boolean().default(false),
          isGlobal: z.boolean().default(false),
        }),
        position: PositionSchema,
      }),
      z.object({
        type: z.literal(NODE_TYPES.END),
        data: z.object({
          name: z.string().min(1, "End node needs a name"),
          prompt: z.string().min(1, "End node needs a prompt"),
        }),
        position: PositionSchema,
      }),
      z.object({
        type: z.literal(NODE_TYPES.TRANSFER),
        data: z.object({
          name: z.string().min(1, "Transfer node needs a name"),
          prompt: z.string(),
        }),
        position: PositionSchema,
      }),
      z.object({
        type: z.literal(NODE_TYPES.END_CHAT),
        data: z.object({
          name: z.string().min(1, "End chat node needs a name"),
          prompt: z.string().min(1, "End chat node needs a prompt"),
        }),
        position: PositionSchema,
      }),
      z.object({
        type: z.literal(NODE_TYPES.TRANSFER_CHAT),
        data: z.object({
          name: z.string().min(1, "Transfer chat node needs a name"),
          prompt: z.string(),
        }),
        position: PositionSchema,
      }),
    ])
    .transform((data) => {
      if (data?.type === NODE_TYPES.CONVERSATION) {
        return {
          name: data?.data?.name,
          type: "conversation",
          prompt: data?.data?.prompt,
          isStart: data?.data?.isStart,
          isGlobal: data?.data?.isGlobal,
          metadata: {
            position: data?.position,
          },
        };
      } else if (data?.type === NODE_TYPES.END) {
        return {
          name: data?.data?.name,
          tool: {
            type: "endCall",
            function: {
              name: "end_call",
              parameters: {
                type: "object",
                required: [],
                properties: {},
              },
            },
            messages: [
              {
                type: "request-start",
                content: data?.data?.prompt,
                blocking: true,
              },
            ],
          },
          type: "tool",
          isStart: false,
          metadata: {
            position: data?.position,
          },
        };
      } else if (data?.type === NODE_TYPES.TRANSFER) {
        return {
          name: data?.data?.name,
          tool: {
            type: "transferCall",
            function: {
              name: "transfer_call",
              parameters: {
                type: "object",
                required: [],
                properties: {},
              },
            },
            messages: [
              {
                type: "request-start",
                content: data?.data?.prompt,
                blocking: true,
              },
            ],
            destinations: [],
          },
          type: "tool",
          isStart: false,
          metadata: {
            position: data?.position,
          },
        };
      } else if (data?.type === NODE_TYPES.END_CHAT) {
        return {
          name: data?.data?.name,
          tool: {
            type: "endChat",
            function: {
              name: "end_chat",
              parameters: {
                type: "object",
                required: [],
                properties: {},
              },
            },
            messages: [
              {
                type: "request-start",
                content: data?.data?.prompt,
                blocking: true,
              },
            ],
          },
          type: "tool",
          isStart: false,
          metadata: {
            position: data?.position,
          },
        };
      } else if (data?.type === NODE_TYPES.TRANSFER_CHAT) {
        return {
          name: data?.data?.name,
          tool: {
            type: "transferChat",
            function: {
              name: "transfer_chat",
              parameters: {
                type: "object",
                required: [],
                properties: {},
              },
            },
            messages: [
              {
                type: "request-start",
                content: data?.data?.prompt,
                blocking: true,
              },
            ],
            destinations: [],
          },
          type: "tool",
          isStart: false,
          metadata: {
            position: data?.position,
          },
        };
      }
    });

export const ValidateAndTransformEdgeSchema = () =>
  z
    .object({
      type: z.literal("condition"),
      data: z.object({
        prompt: z.string().min(1, "Condition node needs a prompt"),
      }),
      source: z.string().min(1, "Condition node needs a source"),
      target: z.string().min(1, "Condition node needs a target"),
    })
    .transform((data) => ({
      to: data?.target,
      from: data?.source,
      condition: {
        type: "ai",
        prompt: data?.data?.prompt,
      },
    }));

export const ValidateAndTransformGraphSchema = () =>
  z.object({
    nodes: z.array(ValidateAndTransformNodeSchema()),
    edges: z.array(ValidateAndTransformEdgeSchema()),
  });
