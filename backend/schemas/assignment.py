import uuid
from datetime import datetime

from pydantic import BaseModel


class AssignmentCreate(BaseModel):
    title: str
    description: str = ""
    rubric_text: str = ""


class AssignmentOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    rubric_text: str
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class AssignmentCandidateOut(BaseModel):
    """Candidate-safe view — NO zip_file_path, NO bug_manifest_path exposed."""
    id: uuid.UUID
    title: str
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}
