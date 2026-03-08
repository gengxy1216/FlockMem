from __future__ import annotations

import json
import uuid
from typing import Any

from flockmem.infra.sqlite.collective_repository import CollectiveRepository

_VALID_SCOPE_TYPES = {"personal", "team", "global"}
_VALID_CHANGE_TYPES = {"create", "update", "deprecate", "rollback"}
_VALID_ACTORS = {"agent", "user", "system"}


class CoreLoopService:
    def __init__(self, repo: CollectiveRepository) -> None:
        self.repo = repo

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        scope_type = _normalize_token(payload.get("scope_type")).lower()
        if scope_type not in _VALID_SCOPE_TYPES:
            raise ValueError("scope_type must be one of personal/team/global")

        scope_id = _normalize_scope_id(scope_type=scope_type, value=payload.get("scope_id"))
        coordination_id = _normalize_token(payload.get("coordination_id")) or None
        knowledge_id = (
            _normalize_token(payload.get("knowledge_id"))
            or (f"coord:{coordination_id}" if coordination_id else uuid.uuid4().hex)
        )
        change_type = (_normalize_token(payload.get("change_type")) or "update").lower()
        if change_type not in _VALID_CHANGE_TYPES:
            raise ValueError("change_type must be one of create/update/deprecate/rollback")
        changed_by = (_normalize_token(payload.get("changed_by")) or "agent").lower()
        if changed_by not in _VALID_ACTORS:
            raise ValueError("changed_by must be one of agent/user/system")

        actor_id = _normalize_token(payload.get("actor_id")) or changed_by
        content = payload.get("content")
        if not isinstance(content, dict) or not content:
            raise ValueError("content must be a non-empty object")

        read_acl = _normalize_acl(payload.get("read_acl"))
        write_acl = _normalize_acl(payload.get("write_acl"))
        if write_acl and actor_id not in write_acl:
            raise PermissionError("actor is not allowed to write this scope")

        existing = self.repo.get_knowledge_item(knowledge_id)
        if existing:
            if existing.get("scope_type") != scope_type or existing.get("scope_id") != scope_id:
                raise ValueError("knowledge scope cannot change once created")
            existing_write_acl = _normalize_acl(existing.get("write_acl"))
            if existing_write_acl and actor_id not in existing_write_acl:
                raise PermissionError("actor is not allowed to update this knowledge")
            if not read_acl:
                read_acl = _normalize_acl(existing.get("read_acl"))
            if not write_acl:
                write_acl = existing_write_acl

        parent_revision_id = (
            _normalize_token(payload.get("parent_revision_id"))
            or (str(existing.get("canonical_revision_id") or "").strip() if existing else None)
        )
        confidence = _normalize_score(payload.get("confidence"), default=0.6)
        trust_score = _normalize_score(payload.get("trust_score"), default=0.5)
        evidence = _normalize_evidence(payload.get("evidence"))
        normalized_content_json = json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if coordination_id:
            replay = self.repo.find_revision_by_coordination(
                knowledge_id=knowledge_id,
                coordination_id=coordination_id,
                change_type=change_type,
                content_json=normalized_content_json,
            )
            if replay:
                current = self.repo.get_knowledge_item(knowledge_id) or {}
                return {
                    "knowledge_id": knowledge_id,
                    "revision_id": str(replay.get("revision_id") or ""),
                    "state": str(current.get("state") or "canonical"),
                    "canonical_revision_id": current.get("canonical_revision_id"),
                    "scope_type": str(current.get("scope_type") or scope_type),
                    "scope_id": str(current.get("scope_id") or scope_id),
                    "idempotent_replay": True,
                }

        revision_id = _normalize_token(payload.get("revision_id")) or uuid.uuid4().hex
        is_deprecated = change_type == "deprecate"
        state = "deprecated" if is_deprecated else "canonical"
        canonical_revision_id = None if is_deprecated else revision_id
        revision_id = self.repo.apply_ingest_change(
            knowledge_id=knowledge_id,
            scope_type=scope_type,
            scope_id=scope_id,
            state=state,
            canonical_revision_id=canonical_revision_id,
            read_acl=read_acl,
            write_acl=write_acl,
            trust_score=trust_score,
            revision_id=revision_id,
            parent_revision_id=parent_revision_id,
            content=content,
            confidence=confidence,
            change_type=change_type,
            changed_by=changed_by,
            evidence=evidence,
            coordination_mode=_normalize_token(payload.get("coordination_mode")) or None,
            coordination_id=coordination_id,
            runtime_id=_normalize_token(payload.get("runtime_id")) or None,
            agent_id=_normalize_token(payload.get("agent_id")) or None,
            subagent_id=_normalize_token(payload.get("subagent_id")) or None,
            team_id=_normalize_token(payload.get("team_id")) or None,
            session_id=_normalize_token(payload.get("session_id")) or None,
        )
        return {
            "knowledge_id": knowledge_id,
            "revision_id": revision_id,
            "state": state,
            "canonical_revision_id": canonical_revision_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
        }

    def context(self, payload: dict[str, Any]) -> dict[str, Any]:
        actor_id = _normalize_token(payload.get("actor_id")) or None
        scope_type = (_normalize_token(payload.get("scope_type")) or "").lower()
        scope_id = _normalize_token(payload.get("scope_id"))
        personal_scope_id = _normalize_token(payload.get("personal_scope_id"))
        team_scope_id = _normalize_token(payload.get("team_scope_id"))
        include_global = bool(payload.get("include_global", True))
        top_k = max(1, min(int(payload.get("top_k") or 20), 100))

        if scope_type:
            if scope_type not in _VALID_SCOPE_TYPES:
                raise ValueError("scope_type must be one of personal/team/global")
            if scope_type == "global":
                include_global = True
            else:
                scoped_id = _normalize_scope_id(scope_type=scope_type, value=scope_id)
                if scope_type == "personal":
                    personal_scope_id = scoped_id
                if scope_type == "team":
                    team_scope_id = scoped_id

        # Enforce deterministic priority: personal -> team -> global.
        scopes: list[tuple[str, str]] = []
        seen_scopes: set[tuple[str, str]] = set()
        if personal_scope_id:
            token = ("personal", personal_scope_id)
            scopes.append(token)
            seen_scopes.add(token)
        if team_scope_id:
            token = ("team", team_scope_id)
            if token not in seen_scopes:
                scopes.append(token)
                seen_scopes.add(token)
        if include_global:
            token = ("global", "global")
            if token not in seen_scopes:
                scopes.append(token)
                seen_scopes.add(token)

        if not scopes:
            raise ValueError("at least one scope must be provided")

        items = self.repo.get_context_by_scopes(
            scopes=scopes,
            actor_id=actor_id,
            limit=top_k,
        )
        normalized_items: list[dict[str, Any]] = []
        for row in items:
            normalized_items.append(
                {
                    "knowledge_id": str(row.get("knowledge_id") or ""),
                    "scope_type": str(row.get("scope_type") or ""),
                    "scope_id": str(row.get("scope_id") or ""),
                    "state": str(row.get("state") or ""),
                    "revision_id": str(row.get("revision_id") or ""),
                    "content": row.get("content") or {},
                    "confidence": float(row.get("confidence") or 0.0),
                    "trust_score": float(row.get("trust_score") or 0.0),
                    "read_acl": _normalize_acl(row.get("read_acl")),
                    "write_acl": _normalize_acl(row.get("write_acl")),
                }
            )

        return {
            "items": normalized_items,
            "count": len(normalized_items),
            "scope_order": [scope for scope, _ in scopes],
        }

    def feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        knowledge_id = _normalize_token(payload.get("knowledge_id"))
        if not knowledge_id:
            raise ValueError("knowledge_id is required")
        item = self.repo.get_knowledge_item(knowledge_id)
        if not item:
            raise KeyError("knowledge not found")
        revision_id = _normalize_token(payload.get("revision_id")) or None
        revision: dict[str, Any] | None = None
        if revision_id:
            revision = self.repo.get_revision(revision_id)
            if not revision:
                raise KeyError("revision not found")
            revision_knowledge_id = _normalize_token(revision.get("knowledge_id"))
            if revision_knowledge_id != knowledge_id:
                raise ValueError("revision does not belong to knowledge_id")

        feedback_type = _normalize_token(payload.get("feedback_type")).lower()
        if not feedback_type:
            raise ValueError("feedback_type is required")
        actor = _normalize_token(payload.get("actor"))
        if not actor:
            raise ValueError("actor is required")
        write_acl = _normalize_acl(item.get("write_acl"))
        if write_acl and actor not in write_acl:
            raise PermissionError("actor is not allowed to update this knowledge")
        feedback_payload = payload.get("feedback_payload")
        if not isinstance(feedback_payload, dict):
            raise ValueError("feedback_payload must be an object")
        coordination_mode = _normalize_token(payload.get("coordination_mode")) or (
            _normalize_token(revision.get("coordination_mode")) if revision else None
        ) or None
        coordination_id = _normalize_token(payload.get("coordination_id")) or (
            _normalize_token(revision.get("coordination_id")) if revision else None
        ) or None
        runtime_id = _normalize_token(payload.get("runtime_id")) or (
            _normalize_token(revision.get("runtime_id")) if revision else None
        ) or None
        agent_id = _normalize_token(payload.get("agent_id")) or (
            _normalize_token(revision.get("agent_id")) if revision else None
        ) or None
        subagent_id = _normalize_token(payload.get("subagent_id")) or (
            _normalize_token(revision.get("subagent_id")) if revision else None
        ) or None
        team_id = _normalize_token(payload.get("team_id")) or (
            _normalize_token(revision.get("team_id")) if revision else None
        ) or None
        session_id = _normalize_token(payload.get("session_id")) or (
            _normalize_token(revision.get("session_id")) if revision else None
        ) or None
        normalized_feedback_payload_json = json.dumps(
            feedback_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        is_idempotent_replay = False
        replay_feedback: dict[str, Any] | None = None
        if coordination_id:
            replay_feedback = self.repo.find_feedback_by_coordination(
                knowledge_id=knowledge_id,
                coordination_id=coordination_id,
                feedback_type=feedback_type,
                actor=actor,
                feedback_payload_json=normalized_feedback_payload_json,
            )
            is_idempotent_replay = replay_feedback is not None
            if is_idempotent_replay and not revision_id:
                revision_id = _normalize_token((replay_feedback or {}).get("revision_id")) or None
                if revision_id and not revision:
                    revision = self.repo.get_revision(revision_id)
        revise_plan = self._plan_revise_after_feedback(
            item=item,
            revision_id=revision_id,
            revision=revision,
            feedback_type=feedback_type,
            feedback_payload=feedback_payload,
            is_idempotent_replay=is_idempotent_replay,
        )
        feedback_id, is_replay = self.repo.apply_feedback_and_revise(
            knowledge_id=knowledge_id,
            revision_id=revision_id,
            feedback_type=feedback_type,
            feedback_payload=feedback_payload,
            actor=actor,
            coordination_mode=coordination_mode,
            coordination_id=coordination_id,
            runtime_id=runtime_id,
            agent_id=agent_id,
            subagent_id=subagent_id,
            team_id=team_id,
            session_id=session_id,
            revise_state=(
                str(revise_plan.get("state") or "")
                if bool(revise_plan.get("persist_update"))
                else None
            ),
            revise_canonical_revision_id=(
                revise_plan.get("canonical_revision_id")
                if bool(revise_plan.get("persist_update"))
                else None
            ),
            revise_trust_score=(
                float(revise_plan.get("trust_score") or 0.0)
                if bool(revise_plan.get("persist_update"))
                else None
            ),
            revise_read_acl=(
                _normalize_acl(item.get("read_acl"))
                if bool(revise_plan.get("persist_update"))
                else None
            ),
            revise_write_acl=(
                write_acl if bool(revise_plan.get("persist_update")) else None
            ),
        )
        return {
            "knowledge_id": knowledge_id,
            "feedback_id": feedback_id,
            "idempotent_replay": is_replay,
            "revise_applied": bool(revise_plan.get("revise_applied")),
            "revise_action": str(revise_plan.get("revise_action") or "noop"),
            "state": str(revise_plan.get("state") or ""),
            "canonical_revision_id": revise_plan.get("canonical_revision_id"),
        }

    def _plan_revise_after_feedback(
        self,
        *,
        item: dict[str, Any],
        revision_id: str | None,
        revision: dict[str, Any] | None,
        feedback_type: str,
        feedback_payload: dict[str, Any],
        is_idempotent_replay: bool = False,
    ) -> dict[str, Any]:
        outcome = self._resolve_outcome_status(
            feedback_type=feedback_type,
            feedback_payload=feedback_payload,
        )
        current_state = _normalize_token(item.get("state")).lower() or "draft"
        current_canonical = _normalize_token(item.get("canonical_revision_id")) or None
        trust_score = _normalize_score(item.get("trust_score"), default=0.5)
        if not outcome:
            return {
                "revise_applied": False,
                "revise_action": "noop",
                "state": current_state,
                "canonical_revision_id": current_canonical,
                "trust_score": trust_score,
                "persist_update": False,
            }

        target_revision_id = revision_id or current_canonical
        target_revision = revision
        if target_revision_id and not target_revision:
            target_revision = self.repo.get_revision(target_revision_id)
        stale_replay_target = bool(
            is_idempotent_replay
            and target_revision_id
            and current_canonical
            and target_revision_id != current_canonical
        )
        if stale_replay_target:
            return {
                "revise_applied": False,
                "revise_action": "stale_replay_noop",
                "state": current_state,
                "canonical_revision_id": current_canonical,
                "trust_score": trust_score,
                "persist_update": False,
            }

        if outcome == "failed":
            rollback_flag = _to_bool(feedback_payload.get("rollback_flag"))
            parent_revision_id = (
                _normalize_token((target_revision or {}).get("parent_revision_id")) or None
            )
            should_rollback = bool(
                target_revision_id
                and parent_revision_id
                and (rollback_flag or target_revision_id == current_canonical)
            )
            if should_rollback:
                next_canonical = parent_revision_id
                next_state = "canonical"
                action = "rollback_to_parent"
            else:
                next_canonical = None
                next_state = "deprecated"
                action = "demote_deprecated"
            next_trust = max(0.0, trust_score - 0.2)
            return {
                "revise_applied": True,
                "revise_action": action,
                "state": next_state,
                "canonical_revision_id": next_canonical,
                "trust_score": next_trust,
                "persist_update": True,
            }

        if outcome == "success":
            next_canonical = target_revision_id or current_canonical
            if not next_canonical:
                return {
                    "revise_applied": False,
                    "revise_action": "noop_no_revision",
                    "state": current_state,
                    "canonical_revision_id": current_canonical,
                    "trust_score": trust_score,
                    "persist_update": False,
                }
            reuse_hit = _to_bool(feedback_payload.get("reuse_hit"))
            retry_count = _to_non_negative_int(feedback_payload.get("retry_count"))
            tool_error_count = _to_non_negative_int(feedback_payload.get("tool_error_count"))
            boost = 0.1 if reuse_hit and retry_count == 0 and tool_error_count == 0 else 0.05
            next_trust = min(1.0, trust_score + boost)
            next_state = "canonical"
            action = (
                "keep_canonical"
                if current_state == "canonical" and current_canonical == next_canonical
                else "promote_canonical"
            )
            return {
                "revise_applied": True,
                "revise_action": action,
                "state": next_state,
                "canonical_revision_id": next_canonical,
                "trust_score": next_trust,
                "persist_update": True,
            }

        return {
            "revise_applied": False,
            "revise_action": "noop",
            "state": current_state,
            "canonical_revision_id": current_canonical,
            "trust_score": trust_score,
            "persist_update": False,
        }

    def _resolve_outcome_status(
        self,
        *,
        feedback_type: str,
        feedback_payload: dict[str, Any],
    ) -> str | None:
        outcome = _normalize_token(feedback_payload.get("outcome_status")).lower()
        if outcome in {"success", "succeeded", "passed", "ok"}:
            return "success"
        if outcome in {"failed", "failure", "error", "abandoned", "timeout"}:
            return "failed"
        lowered_feedback_type = _normalize_token(feedback_type).lower()
        if "success" in lowered_feedback_type or lowered_feedback_type.endswith("_pass"):
            return "success"
        if (
            "fail" in lowered_feedback_type
            or "error" in lowered_feedback_type
            or lowered_feedback_type.endswith("_timeout")
        ):
            return "failed"
        if _to_bool(feedback_payload.get("rollback_flag")):
            return "failed"
        return None


def _normalize_token(value: Any) -> str:
    return str(value or "").strip()


def _normalize_scope_id(*, scope_type: str, value: Any) -> str:
    scope_id = str(value or "").strip()
    if scope_type == "global":
        return scope_id or "global"
    if not scope_id:
        raise ValueError("scope_id is required for personal/team scope")
    return scope_id


def _normalize_acl(value: Any) -> list[str]:
    if isinstance(value, list):
        out = [str(x).strip() for x in value if str(x).strip()]
    else:
        out = []
    dedup: list[str] = []
    seen: set[str] = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        dedup.append(item)
    return dedup


def _normalize_score(value: Any, *, default: float) -> float:
    if value is None:
        return default
    score = float(value)
    if score < 0.0 or score > 1.0:
        raise ValueError("score must be in [0, 1]")
    return score


def _normalize_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _to_non_negative_int(value: Any) -> int:
    if value is None:
        return 0
    count = int(value)
    return max(0, count)
