from pydantic import BaseModel, Field


class InterventionGenerateRequest(BaseModel):
    student_id: int


class InterventionEditRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=10, max_length=10000)