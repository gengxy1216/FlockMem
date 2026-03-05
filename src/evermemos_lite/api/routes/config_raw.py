from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from evermemos_lite.service.extractor_factory import build_memory_extractor

router = APIRouter(prefix="/api/v1/config", tags=["config"])


class RawConfigPatch(BaseModel):
    config: dict[str, Any]


@router.get("/raw")
async def get_raw_config(request: Request) -> dict[str, Any]:
    config_repo = request.app.state.config_repo
    payload = config_repo.get_raw_config(request.app.state.settings)
    return {
        "status": "ok",
        "result": {
            "config": payload,
            "path": str(config_repo.config_path),
        },
    }


@router.put("/raw")
async def put_raw_config(request: Request, payload: RawConfigPatch) -> dict[str, Any]:
    config_repo = request.app.state.config_repo
    old_payload = config_repo.get_raw_config(request.app.state.settings)
    updated_payload = config_repo.replace_raw_config(
        bootstrap_settings=request.app.state.settings,
        payload=payload.config,
    )
    runtime_model_config = config_repo.get_runtime_model_config(request.app.state.settings)
    request.app.state.runtime_model_config.clear()
    request.app.state.runtime_model_config.update(runtime_model_config)
    request.app.state.chat_responder.base_url = str(
        runtime_model_config.get("chat_base_url", "")
    )
    request.app.state.chat_responder.api_key = str(
        runtime_model_config.get("chat_api_key", "")
    )
    request.app.state.chat_responder.model = str(
        runtime_model_config.get("chat_model", "")
    )
    request.app.state.chat_responder.provider = str(
        runtime_model_config.get("chat_provider", "openai")
    )
    request.app.state.memory_service.extractor = build_memory_extractor(
        settings=request.app.state.settings,
        runtime_model_config=request.app.state.runtime_model_config,
    )
    old_settings = old_payload.get("settings") if isinstance(old_payload, dict) else {}
    new_settings = (
        updated_payload.get("settings") if isinstance(updated_payload, dict) else {}
    )
    restart_required = old_settings != new_settings
    return {
        "status": "ok",
        "result": {
            "saved": True,
            "restart_required": bool(restart_required),
            "path": str(config_repo.config_path),
            "config": updated_payload,
        },
    }
