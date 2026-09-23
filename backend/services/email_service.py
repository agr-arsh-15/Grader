"""
Email & Credentials helpers: standardized credential generation
(candidate_name@grader.com, Name@123) and email composition for mailto / client dispatch.
"""
import re
from typing import Optional


def generate_candidate_portal_email(full_name: str) -> str:
    """
    Generate standardized portal login email: candidate_name@grader.com.
    e.g. 'Arsh Agrawal' -> 'arsh_agrawal@grader.com'
    """
    cleaned = full_name.strip().lower()
    slug = re.sub(r'[^a-z0-9]+', '_', cleaned).strip('_')
    if not slug:
        slug = "candidate"
    return f"{slug}@grader.com"


def generate_candidate_default_password(full_name: str) -> str:
    """
    Generate standardized password: Name@123.
    e.g. 'Arsh Agrawal' -> 'Arsh@123'
         'john doe' -> 'John@123'
    """
    parts = full_name.strip().split()
    first_name = parts[0] if parts else "Candidate"
    clean_first = re.sub(r'[^a-zA-Z0-9]', '', first_name).capitalize()
    if not clean_first:
        clean_first = "Candidate"
    return f"{clean_first}@123"


def compose_assessment_email_text(
    candidate_name: str,
    login_email: str,
    password: str,
    portal_url: str,
    assignment_title: Optional[str] = None,
    due_date: Optional[str] = None,
) -> tuple[str, str]:
    """
    Returns (subject, plain_text_body) for direct mailto opening.
    """
    task_name = assignment_title or "AI-Assisted Coding Assessment"
    deadline_text = due_date or "As specified on your dashboard"
    subject = f"Invitation: Coding Assessment ({task_name}) — Grader.ai"

    plain_body = f"""Hello {candidate_name},

You have been invited to complete a coding assessment on the Grader.ai platform.

Assessment Details:
- Task: {task_name}
- Deadline: {deadline_text}
- Portal URL: {portal_url}

Your Login Credentials:
- Portal Username: {login_email}
- Temporary Password: {password}

Instructions:
1. Log in to the portal at {portal_url} using your credentials.
2. Download your assigned starter codebase package (.zip).
3. Complete the task locally using your preferred AI coding tools (Claude, Cursor, Copilot, ChatGPT, etc.).
4. Save and export your AI conversation / session logs.
5. Upload your fixed solution archive along with your AI prompt logs before the deadline.

Best regards,
Assessment & Recruitment Team
Grader.ai
"""
    return subject, plain_body
