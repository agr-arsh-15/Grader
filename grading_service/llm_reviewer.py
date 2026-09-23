"""
LLM-based AI usage reviewer.

Takes the parsed log summary and generates:
  - ai_usage_score (float 0–100)
  - notes (str): short human-readable assessment

Uses OpenAI gpt-4o-mini by default (configurable via OPENAI_MODEL env var).
Degrades gracefully (score=0, notes="LLM unavailable") if OPENAI_API_KEY is missing.
"""
import logging
import os

logger = logging.getLogger(__name__)

_REVIEW_RUBRIC = """
You are an expert evaluator reviewing how a software engineering candidate used AI coding tools
during a bug-fixing assessment. Evaluate the following AI session log summary.

Scoring rubric (0–100 total):
- Problem Decomposition (0–30 pts): Did the candidate break down the task clearly? Did they
  show understanding of what they were doing rather than blindly prompting?
- AI Output Verification (0–30 pts): Did the candidate test, verify, or critically review AI
  suggestions before accepting them?
- Efficiency & Signal (0–25 pts): Was the workflow efficient? Did they iterate intelligently
  rather than repeating the same failed prompts?
- Clarity & Independence (0–15 pts): Did prompts show genuine problem-solving, not just
  copy-pasting error messages?

Return ONLY a JSON object with two keys:
  "score": integer 0–100
  "notes": string (2–4 sentences explaining the score)

Do not include any other text.
"""


def review_ai_usage(log_summary: dict) -> tuple[float, str]:
    """
    Returns (score: float, notes: str).
    Falls back to (0.0, "LLM unavailable") if OpenAI is not configured.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key.startswith("sk-your"):
        logger.warning("OPENAI_API_KEY not set — skipping LLM review")
        return 0.0, "LLM review skipped: OPENAI_API_KEY not configured."

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    summary_text = _format_summary_for_llm(log_summary)

    try:
        import openai
        client = openai.OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _REVIEW_RUBRIC},
                {
                    "role": "user",
                    "content": (
                        f"Here is the AI session log summary:\n\n{summary_text}\n\n"
                        f"And here is an excerpt from the raw logs:\n\n"
                        f"{log_summary.get('raw_excerpt', '')[:2000]}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=400,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        import json
        result = json.loads(content)

        score = float(result.get("score", 0))
        score = max(0.0, min(100.0, score))  # clamp
        notes = str(result.get("notes", "No notes provided."))
        return score, notes

    except Exception as exc:
        logger.error("LLM review failed: %s", exc)
        return 0.0, f"LLM review failed due to an error: {type(exc).__name__}. Automated score only."


def _format_summary_for_llm(summary: dict) -> str:
    lines = [
        f"- Total log files: {summary.get('total_files', 0)} ({summary.get('parsed_files', 0)} successfully parsed)",
        f"- Estimated conversation turns: {summary.get('conversation_turns', 0)}",
        f"- Estimated user prompts: {summary.get('prompt_count', 0)}",
        f"- Estimated total tokens: {summary.get('total_tokens_est', 0)}",
        f"- Verification/testing mentions: {summary.get('verification_mentions', 0)}",
        f"- Problem decomposition mentions: {summary.get('decomposition_mentions', 0)}",
    ]
    return "\n".join(lines)
