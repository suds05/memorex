######################################################################
#
# Local tool implementations exposed to the LLM through the CLI orchestrator.
#
# This module implements recall, save_and_clear, and memory path
# inspection while keeping file access under application control.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

from typing import Any

from .llm import LLMClient
from .storage import MemoryStore


class MemoirTools:
    # Read-only and confirmed-write tools for memoir memory operations.

    def __init__(self, store: MemoryStore, llm: LLMClient):
        # Bind tools to a memory store and model client.

        self.store = store
        self.llm = llm

    def recall(self, user_utterance: str, recent_context: list[dict[str, Any]], hint: str | None = None) -> dict[str, Any]:
        # Use the LLM to recall saved memory relevant to the current utterance.

        full_transcript, full_transcript_used = self.store.read_full_transcript_for_recall()
        return self.llm.recall(
            user_utterance=user_utterance,
            recent_context=recent_context,
            memoir=self.store.read_memoir(),
            full_transcript=full_transcript,
            full_transcript_used=full_transcript_used,
            hint=hint,
        )

    def save_and_clear(self, reason: str = "", suggested_title: str | None = None) -> dict[str, Any]:
        # Generate memoir prose, archive raw records, and clear staging.

        records = self.store.current_records()
        if not records:
            return {"saved": False, "reason": "No current session to save."}
        memoir_entry = self.llm.memoirize(records, suggested_title=suggested_title)
        self.store.append_saved_session(records, memoir_entry)
        return {
            "saved": True,
            "reason": reason,
            "paths": self.store.inspect_paths(),
        }

    def inspect_memory_paths(self) -> dict[str, str]:
        # Return local memory file paths.

        return self.store.inspect_paths()
