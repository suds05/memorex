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

from memoir.agent_harness import AgentHarness
from memoir.llm import LLMClient
from memoir.models import ChatResult, ToolCall
from memoir.storage import MemoryPaths, MemoryStore
from memoir.tracing import color_enabled


class FakeLLM(LLMClient):
    # Deterministic LLM substitute for app-level tests.

    def __init__(self):
        self.next_chat = ChatResult(text="Tell me more.")
        self.last_chat_user_profile = None

    def chat(self, messages: list[dict[str, str]], user_profile: dict[str, Any] | None = None, tools: bool = True) -> ChatResult:
        # Return the preconfigured chat result.

        self.last_chat_user_profile = user_profile
        return self.next_chat

    def chat_with_tool_outputs(
        self,
        messages: list[dict[str, str]],
        previous_output: list[Any],
        tool_outputs: list[dict[str, Any]],
        user_profile: dict[str, Any] | None = None,
    ) -> ChatResult:
        # Return a canned final response after tool execution.

        self.last_chat_user_profile = user_profile
        return ChatResult(text="Ah yes. You were mentioning the train.")

    def memoirize(self, records: list[dict[str, Any]], suggested_title: str | None = None) -> str:
        # Return canned memoir prose.

        return "## Saved\n\nI saved this."

    def update_user_profile(
        self,
        records: list[dict[str, Any]],
        memoir: str,
        user_profile: dict[str, Any],
    ) -> dict[str, Any]:
        # Return a canned profile update.

        return {
            **user_profile,
            "preferences": [*user_profile.get("preferences", []), "likes practical suggestions"],
        }

    def recall(
        self,
        user_utterance: str,
        recent_context: list[dict[str, Any]],
        memoir: str,
        user_profile: dict[str, Any],
        hint: str | None = None,
    ) -> dict[str, Any]:
        # Return a successful fake recall result.

        return {
            "found": True,
            "confidence": "high",
            "summary": "The train conversation.",
            "date_or_session_id": None,
            "supporting_excerpts": [],
        }


class AgentHarnessTests(unittest.TestCase):
    # Exercise the agent harness using fake I/O and a fake model.

    def make_app(self, inputs: list[str]) -> tuple[AgentHarness, MemoryStore, list[str]]:
        # Create a harness wired to temporary storage and scripted user input.

        self.tmp = tempfile.TemporaryDirectory()
        store = MemoryStore(MemoryPaths.from_data_dir(Path(self.tmp.name)))
        output: list[str] = []
        iterator = iter(inputs)
        app = AgentHarness(
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
        self.assertEqual(app.llm.last_chat_user_profile["preferences"], [])
        self.assertEqual(output, ["Tell me more.\n"])
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

    def test_quit_prints_memory_paths_after_discard(self) -> None:
        app, store, output = self.make_app(["n"])
        store.append_current("user", "current session", "session-1")

        app.handle_quit()

        self.assertIn("Discarded the current session.", output)
        self.assertTrue(any(line.startswith("Memoir.md: ") for line in output))
        self.assertTrue(any(line.startswith("UserProfile.json: ") for line in output))

    def test_quit_prints_memory_paths_without_current_session(self) -> None:
        app, _store, output = self.make_app([])

        app.handle_quit()

        self.assertIn("Goodbye.", output)
        self.assertTrue(any(line.startswith("Memoir.md: ") for line in output))
        self.assertTrue(any(line.startswith("UserProfile.json: ") for line in output))

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
        self.assertIn("Ah yes. You were mentioning the train.\n", output)
        self.assertEqual(app.llm.last_chat_user_profile["preferences"], [])

    def test_debug_trace_does_not_change_chat_behavior(self) -> None:
        with patch.dict("os.environ", {"MEMOIR_DEBUG": "1"}):
            app, store, output = self.make_app([])

            text = app.handle_user_turn("I saw the old station.")

        self.assertEqual(text, "Tell me more.")
        self.assertEqual([record["role"] for record in store.current_records()], ["user", "assistant"])
        self.assertEqual(output, ["Tell me more.\n"])

    def test_no_color_disables_debug_color(self) -> None:
        with patch.dict("os.environ", {"NO_COLOR": "1"}):
            self.assertFalse(color_enabled())


if __name__ == "__main__":
    unittest.main()
