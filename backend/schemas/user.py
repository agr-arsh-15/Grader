import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from backend.models.user import UserRole


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    created_at: datetime

    model_config = {"from_attributes": True}
