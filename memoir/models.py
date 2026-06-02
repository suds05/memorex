######################################################################
#
# Shared dataclasses for model responses and requested tool calls.
#
# This module contains small normalized data structures used between
# the OpenAI client wrapper and the CLI orchestrator.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    # A function tool request returned by the LLM.

    name: str
    arguments: dict[str, Any]
    call_id: str | None = None


@dataclass(frozen=True)
class ChatResult:
    # A normalized chat response with text, tool calls, and raw API output.

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_output: list[Any] = field(default_factory=list)
