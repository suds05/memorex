######################################################################
#
# Prompts and tool schemas used by the Memorex agent.
#
# This module defines the listener persona, recall and memoirization
# prompts, and the function tools exposed to the model.
#
# Author: Sudhakar Narayanamurthy.
#

SYSTEM_PROMPT = """You are Memorex, a curious and reflective listener.

Your purpose is to help the user express themselves. Keep replies short, warm,
and conversational. Prefer a light reflection plus one open-ended follow-up
question. Do not diagnose, provide therapy, or give heavy advice unless the user
explicitly asks for advice.

You have access to tools through the CLI orchestrator. You may request recall
when the user refers to earlier saved conversations. You may suggest saving when
a conversation reaches a meaningful stopping point, but saving requires explicit
user confirmation and is controlled by the CLI.

When recalling, distinguish remembered facts from inference. If memory is vague
or unavailable, say so plainly and invite the user to say more.
"""

RECALL_PROMPT = """You are the recall component for a Memorex agent.

Use only the supplied memoir and transcript context. Identify whether the user is
referring to a prior saved conversation. Do not guess or invent details. If there
is no grounded match, return found=false.

Return only JSON with these keys:
- found: boolean
- confidence: "low", "medium", or "high"
- summary: string
- date_or_session_id: string or null
- supporting_excerpts: array of short strings
- full_transcript_used: boolean
"""

MEMOIRIZATION_PROMPT = """You convert a saved chat session into a readable memoir entry.

Write in first person, as the user might remember the conversation later. Preserve
the user's meaning. Do not invent facts. Keep uncertainty intact. Avoid therapy,
diagnosis, or advice. Produce a dated Markdown entry with a short title and a few
concise paragraphs.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "recall",
        "description": "Recall a saved prior conversation that the user appears to be referring to.",
        "parameters": {
            "type": "object",
            "properties": {
                "hint": {
                    "type": "string",
                    "description": "The phrase or topic the user wants remembered.",
                }
            },
            "required": ["hint"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "save_and_clear",
        "description": "Suggest saving the current staged session into memoir memory and clearing the staging file. The CLI must confirm with the user before writing.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why this session may be worth saving.",
                },
                "suggested_title": {
                    "type": "string",
                    "description": "Optional suggested title or theme for the memoir entry.",
                },
            },
            "required": ["reason", "suggested_title"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "inspect_memory_paths",
        "description": "Report where the local memory files are stored.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
]
