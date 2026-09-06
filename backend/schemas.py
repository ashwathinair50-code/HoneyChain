from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal


class Strict(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, str_strip_whitespace=False
    )


class TelemetryIn(Strict):
    device_id: str = Field(min_length=1, max_length=64)
    hive_id: str = Field(min_length=1, max_length=64)
    beekeeper_id: str = Field(min_length=1, max_length=64)
    timestamp: datetime
    weight_kg: float = Field(ge=0, le=200, strict=True)
    temperature_c: float = Field(ge=-40, le=80, strict=True)
    humidity_percent: float = Field(ge=0, le=100, strict=True)

    @field_validator("timestamp")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Explicit timezone required")
        return value.astimezone(timezone.utc)


class ExtractionIn(Strict):
    client_operation_id: UUID
    apiary_id: str
    source_hive_ids: list[str] = Field(min_length=1, max_length=100)
    extracted_at: datetime
    quantity_kg: Decimal = Field(gt=0, le=10000, max_digits=10, decimal_places=3)
    honey_type: str | None = Field(default=None, max_length=120)
    _aware = field_validator("extracted_at")(TelemetryIn.aware.__func__)

    @field_validator("source_hive_ids")
    @classmethod
    def distinct(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Duplicate source hives")
        return value


class SyncIn(Strict):
    operations: list[ExtractionIn] = Field(min_length=1, max_length=50)


class Parameter(Strict):
    code: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=40)
    method: str = Field(min_length=1, max_length=150)


class ResultIn(Strict):
    report_reference: str = Field(min_length=1, max_length=150)
    tested_at: datetime
    parameters: list[Parameter] = Field(min_length=1, max_length=30)
    outcome: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    evidence_reference: str = Field(min_length=1, max_length=500)
    report_content: str | None = Field(default=None, min_length=1, max_length=100000)
    supersedes_result_id: str | None = None
    _aware = field_validator("tested_at")(TelemetryIn.aware.__func__)


class VersionIn(Strict):
    expected_version: int = Field(ge=1)


class AssignmentIn(VersionIn):
    lab_id: str


class ApprovalIn(VersionIn):
    finalized_result_id: str
    comment: str = Field(default="", max_length=1000)


class RejectionIn(VersionIn):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Rejection reason must not be blank")
        return value


class MaintenanceIn(Strict):
    occurred_at: datetime
    description: str = Field(min_length=1, max_length=300)
    _aware = field_validator("occurred_at")(TelemetryIn.aware.__func__)
