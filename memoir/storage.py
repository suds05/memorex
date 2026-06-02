######################################################################
#
# Local file storage for staged sessions, transcript archive, and memoir prose.
#
# This module owns the ~/.memorex memory layout, JSONL transcript
# helpers, recall size limit, and save/discard file operations.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

FULL_TRANSCRIPT_RECALL_LIMIT_BYTES = 100_000


def utc_now_iso() -> str:
    # Return the current UTC timestamp in ISO-8601 format.

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_session_id() -> str:
    # Create a unique identifier for a CLI chat session.

    return str(uuid4())


@dataclass(frozen=True)
class MemoryPaths:
    # Filesystem paths for all memoir memory files.

    data_dir: Path
    current_session: Path
    full_transcript: Path
    memoir: Path

    @classmethod
    def from_data_dir(cls, data_dir: Path) -> "MemoryPaths":
        # Build the standard memory file layout under a data directory.

        return cls(
            data_dir=data_dir,
            current_session=data_dir / "CurrentSession.jsonl",
            full_transcript=data_dir / "FullTranscript.jsonl",
            memoir=data_dir / "Memoir.md",
        )


class MemoryStore:
    # Read and write local memoir memory files.

    def __init__(self, paths: MemoryPaths):
        # Create the data directory if needed and remember file paths.

        self.paths = paths
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)

    def append_current(self, role: str, content: str, session_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        # Append one user or assistant turn to the staged current session.

        record = {
            "timestamp": utc_now_iso(),
            "session_id": session_id,
            "role": role,
            "content": content,
        }
        if metadata:
            record["metadata"] = metadata
        append_jsonl(self.paths.current_session, [record])
        return record

    def current_records(self) -> list[dict[str, Any]]:
        # Read all staged records for the active session.

        return read_jsonl(self.paths.current_session)

    def has_current_session(self) -> bool:
        # Return whether a non-empty staged session exists.

        return self.paths.current_session.exists() and self.paths.current_session.stat().st_size > 0

    def recent_context(self, limit: int = 12) -> list[dict[str, Any]]:
        # Read the most recent staged turns for chat context.

        return self.current_records()[-limit:]

    def read_memoir(self) -> str:
        # Read the readable memoir file, or return empty text if absent.

        return read_text(self.paths.memoir)

    def read_full_transcript_for_recall(self) -> tuple[str, bool]:
        # Read the raw transcript for recall when it is under the v1 size limit.

        path = self.paths.full_transcript
        if not path.exists():
            return "", True
        if path.stat().st_size > FULL_TRANSCRIPT_RECALL_LIMIT_BYTES:
            return "", False
        return read_text(path), True

    def append_saved_session(self, records: list[dict[str, Any]], memoir_entry: str) -> None:
        # Commit a session to memoir and full transcript, then clear staging.

        if not records:
            return
        append_text(self.paths.memoir, ensure_trailing_newline(memoir_entry) + "\n")
        append_jsonl(self.paths.full_transcript, records)
        clear_file(self.paths.current_session)

    def discard_current(self) -> None:
        # Clear the staged current session without saving it.

        clear_file(self.paths.current_session)

    def inspect_paths(self) -> dict[str, str]:
        # Return absolute paths for all memory files.

        return {
            "CurrentSession.jsonl": str(self.paths.current_session.resolve()),
            "FullTranscript.jsonl": str(self.paths.full_transcript.resolve()),
            "Memoir.md": str(self.paths.memoir.resolve()),
        }


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    # Append records to a JSONL file.

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    # Read a JSONL file into dictionaries, validating each non-empty line.

    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} at line {line_number}") from exc
    return records


def read_text(path: Path) -> str:
    # Read a UTF-8 text file, returning empty text when it does not exist.

    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    # Append UTF-8 text to a file, creating parent directories if needed.

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text)


def clear_file(path: Path) -> None:
    # Create or truncate a UTF-8 text file.

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def ensure_trailing_newline(text: str) -> str:
    # Normalize text to end with exactly one newline.

    return text.rstrip() + "\n"


def default_data_dir() -> Path:
    # Return the configured memory directory, defaulting to ~/.memorex.

    configured = os.environ.get("MEMOIR_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".memorex"
