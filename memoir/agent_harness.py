######################################################################
#
# Agent harness for the Memorex CLI and tool orchestration.
#
# This module drives user input, local transcript staging, model
# responses, tool execution, and save/discard confirmation flows.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

import json
from typing import Any, Callable

from .llm import LLMClient
from .models import ChatResult, ToolCall
from .storage import MemoryStore, new_session_id
from .tools import MemoirTools
from .tracing import trace_event


class AgentHarness:
    # Main driver for chat, memory, and tool execution.

    def __init__(
        self,
        store: MemoryStore,
        llm: LLMClient,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
    ):
        # Wire the harness to storage, model, and injectable I/O functions.

        self.store = store
        self.llm = llm
        self.tools = MemoirTools(store, llm)
        self.input = input_func
        self.output = output_func
        self.session_id = new_session_id()

    def recover_previous_session(self) -> None:
        # Offer to save or discard an interrupted staged session on startup.

        if not self.store.has_current_session():
            return
        answer = self.input("I found an unsaved previous session. Save it to the memoir? [y/N] ")
        if is_yes(answer):
            self._save_confirmed(reason="Recovered previous interrupted session.")
            self.output("Saved the previous session.")
        else:
            self.store.discard_current()
            self.output("Discarded the previous session.")

    def run(self) -> int:
        # Run the interactive command loop.

        self.recover_previous_session()
        self.output("Memorex is listening. Type /quit to exit.")
        while True:
            try:
                user_text = self.input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.output("")
                self.handle_quit()
                return 0
            if not user_text:
                continue
            if user_text == "/quit":
                self.handle_quit()
                return 0
            if user_text == "/save":
                if self.store.has_current_session():
                    self._save_confirmed(reason="User requested /save.")
                    self.output("Saved and cleared the current session.")
                else:
                    self.output("There is no current session to save.")
                continue
            if user_text == "/memory":
                paths = self.tools.inspect_memory_paths()
                for name, path in paths.items():
                    self.output(f"{name}: {path}")
                continue
            self.handle_user_turn(user_text)

    def handle_user_turn(self, user_text: str) -> str:
        # Record a user turn, ask the model for a reply, and record the reply.

        self.store.append_current("user", user_text, self.session_id)
        messages = records_to_messages(self.store.recent_context())
        result = self.llm.chat(messages, user_profile=self.store.read_user_profile(), tools=True)
        text = self._handle_tool_calls(user_text, messages, result)
        if text:
            self.store.append_current("assistant", text, self.session_id)
            self.output(f"{text}\n")
        return text

    def handle_quit(self) -> None:
        # Prompt to save or discard the active session before exiting.

        if not self.store.has_current_session():
            self.output("Goodbye.")
            self.print_durable_memory_paths()
            return
        answer = self.input("Update the Memoir and User Profile based on this session before quitting? [y/N] ")
        if is_yes(answer):
            self._save_confirmed(reason="User confirmed save at /quit.")
            self.output("Saved and cleared the current session.")
        else:
            self.store.discard_current()
            self.output("Discarded the current session.")
        self.print_durable_memory_paths()

    def print_durable_memory_paths(self) -> None:
        # Print the durable memory file paths users are most likely to open.

        paths = self.tools.inspect_memory_paths()
        self.output(f"Memoir.md: {paths['Memoir.md']}")
        self.output(f"UserProfile.json: {paths['UserProfile.json']}")

    def _handle_tool_calls(self, user_text: str, messages: list[dict[str, str]], result: ChatResult) -> str:
        # Execute any model-requested tools and ask the model for a final reply.

        if not result.tool_calls:
            return result.text

        trace_event(
            "tool_calls.detected",
            {
                "count": len(result.tool_calls),
                "tool_calls": [tool_call.__dict__ for tool_call in result.tool_calls],
            },
        )
        outputs: list[dict[str, Any]] = []
        for tool_call in result.tool_calls:
            tool_result = self._execute_tool_call(user_text, tool_call)
            trace_event(
                "tool_result",
                {
                    "name": tool_call.name,
                    "call_id": tool_call.call_id,
                    "result": tool_result,
                },
            )
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id or tool_call.name,
                    "output": json.dumps(tool_result, ensure_ascii=False),
                }
            )

        final = self.llm.chat_with_tool_outputs(
            messages,
            result.raw_output,
            outputs,
            user_profile=self.store.read_user_profile(),
        )
        return final.text or result.text

    def _execute_tool_call(self, user_text: str, tool_call: ToolCall) -> dict[str, Any]:
        # Validate and dispatch a single requested tool call.

        trace_event(
            "tool_call.execute",
            {
                "name": tool_call.name,
                "call_id": tool_call.call_id,
                "arguments": tool_call.arguments,
            },
        )
        if tool_call.name == "recall":
            hint = tool_call.arguments.get("hint") or user_text
            return self.tools.recall(
                user_utterance=user_text,
                recent_context=self.store.recent_context(),
                hint=hint,
            )
        if tool_call.name == "inspect_memory_paths":
            return self.tools.inspect_memory_paths()
        if tool_call.name == "save_and_clear":
            reason = tool_call.arguments.get("reason", "Memorex suggested saving this session.")
            answer = self.input(f"Memorex suggests saving this session: {reason} Save now? [y/N] ")
            if not is_yes(answer):
                return {"saved": False, "reason": "User declined save."}
            return self._save_confirmed(
                reason=reason,
                suggested_title=tool_call.arguments.get("suggested_title"),
            )
        return {"error": f"Unknown tool: {tool_call.name}"}

    def _save_confirmed(self, reason: str, suggested_title: str | None = None) -> dict[str, Any]:
        # Run save_and_clear after the caller has obtained user confirmation.

        return self.tools.save_and_clear(reason=reason, suggested_title=suggested_title)


def records_to_messages(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    # Convert stored transcript records into Responses API message inputs.

    messages: list[dict[str, str]] = []
    for record in records:
        role = record.get("role")
        content = record.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            messages.append({"role": role, "content": content})
    return messages


def is_yes(value: str) -> bool:
    # Interpret a CLI confirmation answer.

    return value.strip().lower() in {"y", "yes"}
