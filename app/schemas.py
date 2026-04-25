from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RoleName = Literal["user", "staff", "admin"]
SeverityName = Literal["info", "warning", "critical"]
ScenarioName = Literal[
    "normal",
    "rush-hour",
    "event-surge",
    "electricity-failure",
    "train-breakdown",
    "track-intrusion",
    "ventilation-failure",
]


class LoginPayload(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=6, max_length=120)
    portal: Literal["public", "staff"] = "public"


class RegisterPayload(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=8, max_length=120)


class AlertPayload(BaseModel):
    title: str = Field(min_length=4, max_length=100)
    message: str = Field(min_length=8, max_length=280)
    severity: SeverityName = "warning"


class ScenarioPayload(BaseModel):
    scenario_id: ScenarioName
    affected_station_ids: list[str] = Field(default_factory=list, max_length=8)
    affected_segment_ids: list[str] = Field(default_factory=list, max_length=8)
    notes: str = Field(default="", max_length=280)


class StaffCreatePayload(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=8, max_length=120)
    role: Literal["staff", "admin"] = "staff"


class StaffUpdatePayload(BaseModel):
    is_active: bool | None = None
    role: Literal["staff", "admin"] | None = None

