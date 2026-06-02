# Memorex Agent CLI

## Summary
Build a Python CLI for a reflective listener agent named Memorex. It chats with the user, records the active session in `CurrentSession.jsonl`, saves approved sessions into `Memoir.md` and `UserProfile.json`, and can recall saved earlier conversations when the user refers to them.

Use the standard OpenAI Python SDK with the Responses API, not the Agents SDK. Default to `gpt-5.4-mini`, configurable via `OPENAI_MODEL`.

## Requirements
- The agent presents as a curious, reflective listener who nudges the user to express themselves.
- Agent remembers users well and acts accordingly. This is a key requirement.
  - Maintains lightweight understanding of preferences, recurring themes, important people, goals, and open threads.
  - Uses relevant saved memory without requiring the user to explicitly ask "remember when," while keeping references gentle and grounded.
  - Supports continuity across sessions by noticing unresolved or recurring topics and asking whether the user wants to revisit them when appropriate.
  - Adapts response style based on remembered preferences, such as concise answers, practical suggestions, or a reflective tone.
- Agent remains factual.
  - Preserve uncertainty and avoid inventing details in memoir entries or recall responses.
  - Distinguish remembered facts from inference and avoid pretending certainty when memory is vague.
- User control remains central: saving requires explicit confirmation, and saving a session implies permission to update both memoir and profile memory.

## Key Implementation Aspects
### Memory Model
- Conversation memory: `CurrentSession.jsonl`
  - Temporary staging memory for the active session.
  - Stores raw user/assistant turns while the session is active.
  - Cleared after a confirmed save completes, or discarded if the user declines saving.
  - Used as input for memoir generation and profile-update generation.

- Memoir memory: `Memoir.md`
  - Durable distilled narrative memory of conversation sessions.
  - Captures salient events, feelings, decisions, useful context, unresolved threads, and session-local preference signals.
  - Used as the primary source for recall.

- User profile memory: `UserProfile.json`
  - Durable structured personalization memory.
  - Stores stable preferences, recurring themes, important people, goals, and open threads.
  - Explicit user-stated preferences may be added immediately.
  - Inferred themes/preferences should be promoted only after they appear across at least two saved memoir entries.
  - Used to personalize normal chat turns and support continuity across sessions.

### Tool Orchestration
- Tools are implemented in the Python CLI orchestrator; the model may request tools through Responses API function/tool calls.
- The orchestrator validates tool names and arguments, executes allowed tools, and sends tool results back to the model.
- The model never directly reads or writes files.
- `save_and_clear` remains one confirmed lifecycle operation: commit the staged session into durable memory, then clear `CurrentSession.jsonl`.
- v1 does not support mid-session durable checkpoints. A future `checkpoint_memory` operation may save only new turns without clearing the active session.

### Tools
- `recall`
  - Normal chat turns include `UserProfile.json` as long-term personalization context, while `Memoir.md` is used only when recall is needed.
  - Reads `Memoir.md` for narrative memory and `UserProfile.json` for personalization context; it does not read a durable raw transcript.
  - Recall responses should identify uncertainty and avoid pretending that inferred profile patterns are facts.

- `save_and_clear`
  - On save, the LLM generates a dated `Memoir.md` entry from `CurrentSession.jsonl`.
  - The memoir entry should include session-local preference signals when relevant, without overclaiming them as stable traits.
  - The LLM also proposes conservative `UserProfile.json` updates from the saved session and existing memoir/profile context.
  - Saves `Memoir.md` atomically, updates `UserProfile.json` when possible, and clears `CurrentSession.jsonl` only after the memoir save succeeds.

- `inspect_memory_paths`
  - Reports paths for `CurrentSession.jsonl`, `Memoir.md`, and `UserProfile.json`.

### Other Implementation Details
- Use the standard `openai` package with `OpenAI().responses.create(...)`. Keep `python -m memoir` and `./run.sh` as the v1 entrypoints; the user-facing agent name is Memorex.
- Store memory under `~/.memorex` by default, with `MEMOIR_DATA_DIR` available as an override.
- Do not keep durable `FullTranscript.jsonl` in v1. `CurrentSession.jsonl` is cleared after confirmed save or discarded if the user declines saving.
- Save via atomic staging: write updated durable files to same-directory temp files, atomically replace `Memoir.md`, update `UserProfile.json` when available, write a save-completion marker, then clear `CurrentSession.jsonl`.
- On startup, if a save-completion marker is found, clear `CurrentSession.jsonl` and remove the marker because the durable memoir save already completed before a crash.
- Configure the model with `OPENAI_MODEL`, defaulting to `gpt-5.4-mini`; require `OPENAI_API_KEY` for real OpenAI-backed chat.

## Test Plan
- Test active turns are staged in `CurrentSession.jsonl`.
- Test confirmed save writes `Memoir.md`, updates `UserProfile.json`, and clears `CurrentSession.jsonl`.
- Test declined save discards only the intended staging data.
- Test startup recovery for interrupted `CurrentSession.jsonl` and save-completion markers.
- Test recall uses `Memoir.md` and `UserProfile.json`, not a full transcript file.
- Test explicit preferences can update profile immediately.
- Test inferred preferences require evidence from at least two memoir entries before profile promotion.
- Test profile update failure does not block memoir save or staged-session cleanup after memoir save succeeds.
- Test atomic save recovery does not duplicate or lose staged memory.
- Mock OpenAI calls so tests do not require network access or an API key.

## Running
- Install dependencies in a Python 3.10+ environment: `python -m pip install -e .`
- Set `OPENAI_API_KEY` in the environment.
- Optionally set `OPENAI_MODEL`; otherwise the CLI uses `gpt-5.4-mini`.
- Optionally set `MEMOIR_DATA_DIR`; otherwise memory files are stored in `~/.memorex`.
- Optionally set `MEMOIR_DEBUG=1` to print dimmed LLM request/response and tool traces to stderr.
- Optionally set `NO_COLOR=1` to disable ANSI color in debug output.
- Run the CLI: `python -m memoir`
- Run tests: `python -m unittest discover -s tests -v`

## Example Transcript
```text
$ ./run.sh
Memorex is listening. Type /save, /memory, or /quit.
> Hey buddy!
Hey! Nice to see you. What’s up?

> Do you recall what I told you about tomorrow.
Yes — I remember you said you have a follow-up interview tomorrow, after today’s one, and you weren’t feeling great about it. You also asked for ideas to pep yourself up.

How are you feeling about it now?

> Your idea was good. Can you give me more ideas.
I’m glad it helped. A few more gentle ideas:

- Keep it simple: aim to be present, not perfect.
- Write down 3 strengths you can mention if nerves hit.
- Do a quick “best case / worst case / most likely” check.
- Pick one small ritual for before it starts — a walk, music, tea.
- Remind yourself: they’re getting a real person, not a performance.

Want ideas for calming your nerves, or for answering questions more confidently?

>  I like the 'Keep it simple' one. Thanks a bunch.
Glad that one landed. Simple can be a real strength.

If you want, I can help you turn that into a tiny mantra for tomorrow.

> /quit
Save this session to the memoir before quitting? [y/N] y
Saved and cleared the current session.
Memoir.md: /home/suds05/.memorex/Memoir.md
UserProfile.json: /home/suds05/.memorex/UserProfile.json
```
