######################################################################
#
# Debug tracing helpers for memoir agent execution.
#
# This module prints opt-in model and tool traces to stderr when
# MEMOIR_DEBUG=1 is set in the environment.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

import json
import os
import sys
from typing import Any

DIM = "\033[2m"
RESET = "\033[0m"


# Return whether debug tracing is enabled.
def debug_enabled() -> bool:
    return os.environ.get("MEMOIR_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


# Return whether ANSI color should be used for debug output.
def color_enabled() -> bool:
    return sys.stderr.isatty() and not os.environ.get("NO_COLOR")


# Emit a structured debug event to stderr when tracing is enabled.
def trace_event(event: str, payload: dict[str, Any]) -> None:
    if not debug_enabled():
        return
    header = f"[memoir:debug] {event}"
    body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if color_enabled():
        header = f"{DIM}{header}{RESET}"
        body = f"{DIM}{body}{RESET}"
    print(header, file=sys.stderr)
    print(body, file=sys.stderr)
