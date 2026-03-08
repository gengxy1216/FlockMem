from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from flockmem.bootstrap.app_factory import create_app
from flockmem.config.settings import LiteSettings
from flockmem.testing.writable_tempdir import WritableTempDir


class CollectiveCoreRouteTests(unittest.TestCase):
    def _build_client(self) -> tuple[TestClient, LiteSettings]:
        tmp = WritableTempDir(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        env = {
            "LITE_DATA_DIR": str(Path(tmp.name) / "mem-data"),
            "LITE_CONFIG_DIR": str(Path(tmp.name) / "mem-config"),
            "LITE_CHAT_PROVIDER": "openai",
            "LITE_CHAT_BASE_URL": "https://chat.example/v1",
            "LITE_CHAT_API_KEY": "chat-key",
            "LITE_CHAT_MODEL": "chat-model-a",
            "LITE_EMBEDDING_PROVIDER": "local",
            "LITE_EMBEDDING_MODEL": "local-hash-384",
            "LITE_EXTRACTOR_PROVIDER": "rule",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = LiteSettings.from_env()
        return TestClient(create_app(settings)), settings

    def test_collective_ingest_context_feedback_normal_path(self) -> None:
        client, _ = self._build_client()
        ingest_resp = client.post(
            "/api/v1/collective/ingest",
            json={
                "knowledge_id": "k-alpha",
                "scope_type": "personal",
                "scope_id": "u-1",
                "content": {"fact": "service timeout fixed by retry budget"},
                "change_type": "create",
                "changed_by": "agent",
                "actor_id": "agent-1",
                "read_acl": ["agent-1"],
                "write_acl": ["agent-1"],
                "confidence": 0.85,
                "trust_score": 0.8,
                "evidence": [{"type": "test", "status": "pass"}],
            },
        )
        self.assertEqual(200, ingest_resp.status_code)
        ingest_result = ingest_resp.json().get("result", {})
        self.assertEqual("k-alpha", ingest_result.get("knowledge_id"))
        self.assertTrue(str(ingest_result.get("revision_id", "")).strip())

        context_resp = client.post(
            "/api/v1/collective/context",
            json={
                "personal_scope_id": "u-1",
                "actor_id": "agent-1",
                "top_k": 5,
            },
        )
        self.assertEqual(200, context_resp.status_code)
        context_items = context_resp.json().get("result", {}).get("items", [])
        self.assertGreaterEqual(len(context_items), 1)
        self.assertEqual("k-alpha", context_items[0].get("knowledge_id"))

        feedback_resp = client.post(
            "/api/v1/collective/feedback",
            json={
                "knowledge_id": "k-alpha",
                "revision_id": ingest_result.get("revision_id"),
                "feedback_type": "execution_result",
                "feedback_payload": {"outcome_status": "success"},
                "actor": "agent-1",
            },
        )
        self.assertEqual(200, feedback_resp.status_code)
        feedback_result = feedback_resp.json().get("result", {})
        self.assertTrue(str(feedback_result.get("feedback_id", "")).strip())

    def test_collective_ingest_rejects_write_acl_violation(self) -> None:
        client, _ = self._build_client()
        resp = client.post(
            "/api/v1/collective/ingest",
            json={
                "scope_type": "team",
                "scope_id": "team-a",
                "content": {"fact": "only owner can edit"},
                "change_type": "create",
                "changed_by": "agent",
                "actor_id": "intruder",
                "write_acl": ["owner-1"],
            },
        )
        self.assertEqual(403, resp.status_code)

    def test_collective_context_returns_empty_for_missing_records(self) -> None:
        client, _ = self._build_client()
        resp = client.post(
            "/api/v1/collective/context",
            json={
                "personal_scope_id": "u-missing",
                "include_global": False,
                "top_k": 5,
            },
        )
        self.assertEqual(200, resp.status_code)
        result = resp.json().get("result", {})
        self.assertEqual(0, int(result.get("count", -1)))
        self.assertEqual([], result.get("items", []))

    def test_collective_feedback_returns_not_found_for_missing_knowledge(self) -> None:
        client, _ = self._build_client()
        resp = client.post(
            "/api/v1/collective/feedback",
            json={
                "knowledge_id": "k-not-exist",
                "feedback_type": "execution_result",
                "feedback_payload": {"outcome_status": "failed"},
                "actor": "agent-1",
            },
        )
        self.assertEqual(404, resp.status_code)

    def test_collective_feedback_rejects_write_acl_violation(self) -> None:
        client, _ = self._build_client()
        ingest_resp = client.post(
            "/api/v1/collective/ingest",
            json={
                "knowledge_id": "k-feedback-acl",
                "scope_type": "personal",
                "scope_id": "u-feedback-acl",
                "content": {"fact": "feedback acl protected"},
                "change_type": "create",
                "changed_by": "agent",
                "actor_id": "owner-1",
                "read_acl": ["owner-1"],
                "write_acl": ["owner-1"],
            },
        )
        self.assertEqual(200, ingest_resp.status_code, msg=ingest_resp.text)
        revision_id = ingest_resp.json().get("result", {}).get("revision_id")
        self.assertTrue(str(revision_id or "").strip())

        forbidden_feedback = client.post(
            "/api/v1/collective/feedback",
            json={
                "knowledge_id": "k-feedback-acl",
                "revision_id": revision_id,
                "feedback_type": "execution_signal",
                "feedback_payload": {"outcome_status": "failed", "rollback_flag": True},
                "actor": "intruder-1",
                "coordination_mode": "inruntime_a2a",
                "coordination_id": "coord-feedback-acl-1",
            },
        )
        self.assertEqual(403, forbidden_feedback.status_code, msg=forbidden_feedback.text)

        context_resp = client.post(
            "/api/v1/collective/context",
            json={
                "query": "feedback acl protected",
                "actor_id": "owner-1",
                "personal_scope_id": "u-feedback-acl",
                "include_global": False,
                "top_k": 5,
            },
        )
        self.assertEqual(200, context_resp.status_code, msg=context_resp.text)
        context_items = context_resp.json().get("result", {}).get("items", [])
        self.assertGreaterEqual(len(context_items), 1)
        self.assertEqual("k-feedback-acl", context_items[0].get("knowledge_id"))
        self.assertEqual("canonical", context_items[0].get("state"))


if __name__ == "__main__":
    unittest.main()
