# AI Assessment Grading Portal — v1

An internal tool for running AI-assisted coding assessments. Admins create assignments (buggy codebases + rubrics), assign them to candidates, and trigger automated + LLM-based grading of submissions.

---

## Architecture

```
Grader/
├── backend/          # FastAPI web portal + API (Python 3.12)
└── grading_service/  # Separate FastAPI grading micro-service (Python 3.12)
```

The backend serves the web UI and REST API. When an admin triggers grading, the backend calls the grading service over HTTP. The grading service POSTs results back to the backend's internal endpoint.

---

## Prerequisites

- Python 3.12+
- PostgreSQL 15+ running locally (or accessible)
- An OpenAI API key (optional — AI usage review is skipped gracefully without it)

---

## 1. Set Up PostgreSQL

```bash
# Create database and user
psql -U postgres -c "CREATE USER grader WITH PASSWORD 'graderpass';"
psql -U postgres -c "CREATE DATABASE graderdb OWNER grader;"
```

---

## 2. Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, JWT_SECRET, INTERNAL_API_KEY, and optionally SEED_ADMIN_*
```

### Generate a secure secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Use the output as `JWT_SECRET` and (a different value) as `INTERNAL_API_KEY`.

### Run database migrations:

> All commands below must be run from the `backend/` directory with the venv active.

```bash
# Alembic needs the parent Grader/ dir on the Python path so it can import backend.*
PYTHONPATH=.. alembic upgrade head
```

### Seed the admin account:
```bash
PYTHONPATH=.. python3 seed.py
```
This reads `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` from `.env` and creates the admin user. Safe to run multiple times.

### Start the backend:
```bash
PYTHONPATH=.. uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

The portal is now available at: **http://localhost:8000**

---

## 3. Grading Service Setup

```bash
cd grading_service

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env — set OPENAI_API_KEY (optional), OPENAI_MODEL
```

### Start the grading service:
```bash
uvicorn main:app --host 0.0.0.0 --port 5100 --reload
```

The service runs at: **http://localhost:5100**

---

## 4. Creating a Candidate Account

There is no self-registration in v1. An admin must create candidate accounts directly in the database:

```bash
# From backend/ directory, with .venv active:
python -c "
import asyncio
from database import AsyncSessionLocal
from models.user import User, UserRole
from services.auth_service import hash_password

async def create():
    async with AsyncSessionLocal() as db:
        u = User(email='candidate@example.com', password_hash=hash_password('CandPass@1!'), role=UserRole.candidate)
        db.add(u)
        await db.commit()
        print('Created:', u.email)

asyncio.run(create())
"
```

> **Planned for v2**: A candidate invite/registration flow.

---

## 5. Bug Manifest Format

Upload a `.json` file when creating an assignment:

```json
{
  "bugs": [
    {
      "id": "bug-001",
      "category": "broken-code",
      "file": "src/calculator.py",
      "description": "Division does not handle zero denominator — internal only, never shown to candidates",
      "detection_check": "grep:def safe_divide"
    },
    {
      "id": "bug-002",
      "category": "race-condition",
      "file": "src/worker.py",
      "description": "Missing lock around shared counter",
      "detection_check": "regex:threading\\.Lock\\(\\)"
    },
    {
      "id": "bug-003",
      "category": "wrong-documentation",
      "file": "",
      "description": "README claims O(1) complexity but implementation is O(n)",
      "detection_check": "grep_all:O(1)"
    },
    {
      "id": "bug-004",
      "category": "broken-code",
      "file": "",
      "description": "test_add should pass after fixing off-by-one",
      "detection_check": "test:test_add"
    }
  ]
}
```

### Supported `detection_check` formats:

| Prefix | Behavior |
|---|---|
| `grep:<pattern>` | Case-insensitive substring search in `file` (or all files if `file` is empty) |
| `regex:<pattern>` | Regex search in `file` |
| `grep_all:<pattern>` | Case-insensitive substring search across all submitted files |
| `regex_all:<pattern>` | Regex search across all files |
| `test:<pytest_args>` | Runs `python -m pytest <args>` in extracted submission dir. **Executes candidate code — internal use only.** |
| *(anything else)* | Marked `not_automated` (scores as partial: 0.5× weight) |

---

## Scoring Formula

```
automated_score  = (fixed + 0.5 × partial) / total_bugs × 100
ai_usage_score   = LLM review score (0–100), or 0 if LLM is unavailable
overall_score    = 0.70 × automated_score + 0.30 × ai_usage_score
```

---

## Security Notes

- Passwords hashed with bcrypt via `passlib`
- JWTs signed with `HS256`, secret loaded from env
- `bug_manifest_path` is stored in the DB but **never** returned by any candidate-facing endpoint
- File uploads: extension whitelist + 50 MB streaming cap
- Internal grading callback protected by `X-Internal-Api-Key` header (not JWT)
- Cookies: `httpOnly=True`, `SameSite=Lax`
- No raw stack traces returned to the client (RFC 7807 ProblemDetails responses)

> **CSRF**: SameSite=Lax provides protection against most CSRF vectors. For higher-security deployments, add CSRF token middleware (out of scope for v1).

> **Candidate code execution** (pytest mode): The grading service runs candidate-submitted test files in a subprocess. In production, run the grading service in a sandboxed environment (Docker, VM, or gVisor). Documented here per the spec requirement.

---

## Assumptions

1. **Candidate account creation**: No self-registration in v1. Admins create accounts manually (see Section 4 above).
2. **File storage**: Local disk under `backend/uploads/`. In production, swap `file_service.py` for S3 or similar.
3. **Grading is synchronous**: The backend blocks on the grading service HTTP call (120s timeout). Async job queue is out of scope for v1.
4. **Log file formats**: JSON exports (Cursor, Windsurf, Claude Desktop), plain text, and markdown are all handled. Other formats degrade gracefully (still parsed as plain text).
5. **LLM model**: `gpt-4o-mini` by default. Change `OPENAI_MODEL` in `.env` to use any OpenAI-compatible model.
6. **Due date timezone**: All due dates are stored and interpreted as UTC. The UI displays "UTC" to avoid ambiguity.
7. **Re-submission**: Candidates can re-upload before the deadline (overwrites previous files). After the deadline, uploads are rejected server-side.
8. **Grading result write-back**: The grading service POSTs results back to the backend via HTTP (not direct DB access). This avoids sharing DB credentials with the grading service.

---

## Out of Scope (v1)

- In-browser code editor or terminal
- Real-time proctoring, webcam, tab-switch detection
- Async job queue for grading
- Multi-tenant / org support, billing, email notifications
- AI tooling embedded in the portal itself
- Candidate self-registration or invite flow
