######################################################################
#
# Local file storage for staged sessions, memoir prose, and user profile.
#
# This module owns the ~/.memorex memory layout, JSONL staging
# helpers, atomic save staging, and save/discard file operations.
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

DEFAULT_USER_PROFILE: dict[str, Any] = {
    "preferences": [],
    "recurring_themes": [],
    "important_people": [],
    "goals": [],
    "open_threads": [],
}


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
    memoir: Path
    user_profile: Path
    save_marker: Path

    @classmethod
    def from_data_dir(cls, data_dir: Path) -> "MemoryPaths":
        # Build the standard memory file layout under a data directory.

        return cls(
            data_dir=data_dir,
            current_session=data_dir / "CurrentSession.jsonl",
            memoir=data_dir / "Memoir.md",
            user_profile=data_dir / "UserProfile.json",
            save_marker=data_dir / ".save_complete",
        )


class MemoryStore:
    # Read and write local memoir memory files.

    def __init__(self, paths: MemoryPaths):
        # Create the data directory if needed and remember file paths.

        self.paths = paths
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        self.recover_completed_save()

    def recover_completed_save(self) -> None:
        # Finish cleanup if a previous save committed but crashed before clearing staging.

        if self.paths.save_marker.exists():
            clear_file_atomic(self.paths.current_session)
            self.paths.save_marker.unlink(missing_ok=True)
            fsync_dir(self.paths.save_marker.parent)

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

    def read_user_profile(self) -> dict[str, Any]:
        # Read the structured user profile, or return an empty default profile.

        if not self.paths.user_profile.exists():
            return dict(DEFAULT_USER_PROFILE)
        try:
            profile = json.loads(read_text(self.paths.user_profile))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {self.paths.user_profile}") from exc
        if not isinstance(profile, dict):
            raise ValueError(f"Expected object JSON in {self.paths.user_profile}")
        return {**DEFAULT_USER_PROFILE, **profile}

    def read_user_profile_text(self) -> str:
        # Read the user profile as formatted JSON for model context.

        return json.dumps(self.read_user_profile(), ensure_ascii=False, indent=2)

    def append_saved_session(self, records: list[dict[str, Any]], memoir_entry: str, user_profile: dict[str, Any] | None = None) -> None:
        # Commit a session to memoir/profile, then clear staging.

        if not records:
            return
        updates = {self.paths.memoir: read_text(self.paths.memoir) + ensure_trailing_newline(memoir_entry) + "\n"}
        if user_profile is not None:
            updates[self.paths.user_profile] = json.dumps(user_profile, ensure_ascii=False, indent=2) + "\n"
        atomic_replace_updates_and_clear(
            updates=updates,
            clear_path=self.paths.current_session,
            marker_path=self.paths.save_marker,
        )

    def discard_current(self) -> None:
        # Clear the staged current session without saving it.

        clear_file(self.paths.current_session)

    def inspect_paths(self) -> dict[str, str]:
        # Return absolute paths for all memory files.

        return {
            "CurrentSession.jsonl": str(self.paths.current_session.resolve()),
            "Memoir.md": str(self.paths.memoir.resolve()),
            "UserProfile.json": str(self.paths.user_profile.resolve()),
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


def clear_file_atomic(path: Path) -> None:
    # Create or truncate a UTF-8 text file using atomic replacement.

    atomic_replace_text(path, "")


def ensure_trailing_newline(text: str) -> str:
    # Normalize text to end with exactly one newline.

    return text.rstrip() + "\n"


def atomic_replace_updates_and_clear(updates: dict[Path, str], clear_path: Path, marker_path: Path) -> None:
    # Atomically replace durable files, mark completion, then clear staging.

    temp_paths: list[Path] = []
    replacements: list[tuple[Path, Path]] = []
    try:
        for target_path, new_text in updates.items():
            temp_path = sibling_temp_path(target_path)
            temp_paths.append(temp_path)
            write_text_fsync(temp_path, new_text)
            replacements.append((temp_path, target_path))

        for temp_path, target_path in replacements:
            os.replace(temp_path, target_path)
            fsync_dir(target_path.parent)

        write_marker_atomic(marker_path)
        if marker_path.exists():
            clear_file_atomic(clear_path)
            marker_path.unlink(missing_ok=True)
            fsync_dir(marker_path.parent)
    finally:
        for temp_path in temp_paths:
            temp_path.unlink(missing_ok=True)


def atomic_replace_text(path: Path, text: str) -> None:
    # Atomically replace a text file with new UTF-8 content.

    temp_path = sibling_temp_path(path)
    try:
        write_text_fsync(temp_path, text)
        os.replace(temp_path, path)
        fsync_dir(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def write_marker_atomic(path: Path) -> None:
    # Atomically write a save-completion marker.

    atomic_replace_text(path, utc_now_iso() + "\n")


def sibling_temp_path(path: Path) -> Path:
    # Create a unique temp path beside the target for same-filesystem replacement.

    return path.with_name(f".{path.name}.{uuid4()}.tmp")


def write_text_fsync(path: Path, text: str) -> None:
    # Write text and fsync it so an atomic rename has durable source bytes.

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def fsync_dir(path: Path) -> None:
    # Fsync a directory so file replacement metadata is durable where supported.

    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def default_data_dir() -> Path:
    # Return the configured memory directory, defaulting to ~/.memorex.

    configured = os.environ.get("MEMOIR_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".memorex"
