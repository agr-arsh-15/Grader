"""
Automated bug detection.

For each bug in the manifest, runs its detection_check against the submitted code.

Supported detection_check formats:
  grep:<pattern>           — case-insensitive substring search in bug['file']
  regex:<pattern>          — regex search in bug['file']
  grep_all:<pattern>       — case-insensitive substring search across all files
  regex_all:<pattern>      — regex search across all files
  test:<pytest_args>       — run pytest with the given args in the extracted dir
  (anything else)          — cannot automate; returns "not_automated"

Returns a dict: { bug_id: "fixed" | "not_fixed" | "partial" | "not_automated" }
"""
import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def run_automated_checks(extracted_dir: str, bugs: list[dict]) -> dict[str, str]:
    results: dict[str, str] = {}
    for bug in bugs:
        bug_id = bug.get("id", "unknown")
        detection = (bug.get("detection_check") or "").strip()
        bug_file = bug.get("file", "")

        try:
            result = _evaluate_detection(extracted_dir, detection, bug_file)
        except Exception as exc:
            logger.warning("Error evaluating check for %s: %s", bug_id, exc)
            result = "not_fixed"

        results[bug_id] = result
        logger.debug("Bug %s → %s", bug_id, result)

    return results


# ─────────────────────────────────────────────────────────────────────────────


def _evaluate_detection(base_dir: str, detection: str, bug_file: str) -> str:
    if not detection:
        return "not_automated"

    lower = detection.lower()

    if lower.startswith("grep:"):
        pattern = detection[5:]
        return _grep_file(base_dir, bug_file, pattern, case_insensitive=True)

    if lower.startswith("regex:"):
        pattern = detection[6:]
        return _regex_file(base_dir, bug_file, pattern)

    if lower.startswith("grep_all:"):
        pattern = detection[9:]
        return _grep_all_files(base_dir, pattern, case_insensitive=True)

    if lower.startswith("regex_all:"):
        pattern = detection[10:]
        return _grep_all_files(base_dir, pattern, case_insensitive=False, use_regex=True)

    if lower.startswith("test:"):
        test_args = detection[5:].strip()
        return _run_pytest(base_dir, test_args)

    logger.info("Detection check '%s' has no known prefix — marking not_automated", detection[:60])
    return "not_automated"


def _read_file_safe(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _grep_file(base_dir: str, rel_file: str, pattern: str, case_insensitive: bool) -> str:
    """Search for pattern in a specific file. 'fixed' if found."""
    if not rel_file:
        return _grep_all_files(base_dir, pattern, case_insensitive)

    full_path = Path(base_dir) / rel_file
    if not full_path.exists():
        logger.warning("File '%s' not found in submission", rel_file)
        return "not_fixed"

    content = _read_file_safe(str(full_path))
    if content is None:
        return "not_fixed"

    haystack = content.lower() if case_insensitive else content
    needle = pattern.lower() if case_insensitive else pattern
    return "fixed" if needle in haystack else "not_fixed"


def _regex_file(base_dir: str, rel_file: str, pattern: str) -> str:
    """Regex search in a specific file. 'fixed' if any match found."""
    if not rel_file:
        return _grep_all_files(base_dir, pattern, case_insensitive=False, use_regex=True)

    full_path = Path(base_dir) / rel_file
    if not full_path.exists():
        return "not_fixed"

    content = _read_file_safe(str(full_path))
    if content is None:
        return "not_fixed"

    try:
        return "fixed" if re.search(pattern, content) else "not_fixed"
    except re.error as exc:
        logger.warning("Invalid regex '%s': %s", pattern, exc)
        return "not_automated"


def _grep_all_files(
    base_dir: str, pattern: str, case_insensitive: bool, use_regex: bool = False
) -> str:
    """Search all text files under base_dir for pattern."""
    flags = re.IGNORECASE if case_insensitive else 0
    for root, _dirs, files in os.walk(base_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            content = _read_file_safe(fpath)
            if content is None:
                continue
            try:
                if use_regex:
                    if re.search(pattern, content, flags):
                        return "fixed"
                else:
                    haystack = content.lower() if case_insensitive else content
                    needle = pattern.lower() if case_insensitive else pattern
                    if needle in haystack:
                        return "fixed"
            except re.error:
                continue
    return "not_fixed"


def _run_pytest(base_dir: str, test_args: str) -> str:
    """
    Run pytest in the extracted directory.
    Returns 'fixed' on test pass, 'not_fixed' on failure, 'partial' on error/timeout.

    WARNING: Executes candidate code — acceptable for internal tool only.
    """
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--tb=no", "-q", test_args],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return "fixed"
        elif result.returncode == 1:
            return "not_fixed"
        else:
            # pytest error (collection error, etc.)
            logger.warning("pytest exited with code %d: %s", result.returncode, result.stderr[:200])
            return "partial"
    except subprocess.TimeoutExpired:
        logger.warning("pytest timed out for args: %s", test_args)
        return "partial"
    except FileNotFoundError:
        logger.warning("pytest not available in grading environment")
        return "not_automated"
