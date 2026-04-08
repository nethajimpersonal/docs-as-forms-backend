from pydantic import BaseModel
from typing import Dict

class FormCreate(BaseModel):
    fields: Dict[str, str]  # e.g., {"name": "text", "email": "text"}

class FormFill(BaseModel):
    values: Dict[str, str]  # e.g., {"name": "John", "email": "john@example.com"}


class SaveFormSubmissionRequest(BaseModel):
    form_id: str
    submission_id: str
