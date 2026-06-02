######################################################################
#
# Tests for local tool behavior with a fake LLM client.
#
# This module verifies recall inputs, transcript size fallback, save
# behavior, and failure handling without network calls.
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
from memoir.storage import FULL_TRANSCRIPT_RECALL_LIMIT_BYTES, MemoryPaths, MemoryStore, append_text
from memoir.tools import MemoirTools


class FakeLLM(LLMClient):
    # Deterministic LLM substitute for tool tests.

    def __init__(self, fail_memoirize: bool = False):
        self.fail_memoirize = fail_memoirize
        self.last_recall_full_transcript = ""
        self.last_recall_full_transcript_used = None

    def chat(self, messages: list[dict[str, str]], tools: bool = True) -> ChatResult:
        return ChatResult(text="Tell me more.")

    def chat_with_tool_outputs(
        self,
        messages: list[dict[str, str]],
        previous_output: list[Any],
        tool_outputs: list[dict[str, Any]],
    ) -> ChatResult:
        return ChatResult(text="Ah yes, I remember.")

    def memoirize(self, records: list[dict[str, Any]], suggested_title: str | None = None) -> str:
        # Return canned memoir prose or simulate a model failure.

        if self.fail_memoirize:
            raise RuntimeError("memoirization failed")
        return "## A Saved Moment\n\nI remembered this conversation."

    def recall(
        self,
        user_utterance: str,
        recent_context: list[dict[str, Any]],
        memoir: str,
        full_transcript: str,
        full_transcript_used: bool,
        hint: str | None = None,
    ) -> dict[str, Any]:
        # Record recall inputs and return a grounded-looking fake result.

        self.last_recall_full_transcript = full_transcript
        self.last_recall_full_transcript_used = full_transcript_used
        return {
            "found": bool(memoir or full_transcript),
            "confidence": "medium",
            "summary": "A remembered conversation.",
            "date_or_session_id": None,
            "supporting_excerpts": [],
            "full_transcript_used": full_transcript_used,
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

    def test_save_and_clear_appends_memoir_and_transcript(self) -> None:
        store = self.make_store()
        store.append_current("user", "hello", "session-1")
        tools = MemoirTools(store, FakeLLM())

        result = tools.save_and_clear(reason="test")

        self.assertTrue(result["saved"])
        self.assertEqual(store.current_records(), [])
        self.assertIn("A Saved Moment", store.read_memoir())
        transcript, used = store.read_full_transcript_for_recall()
        self.assertTrue(used)
        self.assertIn('"content": "hello"', transcript)

    def test_failed_memoirization_does_not_clear_current_session(self) -> None:
        store = self.make_store()
        store.append_current("user", "hello", "session-1")
        tools = MemoirTools(store, FakeLLM(fail_memoirize=True))

        with self.assertRaises(RuntimeError):
            tools.save_and_clear(reason="test")

        self.assertEqual(len(store.current_records()), 1)
        self.assertEqual(store.read_memoir(), "")

    def test_recall_uses_full_transcript_under_limit(self) -> None:
        store = self.make_store()
        append_text(store.paths.memoir, "## Old Talk\n\nWe discussed the train.")
        append_text(store.paths.full_transcript, '{"role":"user","content":"the train"}\n')
        fake = FakeLLM()
        tools = MemoirTools(store, fake)

        result = tools.recall("remember the train?", [], "train")

        self.assertTrue(result["found"])
        self.assertTrue(fake.last_recall_full_transcript_used)
        self.assertIn("train", fake.last_recall_full_transcript)

    def test_recall_skips_full_transcript_over_limit(self) -> None:
        store = self.make_store()
        append_text(store.paths.memoir, "## Old Talk\n\nWe discussed the train.")
        append_text(store.paths.full_transcript, "x" * (FULL_TRANSCRIPT_RECALL_LIMIT_BYTES + 1))
        fake = FakeLLM()
        tools = MemoirTools(store, fake)

        result = tools.recall("remember the train?", [], "train")

        self.assertTrue(result["found"])
        self.assertFalse(fake.last_recall_full_transcript_used)
        self.assertEqual(fake.last_recall_full_transcript, "")


if __name__ == "__main__":
    unittest.main()
