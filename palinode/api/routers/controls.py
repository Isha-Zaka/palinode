"""HTTP controls for persisted automatic capture and recall policy."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool

from palinode.core.capture_policy import (
    CapturePolicyError,
    evaluate_capture_policy,
    load_capture_policy,
    update_capture_policy,
)


router = APIRouter()


class ControlsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_paused: StrictBool | None = None
    recall_paused: StrictBool | None = None
    excluded_projects: list[str] | None = None
    excluded_paths: list[str] | None = None


class ControlsCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["capture", "recall"]
    cwd: str | None = None
    project: str | None = None
    source_path: str | None = None
    automatic: StrictBool = True


@router.get("/controls")
def controls_status_api() -> dict[str, object]:
    try:
        return load_capture_policy().public()
    except CapturePolicyError as exc:
        raise HTTPException(status_code=503, detail="Capture policy is unavailable") from exc


@router.post("/controls")
def controls_update_api(req: ControlsUpdateRequest) -> dict[str, object]:
    try:
        policy, committed = update_capture_policy(**req.model_dump())
        return policy.public(committed=committed)
    except CapturePolicyError as exc:
        raise HTTPException(status_code=400, detail="Invalid capture policy") from exc


@router.post("/controls/check")
def controls_check_api(req: ControlsCheckRequest) -> dict[str, object]:
    return evaluate_capture_policy(
        req.action,
        automatic=req.automatic,
        cwd=req.cwd,
        project=req.project,
        source_path=req.source_path,
    ).public()
