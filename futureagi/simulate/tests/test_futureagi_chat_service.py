"""Regression tests for FutureAGIChatService message assembly (TH-7101).

The simulator persona must experience a human-like conversation, so the
agent-under-test's tool machinery is scrubbed from what the persona LLM sees:
tool results and pure tool-call turns are dropped, and only the agent's text
replies are forwarded (as assistant turns). This also makes the malformed
tool-call sequence that caused the send-message 500 structurally impossible.

The forwarding logic (`_to_provider_messages`) is pure — no DB — so these run
as plain unit tests. The full tool data is still persisted to ChatMessageModel
(covered by the eval adapter's own tests), so scrubbing here loses nothing.
"""

import pytest

from simulate.pydantic_schemas.chat import (
    ChatMessage,
    ChatRole,
    ToolCall,
    ToolCallFunction,
)
from simulate.services.futureagi_chat.service import (
    FutureAGIChatService,
    SimulatorMessage,
)


def _tool_call(call_id: str = "call_1", name: str = "get_order") -> ToolCall:
    return ToolCall(
        id=call_id,
        type="function",
        function=ToolCallFunction(name=name, arguments='{"order_id": "ORD-1"}'),
    )


@pytest.mark.unit
class TestSimulatorMessage:
    def test_plain_message_dict_shape(self):
        assert SimulatorMessage(role="user", content="hi").to_dict() == {
            "role": "user",
            "content": "hi",
        }

    def test_tool_fields_included_only_when_set(self):
        # tool_calls / tool_call_id are omitted unless explicitly provided.
        assert SimulatorMessage(role="assistant", content="hey").to_dict() == {
            "role": "assistant",
            "content": "hey",
        }
        d = SimulatorMessage(
            role="tool", content="out", tool_call_id="call_1"
        ).to_dict()
        assert d == {"role": "tool", "content": "out", "tool_call_id": "call_1"}


@pytest.mark.unit
class TestToProviderMessagesScrubbing:
    def setup_method(self):
        self.svc = FutureAGIChatService()

    def test_agent_text_turn_becomes_assistant(self):
        out = self.svc._to_provider_messages(
            [ChatMessage(role=ChatRole.USER, content="Your order shipped.")]
        )
        assert out == [{"role": "assistant", "content": "Your order shipped."}]

    def test_pure_tool_call_turn_is_scrubbed(self):
        # Empty content + tool_calls (a pure tool call) contributes nothing to
        # the persona's view.
        out = self.svc._to_provider_messages(
            [ChatMessage(role=ChatRole.ASSISTANT, content="", tool_calls=[_tool_call()])]
        )
        assert out == []

    def test_tool_result_is_scrubbed(self):
        out = self.svc._to_provider_messages(
            [
                ChatMessage(
                    role=ChatRole.TOOL, content="ORD-1 shipped", tool_call_id="call_1"
                )
            ]
        )
        assert out == []

    def test_tool_call_turn_with_text_keeps_only_text(self):
        # If a turn carries both text and tool_calls, the text survives as an
        # assistant message and the tool_calls are dropped.
        out = self.svc._to_provider_messages(
            [
                ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content="Let me check that for you.",
                    tool_calls=[_tool_call()],
                )
            ]
        )
        assert out == [
            {"role": "assistant", "content": "Let me check that for you."}
        ]
        assert "tool_calls" not in out[0]

    def test_genuinely_empty_message_is_skipped(self):
        out = self.svc._to_provider_messages(
            [
                ChatMessage(role=ChatRole.USER, content=""),
                ChatMessage(role=ChatRole.USER, content="   "),
            ]
        )
        assert out == []

    def test_full_agent_turn_yields_only_text_in_order(self):
        # A realistic multi-step agent turn: think -> tool call -> tool result
        # -> final answer. The persona should see only the two text replies,
        # in order, both as assistant, with no tool artifacts.
        out = self.svc._to_provider_messages(
            [
                ChatMessage(role=ChatRole.ASSISTANT, content="Checking your order…"),
                ChatMessage(
                    role=ChatRole.ASSISTANT, content="", tool_calls=[_tool_call()]
                ),
                ChatMessage(
                    role=ChatRole.TOOL, content="ORD-1 shipped", tool_call_id="call_1"
                ),
                ChatMessage(
                    role=ChatRole.ASSISTANT, content="It shipped yesterday."
                ),
            ]
        )
        assert out == [
            {"role": "assistant", "content": "Checking your order…"},
            {"role": "assistant", "content": "It shipped yesterday."},
        ]
        assert all("tool_calls" not in m and "tool_call_id" not in m for m in out)
