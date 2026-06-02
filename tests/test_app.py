######################################################################
#
# Tests for CLI orchestration, recovery, and tool-confirmation behavior.
#
# This module verifies the app loop helpers using scripted input,
# captured output, temporary storage, and a fake model client.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from typing import Any

from memoir.app import MemoirApp
from memoir.llm import LLMClient
from memoir.models import ChatResult, ToolCall
from memoir.storage import MemoryPaths, MemoryStore
from memoir.tracing import color_enabled


class FakeLLM(LLMClient):
    # Deterministic LLM substitute for app-level tests.

    def __init__(self):
        self.next_chat = ChatResult(text="Tell me more.")

    def chat(self, messages: list[dict[str, str]], tools: bool = True) -> ChatResult:
        # Return the preconfigured chat result.

        return self.next_chat

    def chat_with_tool_outputs(
        self,
        messages: list[dict[str, str]],
        previous_output: list[Any],
        tool_outputs: list[dict[str, Any]],
    ) -> ChatResult:
        # Return a canned final response after tool execution.

        return ChatResult(text="Ah yes. You were mentioning the train.")

    def memoirize(self, records: list[dict[str, Any]], suggested_title: str | None = None) -> str:
        # Return canned memoir prose.

        return "## Saved\n\nI saved this."

    def recall(
        self,
        user_utterance: str,
        recent_context: list[dict[str, Any]],
        memoir: str,
        full_transcript: str,
        full_transcript_used: bool,
        hint: str | None = None,
    ) -> dict[str, Any]:
        # Return a successful fake recall result.

        return {
            "found": True,
            "confidence": "high",
            "summary": "The train conversation.",
            "date_or_session_id": None,
            "supporting_excerpts": [],
            "full_transcript_used": full_transcript_used,
        }


class AppTests(unittest.TestCase):
    # Exercise the CLI app using fake I/O and a fake model.

    def make_app(self, inputs: list[str]) -> tuple[MemoirApp, MemoryStore, list[str]]:
        # Create an app wired to temporary storage and scripted user input.

        self.tmp = tempfile.TemporaryDirectory()
        store = MemoryStore(MemoryPaths.from_data_dir(Path(self.tmp.name)))
        output: list[str] = []
        iterator = iter(inputs)
        app = MemoirApp(
            store,
            FakeLLM(),
            input_func=lambda prompt="": next(iterator),
            output_func=output.append,
        )
        return app, store, output

    def tearDown(self) -> None:
        # Clean up any temporary memory directory created by a test.

        tmp = getattr(self, "tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def test_handle_user_turn_records_user_and_assistant(self) -> None:
        app, store, output = self.make_app([])

        text = app.handle_user_turn("I miss the old station.")

        self.assertEqual(text, "Tell me more.")
        self.assertEqual(output, ["Tell me more."])
        self.assertEqual([record["role"] for record in store.current_records()], ["user", "assistant"])

    def test_recover_previous_session_save(self) -> None:
        app, store, output = self.make_app(["y"])
        store.append_current("user", "old session", "session-1")

        app.recover_previous_session()

        self.assertEqual(store.current_records(), [])
        self.assertIn("Saved the previous session.", output)
        self.assertIn("Saved", store.read_memoir())

    def test_recover_previous_session_discard(self) -> None:
        app, store, output = self.make_app(["n"])
        store.append_current("user", "old session", "session-1")

        app.recover_previous_session()

        self.assertEqual(store.current_records(), [])
        self.assertIn("Discarded the previous session.", output)
        self.assertEqual(store.read_memoir(), "")

    def test_llm_requested_save_requires_confirmation(self) -> None:
        app, store, output = self.make_app(["n"])
        app.llm.next_chat = ChatResult(
            text="",
            tool_calls=[
                ToolCall(
                    name="save_and_clear",
                    arguments={"reason": "This feels meaningful.", "suggested_title": "A Moment"},
                    call_id="call-1",
                )
            ],
        )

        app.handle_user_turn("That mattered to me.")

        self.assertNotEqual(store.current_records(), [])
        self.assertEqual(store.read_memoir(), "")
        self.assertIn("Ah yes. You were mentioning the train.", output)

    def test_debug_trace_does_not_change_chat_behavior(self) -> None:
        with patch.dict("os.environ", {"MEMOIR_DEBUG": "1"}):
            app, store, output = self.make_app([])

            text = app.handle_user_turn("I saw the old station.")

        self.assertEqual(text, "Tell me more.")
        self.assertEqual([record["role"] for record in store.current_records()], ["user", "assistant"])
        self.assertEqual(output, ["Tell me more."])

    def test_no_color_disables_debug_color(self) -> None:
        with patch.dict("os.environ", {"NO_COLOR": "1"}):
            self.assertFalse(color_enabled())


if __name__ == "__main__":
    unittest.main()
