######################################################################
#
# OpenAI Responses API wrapper and LLM protocol for the Memorex agent.
#
# This module isolates model calls for chat, recall, and memoirization
# so the application can use fake clients in tests.
#
# Author: Sudhakar Narayanamurthy.
#

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from .models import ChatResult, ToolCall
from .prompts import MEMOIRIZATION_PROMPT, PROFILE_UPDATE_PROMPT, RECALL_PROMPT, SYSTEM_PROMPT, TOOL_SCHEMAS
from .tracing import trace_event

DEFAULT_MODEL = "gpt-5.4-mini"


class LLMClient(Protocol):
    # Interface used by the app so tests can provide a fake model.

    def chat(self, messages: list[dict[str, str]], user_profile: dict[str, Any] | None = None, tools: bool = True) -> ChatResult:
        # Generate a chat response and optional tool calls.

        ...

    def chat_with_tool_outputs(
        self,
        messages: list[dict[str, str]],
        previous_output: list[Any],
        tool_outputs: list[dict[str, Any]],
        user_profile: dict[str, Any] | None = None,
    ) -> ChatResult:
        # Continue a chat turn after local tool execution.

        ...

    def memoirize(self, records: list[dict[str, Any]], suggested_title: str | None = None) -> str:
        # Convert a staged transcript into readable memoir prose.

        ...

    def update_user_profile(
        self,
        records: list[dict[str, Any]],
        memoir: str,
        user_profile: dict[str, Any],
    ) -> dict[str, Any]:
        # Produce conservative updates to structured user profile memory.

        ...

    def recall(
        self,
        user_utterance: str,
        recent_context: list[dict[str, Any]],
        memoir: str,
        user_profile: dict[str, Any],
        hint: str | None = None,
    ) -> dict[str, Any]:
        # Use saved memory context to identify a referenced prior conversation.

        ...


class OpenAIResponsesClient:
    # LLM client backed by the standard OpenAI SDK Responses API.

    def __init__(self, model: str | None = None):
        # Create an OpenAI client using OPENAI_MODEL or the default model.

        self.model = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is required for real chat. Install project dependencies first."
            ) from exc
        self.client = OpenAI()

    def chat(self, messages: list[dict[str, str]], user_profile: dict[str, Any] | None = None, tools: bool = True) -> ChatResult:
        # Send current conversation context to the model for a listener reply.

        input_messages = messages
        if user_profile is not None:
            input_messages = [
                {
                    "role": "developer",
                    "content": "UserProfile.json context for personalization only:\n"
                    + json.dumps(user_profile, ensure_ascii=False, indent=2),
                },
                *messages,
            ]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": SYSTEM_PROMPT,
            "input": input_messages,
        }
        if tools:
            kwargs["tools"] = TOOL_SCHEMAS
        trace_event("llm_request.chat", sanitize_request(kwargs))
        response = self.client.responses.create(**kwargs)
        trace_event("llm_response.chat", response_to_trace(response))
        return self._chat_result(response)

    def chat_with_tool_outputs(
        self,
        messages: list[dict[str, str]],
        previous_output: list[Any],
        tool_outputs: list[dict[str, Any]],
        user_profile: dict[str, Any] | None = None,
    ) -> ChatResult:
        # Send function-call outputs back to the model for the final reply.

        input_messages = [*messages, *previous_output, *tool_outputs]
        if user_profile is not None:
            input_messages = [
                {
                    "role": "developer",
                    "content": "UserProfile.json context for personalization only:\n"
                    + json.dumps(user_profile, ensure_ascii=False, indent=2),
                },
                *input_messages,
            ]
        request_payload = {
            "model": self.model,
            "instructions": SYSTEM_PROMPT,
            "input": input_messages,
            "tools": TOOL_SCHEMAS,
        }
        trace_event("llm_request.tool_followup", sanitize_request(request_payload))
        response = self.client.responses.create(
            **request_payload,
        )
        trace_event("llm_response.tool_followup", response_to_trace(response))
        return self._chat_result(response)

    def memoirize(self, records: list[dict[str, Any]], suggested_title: str | None = None) -> str:
        # Ask the model to render the current transcript as a memoir entry.

        prompt = {
            "records": records,
            "suggested_title": suggested_title,
        }
        request_payload = {
            "model": self.model,
            "instructions": MEMOIRIZATION_PROMPT,
            "input": json.dumps(prompt, ensure_ascii=False),
        }
        trace_event("llm_request.memoirize", sanitize_request(request_payload))
        response = self.client.responses.create(
            **request_payload,
        )
        trace_event("llm_response.memoirize", response_to_trace(response))
        return response.output_text.strip()

    def update_user_profile(
        self,
        records: list[dict[str, Any]],
        memoir: str,
        user_profile: dict[str, Any],
    ) -> dict[str, Any]:
        # Ask the model for conservative structured user profile updates.

        prompt = {
            "records": records,
            "memoir_md": memoir,
            "user_profile": user_profile,
        }
        request_payload = {
            "model": self.model,
            "instructions": PROFILE_UPDATE_PROMPT,
            "input": json.dumps(prompt, ensure_ascii=False),
        }
        trace_event("llm_request.update_user_profile", sanitize_request(request_payload))
        response = self.client.responses.create(
            **request_payload,
        )
        trace_event("llm_response.update_user_profile", response_to_trace(response))
        return parse_profile_json(response.output_text, user_profile)

    def recall(
        self,
        user_utterance: str,
        recent_context: list[dict[str, Any]],
        memoir: str,
        user_profile: dict[str, Any],
        hint: str | None = None,
    ) -> dict[str, Any]:
        # Ask the model to perform grounded recall over saved memory text.

        payload = {
            "user_utterance": user_utterance,
            "recent_context": recent_context,
            "hint": hint,
            "memoir_md": memoir,
            "user_profile": user_profile,
        }
        request_payload = {
            "model": self.model,
            "instructions": RECALL_PROMPT,
            "input": json.dumps(payload, ensure_ascii=False),
        }
        trace_event("llm_request.recall", sanitize_request(request_payload))
        response = self.client.responses.create(
            **request_payload,
        )
        trace_event("llm_response.recall", response_to_trace(response))
        return parse_recall_json(response.output_text)

    def _chat_result(self, response: Any) -> ChatResult:
        # Normalize an OpenAI response object into ChatResult.

        tool_calls: list[ToolCall] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "function_call":
                continue
            arguments = getattr(item, "arguments", "{}") or "{}"
            try:
                parsed_args = json.loads(arguments)
            except json.JSONDecodeError:
                parsed_args = {}
            tool_calls.append(
                ToolCall(
                    name=getattr(item, "name", ""),
                    arguments=parsed_args,
                    call_id=getattr(item, "call_id", None),
                )
            )
        return ChatResult(
            text=(getattr(response, "output_text", "") or "").strip(),
            tool_calls=tool_calls,
            raw_output=list(getattr(response, "output", []) or []),
        )


def parse_recall_json(raw_text: str) -> dict[str, Any]:
    # Parse recall JSON, falling back to a safe no-match result on invalid JSON.

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {
            "found": False,
            "confidence": "low",
            "summary": "",
            "date_or_session_id": None,
            "supporting_excerpts": [],
        }
    parsed.setdefault("found", False)
    parsed.setdefault("confidence", "low")
    parsed.setdefault("summary", "")
    parsed.setdefault("date_or_session_id", None)
    parsed.setdefault("supporting_excerpts", [])
    return parsed


def parse_profile_json(raw_text: str, fallback: dict[str, Any]) -> dict[str, Any]:
    # Parse profile JSON, falling back to the existing profile on invalid JSON.

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return fallback
    if not isinstance(parsed, dict):
        return fallback
    for key in ["preferences", "recurring_themes", "important_people", "goals", "open_threads"]:
        parsed.setdefault(key, fallback.get(key, []))
        if not isinstance(parsed[key], list):
            parsed[key] = fallback.get(key, [])
    return parsed


# Prepare a Responses API request for debug printing.
def sanitize_request(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": request.get("model"),
        "instructions": request.get("instructions"),
        "input": request.get("input"),
        "tools": request.get("tools"),
    }


# Prepare a Responses API response for debug printing.
def response_to_trace(response: Any) -> dict[str, Any]:
    return {
        "id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "status": getattr(response, "status", None),
        "output_text": getattr(response, "output_text", None),
        "output": response_output_to_trace(getattr(response, "output", []) or []),
        "usage": object_to_plain(getattr(response, "usage", None)),
    }


# Convert model output items into JSON-serializable debug data.
def response_output_to_trace(output: list[Any]) -> list[Any]:
    traced = []
    for item in output:
        traced.append(object_to_plain(item))
    return traced


# Convert SDK objects into plain data for trace printing.
def object_to_plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [object_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: object_to_plain(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return object_to_plain(value.model_dump())
    if hasattr(value, "__dict__"):
        return object_to_plain(vars(value))
    return str(value)
