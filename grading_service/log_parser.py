"""
AI session log parser.

Reads log files in multiple formats:
- JSON export (e.g. Cursor, Windsurf, Claude Desktop — looks for common keys)
- Plain text / markdown (fallback line-by-line scan)

Returns a structured summary dict that is passed to the LLM reviewer.
Does NOT hard-fail on unrecognized formats — it degrades to a best-effort extraction.
"""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Heuristic patterns for plain-text log scanning
_PROMPT_PATTERNS = [
    re.compile(r"^(you|user|human)\s*[:\|>]", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^>\s+.{10,}", re.MULTILINE),  # markdown quote style
    re.compile(r'"role"\s*:\s*"user"', re.IGNORECASE),
]
_VERIFICATION_PATTERNS = [
    re.compile(r"\b(test|assert|verify|check|run|execute|works|passed|failed)\b", re.IGNORECASE),
    re.compile(r"\b(let me test|tested it|ran the tests?|all tests pass)\b", re.IGNORECASE),
]
_DECOMPOSITION_PATTERNS = [
    re.compile(r"\b(step \d|first|second|third|finally|approach|plan|strategy)\b", re.IGNORECASE),
    re.compile(r"\b(break.*down|sub[\s-]?problem|divide)\b", re.IGNORECASE),
]


def parse_log_files(log_paths: list[str]) -> dict:
    """
    Parse all log files and return a unified summary dict.
    """
    all_conversations: list[dict] = []
    raw_texts: list[str] = []
    total_files = 0
    parsed_files = 0

    for path_str in log_paths:
        path = Path(path_str)
        if not path.exists():
            logger.warning("Log file not found: %s", path_str)
            continue

        total_files += 1
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            raw_texts.append(raw)

            parsed = _try_parse_json(raw)
            if parsed is not None:
                all_conversations.append(parsed)
                parsed_files += 1
            else:
                # Fallback: treat as plain text
                all_conversations.append(_parse_plaintext(raw, path.name))
                parsed_files += 1
        except Exception as exc:
            logger.warning("Failed to read log file %s: %s", path_str, exc)

    if not all_conversations:
        return {
            "total_files": total_files,
            "parsed_files": 0,
            "prompt_count": 0,
            "total_tokens_est": 0,
            "verification_mentions": 0,
            "decomposition_mentions": 0,
            "conversation_turns": 0,
            "raw_excerpt": "",
        }

    # Aggregate
    prompt_count = sum(c.get("prompt_count", 0) for c in all_conversations)
    verification_mentions = sum(c.get("verification_mentions", 0) for c in all_conversations)
    decomposition_mentions = sum(c.get("decomposition_mentions", 0) for c in all_conversations)
    conversation_turns = sum(c.get("conversation_turns", 0) for c in all_conversations)
    total_tokens_est = sum(c.get("total_tokens_est", 0) for c in all_conversations)

    # Excerpt: first 3000 chars of combined raw text for LLM context
    combined_raw = "\n\n---\n\n".join(raw_texts)
    raw_excerpt = combined_raw[:3000]

    return {
        "total_files": total_files,
        "parsed_files": parsed_files,
        "prompt_count": prompt_count,
        "total_tokens_est": total_tokens_est,
        "verification_mentions": verification_mentions,
        "decomposition_mentions": decomposition_mentions,
        "conversation_turns": conversation_turns,
        "raw_excerpt": raw_excerpt,
    }


# ─────────────────────────────────────────────────────────────────────────────


def _try_parse_json(raw: str) -> dict | None:
    """Try to extract structured data from JSON log formats."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    messages: list[dict] = []

    # Format 1: { "messages": [...] }  (common in many AI tools)
    if isinstance(data, dict) and "messages" in data:
        messages = data["messages"]
    # Format 2: top-level list of message objects
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        messages = data
    # Format 3: { "conversation": [...] }
    elif isinstance(data, dict) and "conversation" in data:
        messages = data["conversation"]
    else:
        return None  # Unrecognized JSON structure

    if not messages:
        return None

    prompt_count = 0
    verification_mentions = 0
    decomposition_mentions = 0
    total_chars = 0

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = (msg.get("role") or msg.get("sender") or "").lower()
        content = str(msg.get("content") or msg.get("text") or msg.get("message") or "")
        total_chars += len(content)

        if role in ("user", "human"):
            prompt_count += 1
            for pat in _VERIFICATION_PATTERNS:
                verification_mentions += len(pat.findall(content))
            for pat in _DECOMPOSITION_PATTERNS:
                decomposition_mentions += len(pat.findall(content))

    return {
        "format": "json",
        "conversation_turns": len(messages),
        "prompt_count": prompt_count,
        "total_tokens_est": total_chars // 4,  # rough estimate
        "verification_mentions": verification_mentions,
        "decomposition_mentions": decomposition_mentions,
    }


def _parse_plaintext(raw: str, filename: str) -> dict:
    """Heuristic plain-text / markdown log parser."""
    prompt_count = 0
    for pat in _PROMPT_PATTERNS:
        prompt_count = max(prompt_count, len(pat.findall(raw)))

    verification_mentions = 0
    for pat in _VERIFICATION_PATTERNS:
        verification_mentions += len(pat.findall(raw))

    decomposition_mentions = 0
    for pat in _DECOMPOSITION_PATTERNS:
        decomposition_mentions += len(pat.findall(raw))

    lines = raw.splitlines()
    # Rough turn count: count blank-line-separated blocks
    conversation_turns = max(1, sum(1 for l in lines if not l.strip()))

    return {
        "format": "plaintext",
        "filename": filename,
        "conversation_turns": conversation_turns,
        "prompt_count": prompt_count,
        "total_tokens_est": len(raw) // 4,
        "verification_mentions": verification_mentions,
        "decomposition_mentions": decomposition_mentions,
    }
