from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from flockmem.api.redaction import restore_redacted
from flockmem.api.security import require_admin_access
from flockmem.config.config_json import compact_model_config_for_storage
from flockmem.domain.policy import RuntimePolicy
from flockmem.service.chat_pipeline import execute_chat_query
from flockmem.service.embedding_factory import build_embedding_provider
from flockmem.service.extractor_factory import build_memory_extractor
from flockmem.service.panel_service import normalize_locale

router = APIRouter(prefix="/api/v1/panel", tags=["panel"])


class PanelChatRequest(BaseModel):
    question: str | None = Field(default=None, max_length=8000)
    query: str | None = Field(default=None, max_length=8000)
    user_id: str | None = None
    group_id: str | None = None
    conversation_id: str | None = None
    locale: str | None = None

    @model_validator(mode="after")
    def _normalize_question(self) -> "PanelChatRequest":
        value = str(self.question or self.query or "").strip()
        if not value:
            raise ValueError("question must not be blank")
        self.question = value
        return self


class PanelAssistantRegistryRequest(BaseModel):
    source_code: str = Field(min_length=1, max_length=80)
    assistant_name: str = Field(min_length=1, max_length=160)
    subassistant_name: str | None = Field(default=None, max_length=160)
    workspace_roots: list[str] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=500)


def _service(request: Request):
    return request.app.state.panel_service


def _panel_scan_roots(request: Request) -> list:
    settings = request.app.state.settings
    roots = [settings.config_path.parent, settings.data_dir]
    unique = []
    seen = set()
    for path in roots:
        token = str(path)
        if not token or token in seen:
            continue
        seen.add(token)
        unique.append(path)
    return unique


def _refresh_runtime_state(
    request: Request,
    *,
    previous_settings_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config_repo = request.app.state.config_repo
    current_settings = request.app.state.settings
    new_settings = config_repo.get_effective_settings(current_settings)
    request.app.state.settings = new_settings
    runtime_model_config = config_repo.get_runtime_model_config(new_settings)
    request.app.state.runtime_model_config.clear()
    request.app.state.runtime_model_config.update(runtime_model_config)
    request.app.state.chat_responder.base_url = str(runtime_model_config.get("chat_base_url", ""))
    request.app.state.chat_responder.api_key = str(runtime_model_config.get("chat_api_key", ""))
    request.app.state.chat_responder.model = str(runtime_model_config.get("chat_model", ""))
    request.app.state.chat_responder.provider = str(
        runtime_model_config.get("chat_provider", "openai")
    )
    request.app.state.memory_service.extractor = build_memory_extractor(
        settings=new_settings,
        runtime_model_config=request.app.state.runtime_model_config,
    )
    request.app.state.memory_service.embedding_provider = build_embedding_provider(
        settings=new_settings,
        runtime_model_config=request.app.state.runtime_model_config,
    )
    request.app.state.graph_store.enabled = bool(new_settings.graph_enabled)
    request.app.state.memory_service.search_trace_enabled = bool(new_settings.search_trace_enabled)
    request.app.state.memory_service.recall_mode = bool(new_settings.recall_mode)
    settings_doc = previous_settings_doc if isinstance(previous_settings_doc, dict) else {}
    restart_required = any(
        settings_doc.get(key) != getattr(new_settings, key)
        for key in (
            "embedding_provider",
            "embedding_model",
            "recall_mode",
            "local_embedding_model",
            "local_embedding_device",
        )
        if key in settings_doc
    )
    return {
        "settings": new_settings,
        "runtime_model_config": runtime_model_config,
        "restart_required": restart_required,
    }


def _normalize_settings_update(payload: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if isinstance(payload.get("values"), dict):
        updates.update(payload["values"])
    if isinstance(payload.get("items"), list):
        for item in payload["items"]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("setting_key") or item.get("item_code") or "").strip()
            if not key:
                continue
            if "value" in item:
                updates[key] = item.get("value")
            elif "value_code" in item:
                updates[key] = item.get("value_code")
    for key in (
        "chat_provider",
        "chat_model",
        "embedding_provider",
        "embedding_model",
        "extractor_provider",
        "extractor_model",
        "retrieval_profile",
        "recall_mode",
        "graph_enabled",
        "search_trace_enabled",
        "authorized_scan_roots",
        "assistant_auto_sync_enabled",
    ):
        if key in payload:
            updates[key] = payload.get(key)
    return updates


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    return token in {"1", "true", "yes", "on"}


@router.get("/overview")
async def panel_overview(request: Request, locale: str | None = None) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    result = _service(request).overview(
        locale=resolved_locale,
        scan_roots=_panel_scan_roots(request),
        config_repo=request.app.state.config_repo,
        settings=request.app.state.settings,
    )
    return {"status": "ok", "result": result}


@router.get("/assistants")
async def panel_assistants(request: Request, locale: str | None = None) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    result = _service(request).assistants(
        locale=resolved_locale,
        scan_roots=_panel_scan_roots(request),
        config_repo=request.app.state.config_repo,
        settings=request.app.state.settings,
    )
    return {"status": "ok", "result": result}


@router.get("/assistants/{assistant_id}")
async def panel_assistant_detail(
    assistant_id: str,
    request: Request,
    locale: str | None = None,
) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    result = _service(request).assistant_detail(
        assistant_id=assistant_id,
        locale=resolved_locale,
        scan_roots=_panel_scan_roots(request),
        config_repo=request.app.state.config_repo,
        settings=request.app.state.settings,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="assistant not found")
    return {"status": "ok", "result": result}


@router.post("/assistants/registry", dependencies=[Depends(require_admin_access)])
async def panel_assistant_registry_create(
    payload: PanelAssistantRegistryRequest,
    request: Request,
    locale: str | None = None,
) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    service = _service(request)
    normalized = service.normalize_assistant_registry_entry(
        payload=payload.model_dump(),
        scan_roots=_panel_scan_roots(request),
    )
    if normalized is None:
        raise HTTPException(status_code=400, detail="invalid assistant registry payload")
    config_repo = request.app.state.config_repo
    raw_config = config_repo.get_raw_config(request.app.state.settings)
    panel_doc = dict(raw_config.get("panel") or {}) if isinstance(raw_config.get("panel"), dict) else {}
    registry_items = service._assistant_registry_items(
        config_repo=config_repo,
        settings=request.app.state.settings,
        scan_roots=_panel_scan_roots(request),
    )
    registry_items = [
        item
        for item in registry_items
        if str(item.get("assistant_id") or "") != str(normalized.get("assistant_id") or "")
    ]
    registry_items.append(normalized)
    panel_doc["assistant_registry"] = service.serialize_assistant_registry_items(registry_items)
    raw_config["panel"] = panel_doc
    config_repo.replace_raw_config(
        bootstrap_settings=request.app.state.settings,
        payload=raw_config,
    )
    result = service.assistants(
        locale=resolved_locale,
        scan_roots=_panel_scan_roots(request),
        config_repo=config_repo,
        settings=request.app.state.settings,
    )
    return {"status": "ok", "result": result}


@router.delete(
    "/assistants/registry/{assistant_id}",
    dependencies=[Depends(require_admin_access)],
)
async def panel_assistant_registry_delete(
    assistant_id: str,
    request: Request,
    locale: str | None = None,
) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    service = _service(request)
    config_repo = request.app.state.config_repo
    raw_config = config_repo.get_raw_config(request.app.state.settings)
    panel_doc = dict(raw_config.get("panel") or {}) if isinstance(raw_config.get("panel"), dict) else {}
    registry_items = service._assistant_registry_items(
        config_repo=config_repo,
        settings=request.app.state.settings,
        scan_roots=_panel_scan_roots(request),
    )
    remaining = [
        item
        for item in registry_items
        if str(item.get("assistant_id") or "") != str(assistant_id or "")
    ]
    deleted = len(remaining) != len(registry_items)
    panel_doc["assistant_registry"] = service.serialize_assistant_registry_items(remaining)
    raw_config["panel"] = panel_doc
    config_repo.replace_raw_config(
        bootstrap_settings=request.app.state.settings,
        payload=raw_config,
    )
    result = service.assistants(
        locale=resolved_locale,
        scan_roots=_panel_scan_roots(request),
        config_repo=config_repo,
        settings=request.app.state.settings,
    )
    return {"status": "ok", "result": {"deleted": deleted, "assistants": result}}


@router.get("/feedback")
async def panel_feedback(request: Request, locale: str | None = None) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    result = _service(request).feedback(locale=resolved_locale)
    return {"status": "ok", "result": result}


@router.get("/feedback/{feedback_id}")
async def panel_feedback_detail(
    feedback_id: str,
    request: Request,
    locale: str | None = None,
) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    result = _service(request).feedback_detail(feedback_id=feedback_id, locale=resolved_locale)
    if result is None:
        raise HTTPException(status_code=404, detail="feedback not found")
    return {"status": "ok", "result": result}


@router.get("/memories")
async def panel_memories(
    request: Request,
    locale: str | None = None,
    query: str | None = None,
    user_id: str | None = None,
    group_id: str | None = None,
    sender: str | None = None,
    target: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    result = _service(request).memories(
        locale=resolved_locale,
        query=query,
        user_id=user_id,
        group_id=group_id,
        sender=sender,
        target=target,
        limit=limit,
    )
    return {"status": "ok", "result": result}


@router.get("/memories/{memory_id}")
async def panel_memory_detail(
    memory_id: str,
    request: Request,
    locale: str | None = None,
) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    result = _service(request).memory_detail(memory_id=memory_id, locale=resolved_locale)
    if result is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"status": "ok", "result": result}


@router.post("/chat")
async def panel_chat(payload: PanelChatRequest, request: Request) -> dict[str, Any]:
    resolved_locale = normalize_locale(payload.locale, request.headers.get("accept-language"))
    chat_result = await execute_chat_query(
        request=request,
        query=str(payload.question or ""),
        user_id=payload.user_id,
        group_id=payload.group_id,
        conversation_id=payload.conversation_id,
        top_k=8,
    )
    result = _service(request).chat(
        question=str(payload.question or ""),
        locale=resolved_locale,
        chat_result=chat_result,
    )
    return {"status": "ok", "result": result}


@router.get("/settings")
async def panel_settings(request: Request, locale: str | None = None) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    result = _service(request).settings(
        locale=resolved_locale,
        settings=request.app.state.settings,
        runtime_model_config=request.app.state.runtime_model_config,
        runtime_policy_repo=request.app.state.runtime_policy_repo,
        config_repo=request.app.state.config_repo,
    )
    return {"status": "ok", "result": result}


@router.get("/settings/raw")
async def panel_settings_raw(request: Request, locale: str | None = None) -> dict[str, Any]:
    resolved_locale = normalize_locale(locale, request.headers.get("accept-language"))
    result = _service(request).settings_raw(
        locale=resolved_locale,
        settings=request.app.state.settings,
        config_repo=request.app.state.config_repo,
    )
    return {"status": "ok", "result": result}


@router.put("/settings", dependencies=[Depends(require_admin_access)])
async def panel_settings_update(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    updates = _normalize_settings_update(payload if isinstance(payload, dict) else {})
    if not updates:
        raise HTTPException(status_code=400, detail="no settings updates provided")
    config_repo = request.app.state.config_repo
    current_settings = request.app.state.settings
    old_payload = config_repo.get_raw_config(current_settings)
    settings_doc = dict(old_payload.get("settings") or {}) if isinstance(old_payload.get("settings"), dict) else {}
    previous_settings_doc = dict(settings_doc)
    runtime_model_config = dict(request.app.state.runtime_model_config)
    settings_changed = False
    model_changed = False
    panel_changed = False
    panel_doc = dict(old_payload.get("panel") or {}) if isinstance(old_payload.get("panel"), dict) else {}

    for key, value in updates.items():
        if key in {
            "chat_provider",
            "chat_model",
            "embedding_provider",
            "embedding_model",
            "extractor_provider",
            "extractor_model",
        }:
            runtime_model_config[key] = str(value or "").strip()
            model_changed = True
            continue
        if key == "retrieval_profile":
            settings_doc["retrieval_profile"] = str(value or "").strip() or "agentic"
            current_policy = request.app.state.runtime_policy_repo.get("default") or RuntimePolicy()
            request.app.state.runtime_policy_repo.upsert(
                "default",
                current_policy.merged_with(
                    RuntimePolicy(
                        profile=settings_doc["retrieval_profile"],
                        reason="panel_settings",
                    )
                ),
            )
            settings_changed = True
            continue
        if key in {"recall_mode", "graph_enabled", "search_trace_enabled"}:
            settings_doc[key] = _coerce_bool(value)
            settings_changed = True
            continue
        if key == "authorized_scan_roots":
            roots = value if isinstance(value, list) else str(value or "").splitlines()
            panel_doc["authorized_scan_roots"] = [
                str(item).strip() for item in roots if str(item).strip()
            ]
            panel_changed = True
            continue
        if key == "assistant_auto_sync_enabled":
            panel_doc["assistant_auto_sync_enabled"] = _coerce_bool(value)
            panel_changed = True

    next_payload = dict(old_payload)
    if settings_changed:
        next_payload["settings"] = settings_doc
    if model_changed:
        next_payload["models"] = compact_model_config_for_storage(runtime_model_config, current_settings)
    if panel_changed:
        next_payload["panel"] = panel_doc
    config_repo.replace_raw_config(
        bootstrap_settings=current_settings,
        payload=next_payload,
    )
    refresh_state = _refresh_runtime_state(
        request,
        previous_settings_doc=previous_settings_doc,
    )
    resolved_locale = normalize_locale(
        payload.get("locale") if isinstance(payload, dict) else None,
        request.headers.get("accept-language"),
    )
    result = _service(request).settings(
        locale=resolved_locale,
        settings=request.app.state.settings,
        runtime_model_config=request.app.state.runtime_model_config,
        runtime_policy_repo=request.app.state.runtime_policy_repo,
        config_repo=request.app.state.config_repo,
    )
    result["saved"] = True
    result["restart_required"] = bool(
        refresh_state["restart_required"]
        or any(key in updates for key in {"embedding_provider", "embedding_model", "recall_mode"})
    )
    result["updated_keys"] = sorted(updates.keys())
    return {"status": "ok", "result": result}


@router.put("/settings/raw", dependencies=[Depends(require_admin_access)])
async def panel_settings_raw_update(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    config_repo = request.app.state.config_repo
    current_settings = request.app.state.settings
    old_payload = config_repo.get_raw_config(current_settings)
    previous_settings_doc = (
        dict(old_payload.get("settings") or {}) if isinstance(old_payload.get("settings"), dict) else {}
    )
    if isinstance(body.get("config"), dict):
        merged_payload = restore_redacted(body.get("config") or {}, old_payload)
    else:
        raw_text = str(body.get("raw_json") or body.get("raw_text") or "").strip()
        if not raw_text:
            raise HTTPException(status_code=400, detail="raw config payload is required")
        try:
            parsed = json.loads(raw_text)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid raw json: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="raw config must be a JSON object")
        merged_payload = restore_redacted(parsed, old_payload)
    updated_payload = config_repo.replace_raw_config(
        bootstrap_settings=current_settings,
        payload=merged_payload,
    )
    refresh_state = _refresh_runtime_state(
        request,
        previous_settings_doc=previous_settings_doc,
    )
    resolved_locale = normalize_locale(body.get("locale"), request.headers.get("accept-language"))
    result = _service(request).settings_raw(
        locale=resolved_locale,
        settings=request.app.state.settings,
        config_repo=config_repo,
    )
    result["saved"] = True
    result["restart_required"] = bool(refresh_state["restart_required"])
    result["config"] = updated_payload if body.get("include_unredacted") else result["config"]
    return {"status": "ok", "result": result}
