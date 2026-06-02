######################################################################
#
# Tests for local memoir file storage behavior.
#
# This module verifies JSONL persistence, profile storage, save clearing,
# and memory directory selection.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from memoir.storage import (
    MemoryPaths,
    MemoryStore,
    append_text,
    default_data_dir,
)


class MemoryStoreTests(unittest.TestCase):
    # Exercise JSONL storage, profile storage, and data directory selection.

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

        store.append_saved_session(
            records,
            "## Entry\n\nI said hello.",
            user_profile={"preferences": ["likes concise replies"], "recurring_themes": [], "important_people": [], "goals": [], "open_threads": []},
        )

        self.assertEqual(store.current_records(), [])
        self.assertIn("I said hello.", store.read_memoir())
        self.assertIn("likes concise replies", store.read_user_profile_text())

    def test_read_user_profile_returns_default_when_missing(self) -> None:
        store = self.make_store()

        profile = store.read_user_profile()

        self.assertEqual(profile["preferences"], [])
        self.assertEqual(profile["open_threads"], [])

    def test_default_data_dir_uses_home_memorex(self) -> None:
        self.assertEqual(default_data_dir(), Path.home() / ".memorex")

    def test_default_data_dir_supports_env_override(self) -> None:
        with patch.dict("os.environ", {"MEMOIR_DATA_DIR": "~/custom-memoir"}):
            self.assertEqual(default_data_dir(), Path.home() / "custom-memoir")


if __name__ == "__main__":
    unittest.main()
