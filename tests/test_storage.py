######################################################################
#
# Tests for local memoir file storage behavior.
#
# This module verifies JSONL persistence, recall size limits, save
# clearing, and memory directory selection.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from memoir.storage import (
    FULL_TRANSCRIPT_RECALL_LIMIT_BYTES,
    MemoryPaths,
    MemoryStore,
    append_text,
    default_data_dir,
)


class MemoryStoreTests(unittest.TestCase):
    # Exercise JSONL storage, recall limits, and data directory selection.

    def make_store(self) -> MemoryStore:
        # Create an isolated temporary memory store for a test.

        self.tmp = tempfile.TemporaryDirectory()
        return MemoryStore(MemoryPaths.from_data_dir(Path(self.tmp.name)))

    def tearDown(self) -> None:
        # Clean up any temporary memory directory created by a test.

        tmp = getattr(self, "tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def test_append_and_read_current_session(self) -> None:
        store = self.make_store()
        store.append_current("user", "hello", "session-1")
        store.append_current("assistant", "tell me more", "session-1")

        records = store.current_records()

        self.assertEqual([record["role"] for record in records], ["user", "assistant"])
        self.assertEqual(records[0]["content"], "hello")

    def test_append_saved_session_clears_current(self) -> None:
        store = self.make_store()
        store.append_current("user", "hello", "session-1")
        records = store.current_records()

        store.append_saved_session(records, "## Entry\n\nI said hello.")

        self.assertEqual(store.current_records(), [])
        self.assertIn("I said hello.", store.read_memoir())
        self.assertEqual(len(store.read_full_transcript_for_recall()[0].splitlines()), 1)

    def test_full_transcript_recall_limit(self) -> None:
        store = self.make_store()
        append_text(store.paths.full_transcript, "x" * (FULL_TRANSCRIPT_RECALL_LIMIT_BYTES + 1))

        transcript, used = store.read_full_transcript_for_recall()

        self.assertEqual(transcript, "")
        self.assertFalse(used)

    def test_default_data_dir_uses_home_memorex(self) -> None:
        self.assertEqual(default_data_dir(), Path.home() / ".memorex")

    def test_default_data_dir_supports_env_override(self) -> None:
        with patch.dict("os.environ", {"MEMOIR_DATA_DIR": "~/custom-memoir"}):
            self.assertEqual(default_data_dir(), Path.home() / "custom-memoir")


if __name__ == "__main__":
    unittest.main()
