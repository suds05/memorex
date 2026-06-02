######################################################################
#
# Command-line entrypoint wiring storage, model client, and app loop.
#
# This module is the main entrypoint for the memoir CLI application,
# which provides a conversational interface for users to interact
# with their memory store and LLM client.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

from .app import MemoirApp
from .llm import OpenAIResponsesClient
from .storage import MemoryPaths, MemoryStore, default_data_dir


def main() -> int:
    # Start the memoir CLI with default storage and OpenAI client settings.

    paths = MemoryPaths.from_data_dir(default_data_dir())
    store = MemoryStore(paths)
    llm = OpenAIResponsesClient()
    app = MemoirApp(store, llm)
    return app.run()
