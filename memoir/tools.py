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

        return self.llm.recall(
            user_utterance=user_utterance,
            recent_context=recent_context,
            memoir=self.store.read_memoir(),
            user_profile=self.store.read_user_profile(),
            hint=hint,
        )

    def save_and_clear(self, reason: str = "", suggested_title: str | None = None) -> dict[str, Any]:
        # Generate memoir prose, update profile when possible, and clear staging.

        records = self.store.current_records()
        if not records:
            return {"saved": False, "reason": "No current session to save."}
        memoir_entry = self.llm.memoirize(records, suggested_title=suggested_title)
        profile_updated = True
        try:
            user_profile = self.llm.update_user_profile(
                records=records,
                memoir=self.store.read_memoir() + "\n" + memoir_entry,
                user_profile=self.store.read_user_profile(),
            )
        except Exception:
            profile_updated = False
            user_profile = None
        self.store.append_saved_session(records, memoir_entry, user_profile=user_profile)
        return {
            "saved": True,
            "reason": reason,
            "profile_updated": profile_updated,
            "paths": self.store.inspect_paths(),
        }

    def inspect_memory_paths(self) -> dict[str, str]:
        # Return local memory file paths.

        return self.store.inspect_paths()
