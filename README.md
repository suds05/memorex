# Memoir Agent CLI

## Summary
Build a Python CLI called `memoir` for a reflective listener agent. It chats with the user, records the active session in `CurrentSession.jsonl`, saves approved sessions into both `Memoir.md` and `FullTranscript.jsonl`, and can recall saved earlier conversations when the user refers to them.

Use the standard OpenAI Python SDK with the Responses API, not the Agents SDK. Default to `gpt-5.4-mini`, configurable via `OPENAI_MODEL`.

## Requirements
- The agent presents as a curious, reflective listener who nudges the user to express themselves.
- The agent avoids therapy, diagnosis, and heavy advice unless the user explicitly asks.
- Every active turn is written to `CurrentSession.jsonl` as staging memory.
- Saved sessions are appended to `FullTranscript.jsonl` with full-fidelity raw conversation records.
- Saved sessions are also converted into dated readable entries in `Memoir.md`.
- The user can trigger saving with `/save`.
- The agent may suggest saving at natural moments, but saving requires explicit user confirmation.
- On `/quit`, the CLI asks whether to save the active session.
- On startup, if an interrupted `CurrentSession.jsonl` exists, the CLI asks whether to save or discard it before starting a new session.
- `/memory` prints the paths for `CurrentSession.jsonl`, `FullTranscript.jsonl`, and `Memoir.md`.
- The user can refer to earlier saved conversations, such as "remember when we talked about...", and the agent should attempt to recall the relevant prior discussion.
- Recall must be grounded in saved memory. If no likely match is found, the agent should say it does not remember clearly and invite the user to say more.
- For v1, full transcript recall only includes `FullTranscript.jsonl` when it is at or below `100_000` bytes. Above that limit, recall falls back to `Memoir.md` only and reports that exact transcript recall was skipped.

## Agent Behavior
- Keep replies short, warm, and conversational.
- Prefer reflection plus one open-ended follow-up question.
- Do not over-summarize the user during the live conversation.
- Preserve uncertainty and avoid inventing details in generated memoir entries.
- Treat save operations as user-controlled, not autonomous.
- When recalling, distinguish remembered facts from inference and avoid pretending certainty when memory is vague.
- If `FullTranscript.jsonl` exceeds the v1 recall limit, the agent may say exact transcript recall is unavailable and continue from `Memoir.md`.

## Key Implementation Aspects
- Scaffold a small Python project with a CLI entrypoint runnable as `python -m memoir`.
- Use the standard `openai` Python package and `OpenAI().responses.create(...)`.
- Do not use the OpenAI Agents SDK for v1.
- Store data under a local `data/` directory:
  - `CurrentSession.jsonl`
  - `FullTranscript.jsonl`
  - `Memoir.md`
- Use append-only JSONL for transcript durability.
- Use the local transcript as the source of truth rather than relying only on OpenAI-hosted conversation state.
- Send recent/current session context to the Responses API for chat replies.
- Define `FULL_TRANSCRIPT_RECALL_LIMIT_BYTES = 100_000`.
- Clear `CurrentSession.jsonl` only after both `Memoir.md` and `FullTranscript.jsonl` are successfully updated.
- Configure the model with `OPENAI_MODEL`, defaulting to `gpt-5.4-mini`.
- Require `OPENAI_API_KEY` for real OpenAI-backed chat.

### Tool Orchestration
- Tools are implemented in the Python CLI orchestrator.
- The LLM may request tools through Responses API function/tool calls.
- The orchestrator validates the requested tool name and arguments.
- The orchestrator executes allowed tools and sends tool results back to the model when needed.
- The model never directly reads or writes files.
- `save_and_clear` always requires explicit user confirmation before file writes, even if the LLM requests it.

### Tools
- `recall`
  - Purpose: use an LLM to identify what saved prior conversation the user is referring to.
  - Inputs: current user utterance, recent current-session context, and optional recall hint.
  - Memory context: pass `Memoir.md`; also pass `FullTranscript.jsonl` only when its size is `<= 100_000` bytes.
  - Prompt: separate recall-specific prompt that asks the model to find grounded matches, avoid guessing, and return a structured result.
  - Reads: `Memoir.md` and, when under the size threshold, `FullTranscript.jsonl`.
  - Writes: nothing.
  - Output: structured result with `found`, `confidence`, `summary`, `date/session_id` when known, optional supporting excerpts, and `full_transcript_used`.
  - Failure behavior: if no grounded match is found, return `found=false`; if the transcript is over the limit, set `full_transcript_used=false` and continue with `Memoir.md`.
  - Use when the user says things like "remember when," "the other day," "last time," or otherwise refers to saved prior conversation.
- `save_and_clear`
  - Purpose: commit the current staged session into long-term memory, then clear the staging file.
  - Inputs: reason for saving and optional suggested title/theme.
  - LLM step: use a separate memoirization prompt to convert `CurrentSession.jsonl` into first-person readable memoir prose for `Memoir.md`.
  - Prompt: preserve the user's meaning, avoid inventing facts, keep uncertainty intact, and write a dated memoir entry.
  - Deterministic file step: append the exact raw session records to `FullTranscript.jsonl`.
  - Reads: `CurrentSession.jsonl`.
  - Writes: only after explicit user confirmation; appends generated prose to `Memoir.md`, appends raw records to `FullTranscript.jsonl`, then clears `CurrentSession.jsonl`.
  - Output: save status and file paths updated.
  - Failure behavior: if memoirization or either append fails, do not clear `CurrentSession.jsonl`.
  - Use when the user runs `/save`, confirms a save at `/quit`, confirms saving an interrupted previous session on startup, or accepts an agent suggestion to save.
- `inspect_memory_paths`
  - Purpose: report where memory files live.
  - Inputs: none.
  - Reads: filesystem path configuration.
  - Writes: nothing.
  - Output: paths for `CurrentSession.jsonl`, `FullTranscript.jsonl`, and `Memoir.md`.
  - Use for `/memory` or when the user asks where the memoir is stored.

### Other Implementation Choices
- Python CLI is the v1 interface.
- The standard OpenAI SDK is enough for v1; no Agents SDK.
- `Memoir.md` is the primary readable memory used for recall.
- `FullTranscript.jsonl` is the authoritative full conversation memory and may be consulted for exact detail while under the v1 size limit.
- `CurrentSession.jsonl` is temporary staging memory.
- If the user declines saving an active or interrupted session, `CurrentSession.jsonl` is discarded.
- v1 uses LLM-based recall over local files, without vector embeddings or a separate search index.

## Test Plan
- Test JSONL append/read behavior for current and full transcript files.
- Test `/save`: current session is appended to `FullTranscript.jsonl`, rendered into `Memoir.md`, then cleared.
- Test startup recovery when `CurrentSession.jsonl` exists.
- Test `/quit` save and discard paths.
- Test recall with a matching saved memoir entry.
- Test recall with no plausible match.
- Test recall includes `FullTranscript.jsonl` when it is `<= 100_000` bytes.
- Test recall skips `FullTranscript.jsonl` and uses `Memoir.md` only when it is over `100_000` bytes.
- Test that recall is read-only and does not modify `CurrentSession.jsonl`, `FullTranscript.jsonl`, or `Memoir.md`.
- Test that LLM-requested `save_and_clear` requires explicit user confirmation before writing.
- Test that failed memoirization does not clear `CurrentSession.jsonl`.
- Mock OpenAI calls so tests do not require network access or an API key.
