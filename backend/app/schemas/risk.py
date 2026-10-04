from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic import StrictInt
from typing import Literal

from ai.risk.features import FEATURES


class RiskFeatureInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    attendance: float = Field(ge=0, le=100)
    assessment: float = Field(ge=0, le=100)
    previous_gpa: float = Field(ge=0, le=4)
    current_gpa: float = Field(ge=0, le=4)
    assignments_completed: float = Field(ge=0)
    activity_per_week: float = Field(ge=0)
    missing_submissions: float = Field(ge=0)
    attendance_change: float
    assessment_change: float
    momentum_score: float
    student_id: StrictInt | None = None

    def feature_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in FEATURES}


class RiskPredictionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    risk_level: str = Field(description='Model class with the highest predicted probability.')
    risk_probability: float = Field(description='Probability of the predicted risk_level class.')
    risk_probability_semantics: str
    risk_level_policy: str
    model_version: str
    prediction_timestamp: datetime
    class_probabilities: dict[str, float]


class ModelRegistryEntryInput(BaseModel):
    model_config = ConfigDict(extra='forbid', protected_namespaces=())

    model_version: str = Field(min_length=1, max_length=80)
    model_type: str = 'classification'
    feature_schema: list[str] | None = None
    feature_contract_version: str | None = None
    training_period: str | None = None
    training_dataset_version: str | None = None
    training_dataset_hash: str | None = None
    training_timestamp: datetime | None = None
    validation_metrics: dict[str, float | int | str | bool] | None = None
    artifact_identifier: str | None = None
    artifact_hash: str | None = None
    status: Literal['candidate'] = 'candidate'
    notes: str | None = None


class RiskSimulationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    student_id: StrictInt | None = None
    scenario: dict[str, float] = Field(default_factory=dict)


class ModelPromotionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    explicit_approval: bool
    approval_note: str = Field(min_length=10, max_length=1000)


class ModelApprovalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    explicit_approval: bool
    approval_note: str = Field(min_length=10, max_length=1000)


class ModelRejectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    rejection_reason: str = Field(min_length=10, max_length=1000)


class ModelRollbackRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    explicit_approval: bool
    rollback_note: str = Field(min_length=10, max_length=1000)


class Phase3PolicyApprovalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    explicit_approval: bool
    aggregation_strategy: Literal['equal_subject_mean']
    feature_contract: list[Literal['fa1_mean', 'fa2_mean', 'assignment_mean', 'attendance_mean']] = Field(min_length=1, max_length=4)
    approval_note: str = Field(min_length=10, max_length=1000)


class Phase3TrainingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    aggregation_strategy: Literal['equal_subject_mean']
    feature_contract: list[Literal['fa1_mean', 'fa2_mean', 'assignment_mean', 'attendance_mean']] = Field(min_length=1)