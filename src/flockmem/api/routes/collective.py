from __future__ import annotations

from typing import Any, Literal

import anyio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/v1/collective", tags=["collective"])
# TODO(v1-contract): 当前为最小可运行契约；待产品/架构定稿后补齐完整 envelope 字段约束与错误码矩阵。


class CollectiveIngestRequest(BaseModel):
    knowledge_id: str | None = None
    revision_id: str | None = None
    parent_revision_id: str | None = None
    scope_type: Literal["personal", "team", "global"]
    scope_id: str | None = None
    content: dict[str, Any]
    change_type: Literal["create", "update", "deprecate", "rollback"] = "update"
    changed_by: Literal["agent", "user", "system"] = "agent"
    actor_id: str | None = None
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    read_acl: list[str] = Field(default_factory=list)
    write_acl: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    coordination_mode: str | None = None
    coordination_id: str | None = None
    runtime_id: str | None = None
    agent_id: str | None = None
    subagent_id: str | None = None
    team_id: str | None = None
    session_id: str | None = None

    @field_validator(
        "knowledge_id",
        "revision_id",
        "parent_revision_id",
        "scope_id",
        "actor_id",
        "coordination_mode",
        "coordination_id",
        "runtime_id",
        "agent_id",
        "subagent_id",
        "team_id",
        "session_id",
        mode="before",
    )
    @classmethod
    def _normalize_tokens(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("read_acl", "write_acl", mode="before")
    @classmethod
    def _normalize_acl(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
        return out


class CollectiveContextRequest(BaseModel):
    query: str | None = None
    actor_id: str | None = None
    scope_type: Literal["personal", "team", "global"] | None = None
    scope_id: str | None = None
    personal_scope_id: str | None = None
    team_scope_id: str | None = None
    include_global: bool = True
    top_k: int = Field(default=20, ge=1, le=100)
    coordination_mode: str | None = None
    coordination_id: str | None = None
    runtime_id: str | None = None
    agent_id: str | None = None
    subagent_id: str | None = None
    team_id: str | None = None
    session_id: str | None = None

    @field_validator(
        "query",
        "actor_id",
        "scope_type",
        "scope_id",
        "personal_scope_id",
        "team_scope_id",
        "coordination_mode",
        "coordination_id",
        "runtime_id",
        "agent_id",
        "subagent_id",
        "team_id",
        "session_id",
        mode="before",
    )
    @classmethod
    def _normalize_tokens(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class CollectiveFeedbackRequest(BaseModel):
    knowledge_id: str
    revision_id: str | None = None
    feedback_type: str
    feedback_payload: dict[str, Any]
    actor: str
    coordination_mode: str | None = None
    coordination_id: str | None = None
    runtime_id: str | None = None
    agent_id: str | None = None
    subagent_id: str | None = None
    team_id: str | None = None
    session_id: str | None = None

    @field_validator(
        "knowledge_id",
        "revision_id",
        "feedback_type",
        "actor",
        "coordination_mode",
        "coordination_id",
        "runtime_id",
        "agent_id",
        "subagent_id",
        "team_id",
        "session_id",
        mode="before",
    )
    @classmethod
    def _normalize_tokens(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


@router.post("/ingest")
async def collective_ingest(
    payload: CollectiveIngestRequest,
    request: Request,
) -> dict[str, Any]:
    service = request.app.state.core_loop_service
    try:
        result = await anyio.to_thread.run_sync(service.ingest, payload.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "message": "ingest accepted", "result": result}


@router.post("/context")
async def collective_context(
    payload: CollectiveContextRequest,
    request: Request,
) -> dict[str, Any]:
    service = request.app.state.core_loop_service
    try:
        result = await anyio.to_thread.run_sync(service.context, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "message": "context resolved", "result": result}


@router.post("/feedback")
async def collective_feedback(
    payload: CollectiveFeedbackRequest,
    request: Request,
) -> dict[str, Any]:
    service = request.app.state.core_loop_service
    try:
        result = await anyio.to_thread.run_sync(service.feedback, payload.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "message": "feedback accepted", "result": result}
