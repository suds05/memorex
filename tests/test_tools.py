######################################################################
#
# Tests for local tool behavior with a fake LLM client.
#
# This module verifies recall inputs, profile updates, save behavior,
# and failure handling without network calls.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from memoir.llm import LLMClient
from memoir.models import ChatResult
from memoir.storage import MemoryPaths, MemoryStore, append_text
from memoir.tools import MemoirTools


class FakeLLM(LLMClient):
    # Deterministic LLM substitute for tool tests.

    def __init__(self, fail_memoirize: bool = False):
        self.fail_memoirize = fail_memoirize
        self.fail_profile_update = False
        self.last_recall_user_profile = {}

    def chat(self, messages: list[dict[str, str]], tools: bool = True) -> ChatResult:
        return ChatResult(text="Tell me more.")

    def chat_with_tool_outputs(
        self,
        messages: list[dict[str, str]],
        previous_output: list[Any],
        tool_outputs: list[dict[str, Any]],
        user_profile: dict[str, Any] | None = None,
    ) -> ChatResult:
        return ChatResult(text="Ah yes, I remember.")

    def memoirize(self, records: list[dict[str, Any]], suggested_title: str | None = None) -> str:
        # Return canned memoir prose or simulate a model failure.

        if self.fail_memoirize:
            raise RuntimeError("memoirization failed")
        return "## A Saved Moment\n\nI remembered this conversation."

    def update_user_profile(
        self,
        records: list[dict[str, Any]],
        memoir: str,
        user_profile: dict[str, Any],
    ) -> dict[str, Any]:
        if self.fail_profile_update:
            raise RuntimeError("profile update failed")
        return {
            **user_profile,
            "preferences": [*user_profile.get("preferences", []), "likes concise replies"],
        }

    def recall(
        self,
        user_utterance: str,
        recent_context: list[dict[str, Any]],
        memoir: str,
        user_profile: dict[str, Any],
        hint: str | None = None,
    ) -> dict[str, Any]:
        # Record recall inputs and return a grounded-looking fake result.

        self.last_recall_user_profile = user_profile
        return {
            "found": bool(memoir or user_profile.get("preferences")),
            "confidence": "medium",
            "summary": "A remembered conversation.",
            "date_or_session_id": None,
            "supporting_excerpts": [],
        }


class ToolTests(unittest.TestCase):
    # Exercise save, recall, and failure behavior for memoir tools.

    def make_store(self) -> MemoryStore:
        # Create an isolated temporary memory store for a test.

        self.tmp = tempfile.TemporaryDirectory()
        return MemoryStore(MemoryPaths.from_data_dir(Path(self.tmp.name)))

    def tearDown(self) -> None:
        # Clean up any temporary memory directory created by a test.

        tmp = getattr(self, "tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def test_save_and_clear_appends_memoir_and_updates_profile(self) -> None:
        store = self.make_store()
        store.append_current("user", "hello", "session-1")
        tools = MemoirTools(store, FakeLLM())

        result = tools.save_and_clear(reason="test")

        self.assertTrue(result["saved"])
        self.assertTrue(result["profile_updated"])
        self.assertEqual(store.current_records(), [])
        self.assertIn("A Saved Moment", store.read_memoir())
        self.assertIn("likes concise replies", store.read_user_profile()["preferences"])

    def test_failed_memoirization_does_not_clear_current_session(self) -> None:
        store = self.make_store()
        store.append_current("user", "hello", "session-1")
        tools = MemoirTools(store, FakeLLM(fail_memoirize=True))

        with self.assertRaises(RuntimeError):
            tools.save_and_clear(reason="test")

        self.assertEqual(len(store.current_records()), 1)
        self.assertEqual(store.read_memoir(), "")

    def test_profile_update_failure_does_not_block_memoir_save(self) -> None:
        store = self.make_store()
        fake = FakeLLM()
        fake.fail_profile_update = True
        tools = MemoirTools(store, fake)
        store.append_current("user", "hello", "session-1")

        result = tools.save_and_clear(reason="test")

        self.assertTrue(result["saved"])
        self.assertFalse(result["profile_updated"])
        self.assertEqual(store.current_records(), [])
        self.assertIn("A Saved Moment", store.read_memoir())

    def test_recall_uses_memoir_and_user_profile(self) -> None:
        store = self.make_store()
        append_text(store.paths.memoir, "## Old Talk\n\nWe discussed the train.")
        store.append_saved_session(
            [{"role": "user", "content": "profile seed", "session_id": "session-1", "timestamp": "now"}],
            "## Profile Seed",
            user_profile={"preferences": ["likes practical suggestions"], "recurring_themes": [], "important_people": [], "goals": [], "open_threads": []},
        )
        fake = FakeLLM()
        tools = MemoirTools(store, fake)

        result = tools.recall("remember the train?", [], "train")

        self.assertTrue(result["found"])
        self.assertIn("likes practical suggestions", fake.last_recall_user_profile["preferences"])


if __name__ == "__main__":
    unittest.main()
