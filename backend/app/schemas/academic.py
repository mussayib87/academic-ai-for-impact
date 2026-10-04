from pydantic import BaseModel, ConfigDict, Field, model_validator


class SubjectAcademicRecordUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    fa1: float | None = Field(default=None, ge=0, le=25)
    fa2: float | None = Field(default=None, ge=0, le=25)
    assignment_mark: float | None = Field(default=None, ge=0, le=25)
    attendance_rate: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode='after')
    def require_a_recorded_field(self):
        if not self.model_fields_set:
            raise ValueError('Provide at least one academic field to update.')
        return self
