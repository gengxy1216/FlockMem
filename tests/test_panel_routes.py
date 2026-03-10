from __future__ import annotations

import json
import os
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from flockmem.bootstrap.app_factory import create_app
from flockmem.config.settings import LiteSettings
from flockmem.testing.writable_tempdir import WritableTempDir


class PanelRouteTests(unittest.TestCase):
    def _build_client(self, *, admin_token: str | None = None) -> tuple[TestClient, object]:
        tmp = WritableTempDir(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        env = {
            "LITE_DATA_DIR": str(Path(tmp.name) / "panel-data"),
            "LITE_CONFIG_DIR": str(Path(tmp.name) / "panel-config"),
            "LITE_CHAT_PROVIDER": "openai",
            "LITE_CHAT_BASE_URL": "https://chat.example/v1",
            "LITE_CHAT_API_KEY": "chat-key",
            "LITE_CHAT_MODEL": "chat-model",
            "LITE_EMBEDDING_PROVIDER": "local",
            "LITE_EMBEDDING_MODEL": "local-hash-384",
            "LITE_EXTRACTOR_PROVIDER": "rule",
        }
        if admin_token is not None:
            env["LITE_ADMIN_TOKEN"] = admin_token
            env["LITE_ADMIN_ALLOW_LOCALHOST"] = "false"
        with patch.dict(os.environ, env, clear=True):
            settings = LiteSettings.from_env()
        app = create_app(settings)
        return TestClient(app), app

    def _admin_headers(self, token: str, *, use_api_key: bool = False) -> dict[str, str]:
        if use_api_key:
            return {"X-API-Key": token}
        return {"Authorization": f"Bearer {token}"}

    def _seed_memory(self, app: object, *, sender: str = "user-alpha") -> str:
        now = int(time.time())
        memory_id = f"mem-{uuid.uuid4().hex}"
        engine = app.state.sqlite_engine
        engine.execute(
            """
            INSERT INTO episodic_memory(
              id,event_id,source_message_id,user_id,group_id,timestamp,role,sender,
              sender_name,group_name,episode,summary,subject,importance_score,scene_id,
              storage_tier,memory_category,is_deleted,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                memory_id,
                f"evt-{uuid.uuid4().hex}",
                f"msg-{uuid.uuid4().hex}",
                "user-alpha",
                "group-alpha",
                now,
                "user",
                sender,
                "User Alpha",
                "Group Alpha",
                "Panel route seed memory episode",
                "Panel route seed memory summary",
                "panel-subject",
                0.8,
                None,
                "text_only",
                "general",
                0,
                now,
                now,
            ),
        )
        return memory_id

    def _seed_collective_rows(self, app: object) -> dict[str, str]:
        repo = app.state.collective_repository
        now = int(time.time())

        repo.upsert_knowledge_item(
            knowledge_id="knowledge-main",
            scope_type="personal",
            scope_id="user-alpha",
            state="active",
            canonical_revision_id=None,
            read_acl=["assistant-alpha"],
            write_acl=["assistant-alpha"],
            trust_score=0.9,
        )
        revision_id = repo.insert_revision(
            knowledge_id="knowledge-main",
            revision_id="rev-main",
            parent_revision_id=None,
            content={"fact": "assistant primary revision"},
            confidence=0.88,
            change_type="create",
            changed_by="assistant",
            evidence=[{"kind": "seed"}],
            coordination_mode="inruntime_a2a",
            coordination_id="coord-main",
            runtime_id="codex",
            agent_id="assistant-alpha",
            subagent_id=None,
            team_id="team-alpha",
            session_id="session-alpha",
        )
        main_feedback_id = repo.insert_feedback(
            knowledge_id="knowledge-main",
            revision_id=revision_id,
            feedback_type="execution_signal",
            feedback_payload={
                "outcome_status": "success",
                "memory_id": "memory-main",
                "memory_summary": "Primary remembered feedback",
            },
            actor="user-alpha",
            coordination_mode="inruntime_a2a",
            coordination_id="coord-feedback-main",
            runtime_id="codex",
            agent_id="assistant-alpha",
            subagent_id=None,
            team_id="team-alpha",
            session_id="session-alpha",
        )

        repo.upsert_knowledge_item(
            knowledge_id="knowledge-pending",
            scope_type="personal",
            scope_id="user-alpha",
            state="draft",
            canonical_revision_id=None,
            read_acl=["assistant-alpha"],
            write_acl=["assistant-alpha"],
            trust_score=0.4,
        )
        repo.insert_revision(
            knowledge_id="knowledge-pending",
            revision_id="rev-pending",
            parent_revision_id=None,
            content={"fact": "orphan subassistant revision"},
            confidence=0.61,
            change_type="create",
            changed_by="assistant",
            evidence=[{"kind": "seed"}],
            coordination_mode="inruntime_a2a",
            coordination_id="coord-pending",
            runtime_id="codex",
            agent_id=None,
            subagent_id="subagent-orphan",
            team_id="team-alpha",
            session_id="session-alpha",
        )

        app.state.sqlite_engine.execute(
            "UPDATE knowledge_revision SET created_at=? WHERE revision_id IN (?, ?)",
            (now, "rev-main", "rev-pending"),
        )
        app.state.sqlite_engine.execute(
            "UPDATE knowledge_feedback SET created_at=? WHERE coordination_id=?",
            (now, "coord-feedback-main"),
        )
        return {"main_feedback_id": main_feedback_id}

    def _seed_feedback_without_memory_link(self, app: object) -> None:
        repo = app.state.collective_repository
        repo.upsert_knowledge_item(
            knowledge_id="knowledge-unlinked",
            scope_type="personal",
            scope_id="user-beta",
            state="draft",
            canonical_revision_id=None,
            read_acl=["assistant-beta"],
            write_acl=["assistant-beta"],
            trust_score=0.3,
        )
        revision_id = repo.insert_revision(
            knowledge_id="knowledge-unlinked",
            revision_id="rev-unlinked",
            parent_revision_id=None,
            content={"fact": "feedback without memory link"},
            confidence=0.55,
            change_type="create",
            changed_by="assistant",
            evidence=[{"kind": "seed"}],
            coordination_mode="inruntime_a2a",
            coordination_id="coord-unlinked",
            runtime_id="codex",
            agent_id="assistant-beta",
            subagent_id=None,
            team_id="team-beta",
            session_id="session-beta",
        )
        repo.insert_feedback(
            knowledge_id="knowledge-unlinked",
            revision_id=revision_id,
            feedback_type="execution_signal",
            feedback_payload={"outcome_status": "pending"},
            actor="user-beta",
            coordination_mode="inruntime_a2a",
            coordination_id="coord-feedback-unlinked",
            runtime_id="codex",
            agent_id="assistant-beta",
            subagent_id=None,
            team_id="team-beta",
            session_id="session-beta",
        )

    def _seed_feedback_with_processed_at(self, app: object) -> str:
        repo = app.state.collective_repository
        now = int(time.time())
        repo.upsert_knowledge_item(
            knowledge_id="knowledge-processed",
            scope_type="personal",
            scope_id="user-gamma",
            state="draft",
            canonical_revision_id=None,
            read_acl=["assistant-gamma"],
            write_acl=["assistant-gamma"],
            trust_score=0.5,
        )
        revision_id = repo.insert_revision(
            knowledge_id="knowledge-processed",
            revision_id="rev-processed",
            parent_revision_id=None,
            content={"fact": "feedback with explicit processed time"},
            confidence=0.8,
            change_type="create",
            changed_by="assistant",
            evidence=[{"kind": "seed"}],
            coordination_mode="inruntime_a2a",
            coordination_id="coord-processed",
            runtime_id="codex",
            agent_id="assistant-gamma",
            subagent_id=None,
            team_id="team-gamma",
            session_id="session-gamma",
        )
        return repo.insert_feedback(
            knowledge_id="knowledge-processed",
            revision_id=revision_id,
            feedback_type="user_correction",
            feedback_payload={
                "outcome_status": "accepted",
                "memory_id": "memory-processed",
                "processed_at": now + 3,
            },
            actor="user-gamma",
            coordination_mode="inruntime_a2a",
            coordination_id="coord-feedback-processed",
            runtime_id="codex",
            agent_id="assistant-gamma",
            subagent_id=None,
            team_id="team-gamma",
            session_id="session-gamma",
        )

    def _seed_panel_local_files(self, app: object) -> None:
        settings = app.state.settings
        settings.config_path.parent.mkdir(parents=True, exist_ok=True)
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        (settings.config_path.parent / "AGENTS.md").write_text("# local agent guide\n", encoding="utf-8")
        (settings.data_dir / "SOUL.md").write_text("# soul guide\n", encoding="utf-8")

    def _seed_panel_registry(self, app: object) -> None:
        payload = app.state.config_repo.get_raw_config(app.state.settings)
        payload["panel"] = {
            "assistant_registry": [
                {
                    "source_code": "codex",
                    "assistant_name": "assistant-alpha",
                    "workspace_roots": [
                        str(app.state.settings.config_path.parent),
                        str(app.state.settings.data_dir),
                    ],
                    "note": "primary assistant",
                }
            ]
        }
        app.state.config_repo.replace_raw_config(
            bootstrap_settings=app.state.settings,
            payload=payload,
        )

    def test_panel_overview_returns_structured_cards(self) -> None:
        client, _ = self._build_client()
        resp = client.get("/api/v1/panel/overview")
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertEqual("ok", body.get("status"))
        result = body.get("result", {})
        self.assertEqual("zh-CN", result.get("locale"))
        cards = result.get("cards", [])
        self.assertEqual(5, len(cards))
        self.assertEqual("assistants_total", cards[0]["card_code"])
        self.assertIn("label", cards[0])
        self.assertIn("value", cards[0])
        client.close()

    def test_panel_assistants_returns_registered_primary_and_pending_subassistant(self) -> None:
        client, app = self._build_client()
        self._seed_collective_rows(app)
        self._seed_panel_local_files(app)
        self._seed_panel_registry(app)
        resp = client.get("/api/v1/panel/assistants", params={"locale": "en-US"})
        self.assertEqual(200, resp.status_code)
        result = resp.json()["result"]
        self.assertEqual("en-US", result["locale"])
        items = result["items"]
        self.assertGreaterEqual(len(items), 2)

        primary = next(item for item in items if item["assistant_role"] == "primary")
        self.assertEqual("codex:assistant-alpha", primary["assistant_id"])
        self.assertEqual("Healthy", primary["status_text"])
        self.assertEqual("registered", primary["recognition_state"])
        primary_files = {item["display_name"]: item for item in primary["local_files"]}
        self.assertEqual("recognized", primary_files["AGENTS.md"]["status_code"])
        self.assertEqual("recognized", primary_files["SOUL.md"]["status_code"])

        pending = next(
            item
            for item in items
            if item["assistant_role"] == "subassistant"
            and item["recognition_state"] == "pending_identification"
        )
        self.assertEqual("Incomplete", pending["status_text"])
        self.assertEqual("codex:pending:subagent-orphan", pending["assistant_id"])
        self.assertIsNone(pending["parent_assistant_id"])
        file_statuses = {item["display_name"]: item for item in pending["local_files"]}
        self.assertEqual("not_in_scope", file_statuses["AGENTS.md"]["status_code"])
        self.assertIsNone(file_statuses["AGENTS.md"]["file_path"])
        self.assertEqual("not_in_scope", file_statuses["SOUL.md"]["status_code"])
        client.close()

    def test_panel_assistant_registry_routes_support_create_delete_and_detail(self) -> None:
        client, app = self._build_client()
        self._seed_panel_local_files(app)
        create_resp = client.post(
            "/api/v1/panel/assistants/registry",
            json={
                "source_code": "codex",
                "assistant_name": "assistant-reg",
                "workspace_roots": [
                    str(app.state.settings.config_path.parent),
                    str(app.state.settings.data_dir),
                ],
                "note": "registered from test",
            },
        )
        self.assertEqual(200, create_resp.status_code)
        created_items = create_resp.json()["result"]["items"]
        created = next(item for item in created_items if item["assistant_id"] == "codex:assistant-reg")
        self.assertEqual("registered", created["recognition_state"])

        detail_resp = client.get("/api/v1/panel/assistants/codex:assistant-reg")
        self.assertEqual(200, detail_resp.status_code)
        self.assertEqual("codex:assistant-reg", detail_resp.json()["result"]["assistant_id"])

        delete_resp = client.delete("/api/v1/panel/assistants/registry/codex:assistant-reg")
        self.assertEqual(200, delete_resp.status_code)
        self.assertTrue(delete_resp.json()["result"]["deleted"])
        client.close()

    def test_panel_assistant_registry_write_routes_require_admin_authorization_when_token_configured(
        self,
    ) -> None:
        admin_token = "panel-admin-token"
        client, app = self._build_client(admin_token=admin_token)
        self._seed_panel_local_files(app)
        payload = {
            "source_code": "codex",
            "assistant_name": "assistant-reg-auth",
            "workspace_roots": [
                str(app.state.settings.config_path.parent),
                str(app.state.settings.data_dir),
            ],
            "note": "auth protected registry write",
        }

        create_unauthorized = client.post("/api/v1/panel/assistants/registry", json=payload)
        self.assertEqual(401, create_unauthorized.status_code)

        create_authorized = client.post(
            "/api/v1/panel/assistants/registry",
            json=payload,
            headers=self._admin_headers(admin_token, use_api_key=True),
        )
        self.assertEqual(200, create_authorized.status_code)
        created_items = create_authorized.json()["result"]["items"]
        self.assertTrue(
            any(item["assistant_id"] == "codex:assistant-reg-auth" for item in created_items)
        )

        delete_unauthorized = client.delete(
            "/api/v1/panel/assistants/registry/codex:assistant-reg-auth"
        )
        self.assertEqual(401, delete_unauthorized.status_code)

        delete_authorized = client.delete(
            "/api/v1/panel/assistants/registry/codex:assistant-reg-auth",
            headers=self._admin_headers(admin_token),
        )
        self.assertEqual(200, delete_authorized.status_code)
        self.assertTrue(delete_authorized.json()["result"]["deleted"])
        client.close()

    def test_panel_feedback_returns_result_codes_without_faked_processed_time(self) -> None:
        client, app = self._build_client()
        seeded = self._seed_collective_rows(app)
        resp = client.get("/api/v1/panel/feedback")
        self.assertEqual(200, resp.status_code)
        result = resp.json()["result"]
        self.assertEqual("zh-CN", result["locale"])
        items = result["items"]
        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEqual("remembered", item["result_code"])
        self.assertEqual("已记住", item["result_text"])
        self.assertEqual("linked", item["memory_link_state_code"])
        self.assertIsNone(item["processed_at"])
        self.assertEqual(1, len(item["timeline_items"]))

        detail_resp = client.get(f"/api/v1/panel/feedback/{seeded['main_feedback_id']}")
        self.assertEqual(200, detail_resp.status_code)
        self.assertEqual("remembered", detail_resp.json()["result"]["result_code"])
        client.close()

    def test_panel_feedback_marks_unlinked_feedback_without_memory_fields(self) -> None:
        client, app = self._build_client()
        self._seed_feedback_without_memory_link(app)
        resp = client.get("/api/v1/panel/feedback", params={"locale": "en-US"})
        self.assertEqual(200, resp.status_code)
        item = resp.json()["result"]["items"][0]
        self.assertEqual("not_linked", item["memory_link_state_code"])
        self.assertEqual("Not linked to memory yet", item["memory_link_state_text"])
        self.assertEqual("Not linked to memory yet", item["memory_summary"])
        client.close()

    def test_panel_feedback_detail_uses_explicit_processed_at(self) -> None:
        client, app = self._build_client()
        feedback_id = self._seed_feedback_with_processed_at(app)
        resp = client.get(f"/api/v1/panel/feedback/{feedback_id}", params={"locale": "en-US"})
        self.assertEqual(200, resp.status_code)
        result = resp.json()["result"]
        self.assertEqual("remembered", result["result_code"])
        self.assertIsNotNone(result["processed_at"])
        self.assertGreaterEqual(len(result["timeline_items"]), 2)
        client.close()

    def test_panel_memories_returns_user_facing_list_and_detail(self) -> None:
        client, app = self._build_client()
        memory_id = self._seed_memory(app, sender="assistant-alpha")
        resp = client.get("/api/v1/panel/memories", params={"locale": "en-US", "query": "seed"})
        self.assertEqual(200, resp.status_code)
        result = resp.json()["result"]
        self.assertEqual("en-US", result["locale"])
        self.assertEqual(1, len(result["items"]))
        item = result["items"][0]
        self.assertEqual("User Alpha", item["sender_name"])
        self.assertEqual("Conversation", item["source_text"])

        detail = client.get(f"/api/v1/panel/memories/{memory_id}", params={"locale": "en-US"})
        self.assertEqual(200, detail.status_code)
        self.assertEqual(memory_id, detail.json()["result"]["memory_id"])
        self.assertIn("content", detail.json()["result"])
        client.close()

    def test_panel_chat_returns_trace_from_pipeline_and_accepts_query_alias(self) -> None:
        client, app = self._build_client()
        self._seed_memory(app)
        mocked_chat = {
            "answer": "You told me you like tea.",
            "citations": [
                {
                    "id": "mem-used",
                    "summary": "User likes tea",
                    "sender": "user-alpha",
                    "user_id": "user-alpha",
                    "group_id": "group-alpha",
                    "timestamp": int(time.time()),
                    "source": "conversation",
                    "citation_snippet": "likes tea",
                }
            ],
            "retrieved_memories": [
                {
                    "id": "mem-used",
                    "summary": "User likes tea",
                    "sender": "user-alpha",
                    "user_id": "user-alpha",
                    "group_id": "group-alpha",
                    "timestamp": int(time.time()),
                    "source": "conversation",
                },
                {
                    "id": "mem-hit-only",
                    "summary": "User visited Shanghai",
                    "sender": "user-alpha",
                    "user_id": "user-alpha",
                    "group_id": "group-alpha",
                    "timestamp": int(time.time()),
                    "source": "conversation",
                },
            ],
            "provider": "openai",
            "model": "chat-model",
            "conversation_id": "session-alpha",
            "memory_filter": {"live_segment_count": 1},
            "boundary_detected": True,
        }
        with patch("flockmem.api.routes.panel.execute_chat_query", return_value=mocked_chat):
            resp = client.post(
                "/api/v1/panel/chat",
                json={"query": "What do you remember about me?", "locale": "en-US"},
            )
        self.assertEqual(200, resp.status_code)
        result = resp.json()["result"]
        self.assertEqual("en-US", result["locale"])
        self.assertEqual("What do you remember about me?", result["question"])
        self.assertTrue(result["used_memory"])
        self.assertEqual(1, len(result["used_source_cards"]))
        self.assertEqual(1, len(result["hit_only_source_cards"]))
        self.assertTrue(result["explain_groups"])
        self.assertEqual("You told me you like tea.", result["answer"])
        client.close()

    def test_panel_chat_rejects_blank_question_and_locale_falls_back(self) -> None:
        client, _ = self._build_client()
        bad = client.post("/api/v1/panel/chat", json={"question": "   "})
        self.assertEqual(422, bad.status_code)

        resp = client.get("/api/v1/panel/overview", params={"locale": "fr-FR"})
        self.assertEqual(200, resp.status_code)
        self.assertEqual("zh-CN", resp.json()["result"]["locale"])
        client.close()

    def test_panel_overview_counts_seeded_memory_feedback_and_issues(self) -> None:
        client, app = self._build_client()
        self._seed_memory(app)
        self._seed_collective_rows(app)
        self._seed_panel_local_files(app)
        self._seed_panel_registry(app)
        resp = client.get("/api/v1/panel/overview", headers={"Accept-Language": "en-US,en;q=0.8"})
        self.assertEqual(200, resp.status_code)
        result = resp.json()["result"]
        self.assertEqual("en-US", result["locale"])
        self.assertEqual(1, result["assistant_count"])
        self.assertEqual(1, result["memory_count_24h"])
        self.assertEqual(1, result["feedback_count_24h"])
        self.assertGreaterEqual(result["issue_count"], 1)
        self.assertTrue(result["recent_issues"])
        self.assertTrue(result["recent_activity"])
        client.close()

    def test_panel_settings_returns_tabbed_read_model(self) -> None:
        client, _ = self._build_client()
        resp = client.get("/api/v1/panel/settings", params={"locale": "en-US"})
        self.assertEqual(200, resp.status_code)
        result = resp.json()["result"]
        self.assertEqual("en-US", result["locale"])
        self.assertEqual(4, len(result["cards"]))
        self.assertEqual(
            ["common", "assistants", "memory", "sharing", "advanced"],
            [tab["tab_code"] for tab in result["tabs"]],
        )
        first_item = result["tabs"][0]["items"][0]
        self.assertIn("setting_key", first_item)
        self.assertIn("control_type", first_item)
        assistant_item_codes = {item["setting_key"] for item in result["tabs"][1]["items"]}
        self.assertIn("authorized_scan_roots", assistant_item_codes)
        self.assertTrue(result["raw_mode"]["enabled"])
        self.assertTrue(str(result["raw_mode"]["path"]).endswith("config.json"))
        client.close()

    def test_panel_settings_raw_returns_redacted_payload_and_file_meta(self) -> None:
        client, app = self._build_client()
        app.state.settings.config_path.parent.mkdir(parents=True, exist_ok=True)
        app.state.settings.config_path.write_text(
            '{"version":1,"models":{"chat_api_key":"secret-key"}}',
            encoding="utf-8",
        )
        resp = client.get("/api/v1/panel/settings/raw")
        self.assertEqual(200, resp.status_code)
        result = resp.json()["result"]
        self.assertEqual("zh-CN", result["locale"])
        self.assertTrue(str(result["path"]).endswith("config.json"))
        self.assertIsNotNone(result["updated_at"])
        self.assertIsNotNone(result["size_bytes"])
        self.assertIn("config", result)
        self.assertIn("raw_json", result)
        self.assertIn("fields", result)
        client.close()

    def test_panel_settings_put_and_raw_put_update_shared_source(self) -> None:
        client, app = self._build_client()
        put_resp = client.put(
            "/api/v1/panel/settings",
            json={
                "locale": "en-US",
                "values": {
                    "chat_provider": "siliconflow",
                    "chat_model": "chat-next",
                    "retrieval_profile": "hybrid",
                    "graph_enabled": False,
                    "authorized_scan_roots": ["C:/tmp/flockmem-panel"],
                },
            },
        )
        self.assertEqual(200, put_resp.status_code)
        put_result = put_resp.json()["result"]
        self.assertTrue(put_result["saved"])
        self.assertIn("chat_provider", put_result["updated_keys"])
        self.assertIn("authorized_scan_roots", put_result["updated_keys"])
        self.assertEqual("hybrid", put_result["runtime_policy"]["policy"]["profile"])
        assistants_tab = next(tab for tab in put_result["tabs"] if tab["tab_code"] == "assistants")
        scan_item = next(
            item for item in assistants_tab["items"] if item["setting_key"] == "authorized_scan_roots"
        )
        self.assertIn("flockmem-panel", scan_item["value_text"])

        raw_resp = client.put(
            "/api/v1/panel/settings/raw",
            json={
                "raw_json": json.dumps(
                    {
                        "version": 1,
                        "settings": {
                            **app.state.config_repo.get_raw_config(app.state.settings)["settings"],
                            "graph_enabled": True,
                        },
                        "models": app.state.config_repo.get_raw_config(app.state.settings)["models"],
                    }
                )
            },
        )
        self.assertEqual(200, raw_resp.status_code)
        raw_result = raw_resp.json()["result"]
        self.assertTrue(raw_result["saved"])
        self.assertIn("config", raw_result)
        client.close()

    def test_panel_settings_write_routes_require_admin_authorization_when_token_configured(
        self,
    ) -> None:
        admin_token = "panel-settings-admin-token"
        client, app = self._build_client(admin_token=admin_token)
        put_payload = {
            "locale": "en-US",
            "values": {
                "chat_provider": "siliconflow",
                "chat_model": "chat-next",
                "retrieval_profile": "hybrid",
                "graph_enabled": False,
                "authorized_scan_roots": ["C:/tmp/flockmem-panel-auth"],
            },
        }

        put_unauthorized = client.put("/api/v1/panel/settings", json=put_payload)
        self.assertEqual(401, put_unauthorized.status_code)

        put_authorized = client.put(
            "/api/v1/panel/settings",
            json=put_payload,
            headers=self._admin_headers(admin_token),
        )
        self.assertEqual(200, put_authorized.status_code)
        self.assertTrue(put_authorized.json()["result"]["saved"])

        raw_config = app.state.config_repo.get_raw_config(app.state.settings)
        raw_payload = {
            "raw_json": json.dumps(
                {
                    **raw_config,
                    "settings": {
                        **(raw_config.get("settings") or {}),
                        "graph_enabled": True,
                    },
                }
            )
        }

        raw_unauthorized = client.put("/api/v1/panel/settings/raw", json=raw_payload)
        self.assertEqual(401, raw_unauthorized.status_code)

        raw_authorized = client.put(
            "/api/v1/panel/settings/raw",
            json=raw_payload,
            headers=self._admin_headers(admin_token),
        )
        self.assertEqual(200, raw_authorized.status_code)
        self.assertTrue(raw_authorized.json()["result"]["saved"])
        client.close()


if __name__ == "__main__":
    unittest.main()
