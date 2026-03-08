from __future__ import annotations

import json
import time
import uuid
from typing import Any

from flockmem.infra.sqlite.db import SQLiteEngine


class CollectiveRepository:
    def __init__(self, engine: SQLiteEngine) -> None:
        self.engine = engine

    def get_knowledge_item(self, knowledge_id: str) -> dict[str, Any] | None:
        row = self.engine.query_one(
            """
            SELECT
              knowledge_id,
              scope_type,
              scope_id,
              state,
              canonical_revision_id,
              read_acl,
              write_acl,
              trust_score,
              created_at,
              updated_at
            FROM knowledge_item
            WHERE knowledge_id=?
            """,
            (str(knowledge_id or "").strip(),),
        )
        if not row:
            return None
        row["read_acl"] = _parse_acl(row.get("read_acl"))
        row["write_acl"] = _parse_acl(row.get("write_acl"))
        return row

    def get_revision(self, revision_id: str) -> dict[str, Any] | None:
        row = self.engine.query_one(
            """
            SELECT
              revision_id,
              knowledge_id,
              parent_revision_id,
              confidence,
              change_type,
              changed_by,
              coordination_mode,
              coordination_id,
              runtime_id,
              agent_id,
              subagent_id,
              team_id,
              session_id,
              created_at
            FROM knowledge_revision
            WHERE revision_id=?
            """,
            (str(revision_id or "").strip(),),
        )
        if not row:
            return None
        return row

    def find_revision_by_coordination(
        self,
        *,
        knowledge_id: str,
        coordination_id: str,
        change_type: str,
        content_json: str,
    ) -> dict[str, Any] | None:
        row = self.engine.query_one(
            """
            SELECT
              revision_id,
              knowledge_id,
              confidence,
              change_type,
              changed_by,
              coordination_mode,
              coordination_id,
              runtime_id,
              agent_id,
              subagent_id,
              team_id,
              session_id,
              created_at
            FROM knowledge_revision
            WHERE knowledge_id = ?
              AND coordination_id = ?
              AND change_type = ?
              AND content_json = ?
            LIMIT 1
            """,
            (
                str(knowledge_id or "").strip(),
                str(coordination_id or "").strip(),
                str(change_type or "").strip(),
                str(content_json or "").strip(),
            ),
        )
        if not row:
            return None
        return row

    def upsert_knowledge_item(
        self,
        *,
        knowledge_id: str,
        scope_type: str,
        scope_id: str,
        state: str,
        canonical_revision_id: str | None,
        read_acl: list[str],
        write_acl: list[str],
        trust_score: float,
    ) -> None:
        now = int(time.time())
        self.engine.execute(
            """
            INSERT INTO knowledge_item(
              knowledge_id,scope_type,scope_id,state,canonical_revision_id,
              read_acl,write_acl,trust_score,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(knowledge_id) DO UPDATE SET
              scope_type=excluded.scope_type,
              scope_id=excluded.scope_id,
              state=excluded.state,
              canonical_revision_id=excluded.canonical_revision_id,
              read_acl=excluded.read_acl,
              write_acl=excluded.write_acl,
              trust_score=excluded.trust_score,
              updated_at=excluded.updated_at
            """,
            (
                knowledge_id,
                scope_type,
                scope_id,
                state,
                canonical_revision_id,
                json.dumps(read_acl, ensure_ascii=False),
                json.dumps(write_acl, ensure_ascii=False),
                float(trust_score),
                now,
                now,
            ),
        )

    def insert_revision(
        self,
        *,
        knowledge_id: str,
        revision_id: str | None,
        parent_revision_id: str | None,
        content: dict[str, Any],
        confidence: float,
        change_type: str,
        changed_by: str,
        evidence: list[dict[str, Any]],
        coordination_mode: str | None,
        coordination_id: str | None,
        runtime_id: str | None = None,
        agent_id: str | None = None,
        subagent_id: str | None = None,
        team_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        rid = str(revision_id or uuid.uuid4().hex).strip() or uuid.uuid4().hex
        self.engine.execute(
            """
            INSERT INTO knowledge_revision(
              revision_id,knowledge_id,parent_revision_id,content_json,confidence,
              change_type,changed_by,evidence_json,coordination_mode,coordination_id,
              runtime_id,agent_id,subagent_id,team_id,session_id,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                rid,
                knowledge_id,
                parent_revision_id,
                json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                float(confidence),
                change_type,
                changed_by,
                json.dumps(evidence, ensure_ascii=False, separators=(",", ":")),
                coordination_mode,
                coordination_id,
                runtime_id,
                agent_id,
                subagent_id,
                team_id,
                session_id,
                int(time.time()),
            ),
        )
        return rid

    def apply_ingest_change(
        self,
        *,
        knowledge_id: str,
        scope_type: str,
        scope_id: str,
        read_acl: list[str],
        write_acl: list[str],
        trust_score: float,
        state: str,
        canonical_revision_id: str | None,
        revision_id: str | None,
        parent_revision_id: str | None,
        content: dict[str, Any],
        confidence: float,
        change_type: str,
        changed_by: str,
        evidence: list[dict[str, Any]],
        coordination_mode: str | None,
        coordination_id: str | None,
        runtime_id: str | None = None,
        agent_id: str | None = None,
        subagent_id: str | None = None,
        team_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        rid = str(revision_id or uuid.uuid4().hex).strip() or uuid.uuid4().hex
        content_json = json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        read_acl_json = json.dumps(read_acl, ensure_ascii=False)
        write_acl_json = json.dumps(write_acl, ensure_ascii=False)
        evidence_json = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
        now = int(time.time())
        canonical_candidate = None if canonical_revision_id is None else rid
        with self.engine.connect() as conn:
            inserted_item = conn.execute(
                """
                INSERT OR IGNORE INTO knowledge_item(
                  knowledge_id,scope_type,scope_id,state,canonical_revision_id,
                  read_acl,write_acl,trust_score,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    knowledge_id,
                    scope_type,
                    scope_id,
                    state,
                    canonical_candidate,
                    read_acl_json,
                    write_acl_json,
                    float(trust_score),
                    now,
                    now,
                ),
            )
            insert_revision = conn.execute(
                """
                INSERT OR IGNORE INTO knowledge_revision(
                  revision_id,knowledge_id,parent_revision_id,content_json,confidence,
                  change_type,changed_by,evidence_json,coordination_mode,coordination_id,
                  runtime_id,agent_id,subagent_id,team_id,session_id,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    rid,
                    knowledge_id,
                    parent_revision_id,
                    content_json,
                    float(confidence),
                    change_type,
                    changed_by,
                    evidence_json,
                    coordination_mode,
                    coordination_id,
                    runtime_id,
                    agent_id,
                    subagent_id,
                    team_id,
                    session_id,
                    now,
                ),
            )
            if int(insert_revision.rowcount) == 0:
                if coordination_id:
                    existing = conn.execute(
                        """
                        SELECT revision_id
                        FROM knowledge_revision
                        WHERE knowledge_id = ?
                          AND coordination_id = ?
                          AND change_type = ?
                          AND content_json = ?
                        LIMIT 1
                        """,
                        (knowledge_id, coordination_id, change_type, content_json),
                    ).fetchone()
                else:
                    existing = conn.execute(
                        """
                        SELECT revision_id
                        FROM knowledge_revision
                        WHERE revision_id = ?
                        LIMIT 1
                        """,
                        (rid,),
                    ).fetchone()
                if not existing:
                    raise RuntimeError("failed to resolve idempotent revision replay")
                rid = str(existing["revision_id"])
                conn.execute(
                    """
                    UPDATE knowledge_revision
                    SET coordination_mode = COALESCE(coordination_mode, ?),
                        coordination_id = COALESCE(coordination_id, ?),
                        runtime_id = COALESCE(runtime_id, ?),
                        agent_id = COALESCE(agent_id, ?),
                        subagent_id = COALESCE(subagent_id, ?),
                        team_id = COALESCE(team_id, ?),
                        session_id = COALESCE(session_id, ?)
                    WHERE revision_id = ?
                    """,
                    (
                        coordination_mode,
                        coordination_id,
                        runtime_id,
                        agent_id,
                        subagent_id,
                        team_id,
                        session_id,
                        rid,
                    ),
                )
            effective_canonical_revision = None if canonical_revision_id is None else rid
            needs_item_update = (
                int(inserted_item.rowcount) == 0
                or effective_canonical_revision != canonical_candidate
            )
            if needs_item_update:
                conn.execute(
                    """
                    UPDATE knowledge_item
                    SET scope_type = ?,
                        scope_id = ?,
                        state = ?,
                        canonical_revision_id = ?,
                        read_acl = ?,
                        write_acl = ?,
                        trust_score = ?,
                        updated_at = ?
                    WHERE knowledge_id = ?
                    """,
                    (
                        scope_type,
                        scope_id,
                        state,
                        effective_canonical_revision,
                        read_acl_json,
                        write_acl_json,
                        float(trust_score),
                        now,
                        knowledge_id,
                    ),
                )
            conn.commit()
        return rid

    def insert_feedback(
        self,
        *,
        knowledge_id: str,
        revision_id: str | None,
        feedback_type: str,
        feedback_payload: dict[str, Any],
        actor: str,
        coordination_mode: str | None,
        coordination_id: str | None,
        runtime_id: str | None = None,
        agent_id: str | None = None,
        subagent_id: str | None = None,
        team_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        feedback_id, _ = self.apply_feedback_and_revise(
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
        )
        return feedback_id

    def apply_feedback_and_revise(
        self,
        *,
        knowledge_id: str,
        revision_id: str | None,
        feedback_type: str,
        feedback_payload: dict[str, Any],
        actor: str,
        coordination_mode: str | None,
        coordination_id: str | None,
        runtime_id: str | None = None,
        agent_id: str | None = None,
        subagent_id: str | None = None,
        team_id: str | None = None,
        session_id: str | None = None,
        revise_state: str | None = None,
        revise_canonical_revision_id: str | None = None,
        revise_trust_score: float | None = None,
        revise_read_acl: list[str] | None = None,
        revise_write_acl: list[str] | None = None,
    ) -> tuple[str, bool]:
        feedback_id = uuid.uuid4().hex
        feedback_payload_json = json.dumps(
            feedback_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        is_replay = False
        with self.engine.connect() as conn:
            inserted = conn.execute(
            """
            INSERT OR IGNORE INTO knowledge_feedback(
              feedback_id,knowledge_id,revision_id,feedback_type,feedback_payload,
              actor,coordination_mode,coordination_id,runtime_id,agent_id,subagent_id,
              team_id,session_id,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                feedback_id,
                knowledge_id,
                revision_id,
                feedback_type,
                feedback_payload_json,
                actor,
                coordination_mode,
                coordination_id,
                runtime_id,
                agent_id,
                subagent_id,
                team_id,
                session_id,
                int(time.time()),
            ),
            )
            if int(inserted.rowcount) == 0:
                is_replay = True
                existing = conn.execute(
                    """
                    SELECT feedback_id
                    FROM knowledge_feedback
                    WHERE knowledge_id = ?
                      AND coordination_id = ?
                      AND feedback_type = ?
                      AND actor = ?
                      AND feedback_payload = ?
                    LIMIT 1
                    """,
                    (
                        knowledge_id,
                        coordination_id,
                        feedback_type,
                        actor,
                        feedback_payload_json,
                    ),
                ).fetchone()
                if not existing:
                    raise RuntimeError("failed to resolve idempotent feedback replay")
                feedback_id = str(existing["feedback_id"])
                conn.execute(
                    """
                    UPDATE knowledge_feedback
                    SET coordination_mode = COALESCE(coordination_mode, ?),
                        coordination_id = COALESCE(coordination_id, ?),
                        runtime_id = COALESCE(runtime_id, ?),
                        agent_id = COALESCE(agent_id, ?),
                        subagent_id = COALESCE(subagent_id, ?),
                        team_id = COALESCE(team_id, ?),
                        session_id = COALESCE(session_id, ?)
                    WHERE feedback_id = ?
                    """,
                    (
                        coordination_mode,
                        coordination_id,
                        runtime_id,
                        agent_id,
                        subagent_id,
                        team_id,
                        session_id,
                        feedback_id,
                    ),
                )
            if (
                revise_state is not None
                and revise_trust_score is not None
                and revise_read_acl is not None
                and revise_write_acl is not None
            ):
                conn.execute(
                    """
                    UPDATE knowledge_item
                    SET state = ?,
                        canonical_revision_id = ?,
                        read_acl = ?,
                        write_acl = ?,
                        trust_score = ?,
                        updated_at = ?
                    WHERE knowledge_id = ?
                    """,
                    (
                        revise_state,
                        revise_canonical_revision_id,
                        json.dumps(revise_read_acl, ensure_ascii=False),
                        json.dumps(revise_write_acl, ensure_ascii=False),
                        float(revise_trust_score),
                        int(time.time()),
                        knowledge_id,
                    ),
                )
            conn.commit()
        return feedback_id, is_replay

    def find_feedback_by_coordination(
        self,
        *,
        knowledge_id: str,
        coordination_id: str,
        feedback_type: str,
        actor: str,
        feedback_payload_json: str,
    ) -> dict[str, Any] | None:
        row = self.engine.query_one(
            """
            SELECT
              feedback_id,
              knowledge_id,
              revision_id,
              feedback_type,
              actor,
              coordination_mode,
              coordination_id,
              runtime_id,
              agent_id,
              subagent_id,
              team_id,
              session_id,
              created_at
            FROM knowledge_feedback
            WHERE knowledge_id = ?
              AND coordination_id = ?
              AND feedback_type = ?
              AND actor = ?
              AND feedback_payload = ?
            LIMIT 1
            """,
            (
                str(knowledge_id or "").strip(),
                str(coordination_id or "").strip(),
                str(feedback_type or "").strip(),
                str(actor or "").strip(),
                str(feedback_payload_json or "").strip(),
            ),
        )
        if not row:
            return None
        return row

    def get_context_by_scopes(
        self,
        *,
        scopes: list[tuple[str, str]],
        actor_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not scopes or limit <= 0:
            return []
        rows: list[dict[str, Any]] = []
        seen_knowledge_ids: set[str] = set()
        for scope_type, scope_id in scopes:
            if len(rows) >= limit:
                break
            batch = self.engine.query_all(
                """
                SELECT
                  ki.knowledge_id,
                  ki.scope_type,
                  ki.scope_id,
                  ki.state,
                  ki.canonical_revision_id,
                  ki.read_acl,
                  ki.write_acl,
                  ki.trust_score,
                  ki.updated_at,
                  kr.revision_id,
                  kr.content_json,
                  kr.confidence,
                  kr.change_type,
                  kr.changed_by,
                  kr.created_at AS revision_created_at
                FROM knowledge_item ki
                LEFT JOIN knowledge_revision kr
                  ON kr.revision_id = ki.canonical_revision_id
                WHERE ki.scope_type = ?
                  AND ki.scope_id = ?
                  AND ki.state <> 'deprecated'
                ORDER BY ki.updated_at DESC
                LIMIT ?
                """,
                (scope_type, scope_id, max(1, int(limit))),
            )
            for item in batch:
                knowledge_id = str(item.get("knowledge_id") or "").strip()
                if not knowledge_id or knowledge_id in seen_knowledge_ids:
                    continue
                read_acl = _parse_acl(item.get("read_acl"))
                if read_acl and actor_id and actor_id not in read_acl:
                    continue
                if read_acl and not actor_id:
                    continue
                seen_knowledge_ids.add(knowledge_id)
                item["read_acl"] = read_acl
                item["write_acl"] = _parse_acl(item.get("write_acl"))
                item["content"] = _parse_content(item.get("content_json"))
                rows.append(item)
                if len(rows) >= limit:
                    break
        return rows[:limit]


def _parse_acl(raw_acl: Any) -> list[str]:
    if isinstance(raw_acl, list):
        return [str(x).strip() for x in raw_acl if str(x).strip()]
    text = str(raw_acl or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if not isinstance(data, list):
            return []
        return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        return []


def _parse_content(raw_content: Any) -> dict[str, Any]:
    if isinstance(raw_content, dict):
        return raw_content
    text = str(raw_content or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}
