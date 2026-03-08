from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import TypedDict
from unittest.mock import patch

from fastapi.testclient import TestClient

from flockmem.bootstrap.app_factory import create_app
from flockmem.config.settings import LiteSettings
from flockmem.testing.writable_tempdir import WritableTempDir


REQUIRED_ROUTES = {
    "/api/v1/collective/ingest",
    "/api/v1/collective/context",
    "/api/v1/collective/feedback",
}


class CollectiveRuntime(TypedDict):
    client: TestClient
    routes: set[str]
    tmp: WritableTempDir


def build_collective_client(*, prefix: str) -> CollectiveRuntime:
    tmp = WritableTempDir(ignore_cleanup_errors=True)
    env = {
        "LITE_DATA_DIR": str(Path(tmp.name) / f"{prefix}-data"),
        "LITE_CONFIG_DIR": str(Path(tmp.name) / f"{prefix}-config"),
        "LITE_ADMIN_TOKEN": f"{prefix}-admin-token",
        "LITE_ADMIN_ALLOW_LOCALHOST": "false",
        "LITE_RETRIEVAL_PROFILE": "keyword",
        "LITE_CHAT_PROVIDER": "openai",
        "LITE_CHAT_BASE_URL": "https://chat.example/v1",
        "LITE_CHAT_API_KEY": "qa-chat-key",
        "LITE_CHAT_MODEL": "qa-chat-model",
        "LITE_EMBEDDING_PROVIDER": "openai",
        "LITE_EMBEDDING_BASE_URL": "https://embed.example/v1",
        "LITE_EMBEDDING_API_KEY": "qa-embed-key",
        "LITE_EMBEDDING_MODEL": "qa-embed-model",
        "LITE_EXTRACTOR_PROVIDER": "rule",
        "LITE_RERANK_PROVIDER": "chat_model",
    }
    with patch.dict(os.environ, env, clear=True):
        settings = LiteSettings.from_env()
    app = create_app(settings)
    routes = {getattr(route, "path", "") for route in app.routes}
    return {"client": TestClient(app), "routes": routes, "tmp": tmp}


def skip_if_collective_routes_missing(testcase: unittest.TestCase, routes: set[str], *, suite: str) -> None:
    missing = sorted(REQUIRED_ROUTES - routes)
    if missing:
        testcase.skipTest(
            f"{suite} blocked until collective routes exist: " + ", ".join(missing)
        )


def assert_standard_envelope(testcase: unittest.TestCase, body: dict[str, object]) -> None:
    testcase.assertIn("status", body)
    testcase.assertIn("message", body)
    testcase.assertIn("result", body)
    testcase.assertEqual("ok", body.get("status"))


def _ingest_payload(*, knowledge_id: str, scope_type: str, scope_id: str | None, actor_id: str) -> dict[str, object]:
    return {
        "knowledge_id": knowledge_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "content": {"text": f"collective-{knowledge_id}"},
        "change_type": "update",
        "changed_by": "agent",
        "actor_id": actor_id,
        "read_acl": [],
        "write_acl": [actor_id],
        "coordination_mode": "inruntime_a2a",
        "coordination_id": f"coord-{knowledge_id}",
        "runtime_id": "codex",
        "agent_id": "qa-gate",
        "subagent_id": "qa-sub",
    }


def ingest_success(
    testcase: unittest.TestCase,
    *,
    client: TestClient,
    knowledge_id: str,
    scope_type: str = "personal",
    scope_id: str | None = "u-qa",
    actor_id: str = "qa-writer",
    read_acl: list[str] | None = None,
    write_acl: list[str] | None = None,
) -> dict[str, object]:
    payload = _ingest_payload(
        knowledge_id=knowledge_id,
        scope_type=scope_type,
        scope_id=scope_id,
        actor_id=actor_id,
    )
    if read_acl is not None:
        payload["read_acl"] = read_acl
    if write_acl is not None:
        payload["write_acl"] = write_acl
    response = client.post("/api/v1/collective/ingest", json=payload)
    testcase.assertEqual(200, response.status_code, msg=response.text)
    body = response.json()
    assert_standard_envelope(testcase, body)
    result = body["result"]
    testcase.assertIsInstance(result, dict)
    return result


class CollectiveContractsTests(unittest.TestCase):
    def test_collective_routes_registered(self) -> None:
        runtime = build_collective_client(prefix="qa-contract-routes")
        self.addCleanup(runtime["tmp"].cleanup)
        self.assertEqual(set(), REQUIRED_ROUTES - runtime["routes"])
        runtime["client"].close()

    def test_ingest_context_feedback_follow_standard_contract(self) -> None:
        runtime = build_collective_client(prefix="qa-contract-happy")
        self.addCleanup(runtime["tmp"].cleanup)
        skip_if_collective_routes_missing(self, runtime["routes"], suite="collective-contracts")
        client = runtime["client"]

        ingest_result = ingest_success(
            self,
            client=client,
            knowledge_id="k-contract-1",
            scope_type="personal",
            scope_id="u-contract",
            actor_id="qa-reader",
            read_acl=["qa-reader"],
            write_acl=["qa-reader"],
        )
        self.assertEqual("personal", ingest_result["scope_type"])
        self.assertEqual("u-contract", ingest_result["scope_id"])
        self.assertTrue(str(ingest_result["revision_id"]).strip())

        context_response = client.post(
            "/api/v1/collective/context",
            json={
                "query": "contract lookup",
                "actor_id": "qa-reader",
                "personal_scope_id": "u-contract",
                "include_global": False,
                "top_k": 5,
            },
        )
        self.assertEqual(200, context_response.status_code, msg=context_response.text)
        context_body = context_response.json()
        assert_standard_envelope(self, context_body)
        context_result = context_body["result"]
        self.assertIsInstance(context_result, dict)
        self.assertEqual(["personal"], context_result["scope_order"])
        self.assertGreaterEqual(int(context_result["count"]), 1)
        first_item = context_result["items"][0]
        self.assertEqual("k-contract-1", first_item["knowledge_id"])
        self.assertEqual("u-contract", first_item["scope_id"])

        feedback_response = client.post(
            "/api/v1/collective/feedback",
            json={
                "knowledge_id": "k-contract-1",
                "revision_id": ingest_result["revision_id"],
                "feedback_type": "execution_signal",
                "feedback_payload": {
                    "outcome_status": "success",
                    "tool_error_count": 0,
                    "retry_count": 0,
                    "rollback_flag": False,
                    "reuse_hit": True,
                },
                "actor": "qa-reader",
                "coordination_mode": "inruntime_a2a",
                "coordination_id": "coord-contract-feedback",
            },
        )
        self.assertEqual(200, feedback_response.status_code, msg=feedback_response.text)
        feedback_body = feedback_response.json()
        assert_standard_envelope(self, feedback_body)
        feedback_result = feedback_body["result"]
        self.assertEqual("k-contract-1", feedback_result["knowledge_id"])
        self.assertTrue(str(feedback_result["feedback_id"]).strip())
        client.close()

    def test_contract_boundary_and_error_codes(self) -> None:
        runtime = build_collective_client(prefix="qa-contract-boundary")
        self.addCleanup(runtime["tmp"].cleanup)
        skip_if_collective_routes_missing(self, runtime["routes"], suite="collective-contracts")
        client = runtime["client"]

        boundary_cases: tuple[tuple[str, dict[str, object], int], ...] = (
            (
                "ingest_invalid_scope_literal",
                {
                    "scope_type": "unknown",
                    "scope_id": "u-bad",
                    "content": {"text": "x"},
                    "changed_by": "agent",
                },
                422,
            ),
            (
                "ingest_empty_content",
                {
                    "knowledge_id": "k-empty-content",
                    "scope_type": "personal",
                    "scope_id": "u-bad",
                    "content": {},
                    "changed_by": "agent",
                    "actor_id": "qa-writer",
                },
                400,
            ),
        )
        for case_name, payload, expected_status in boundary_cases:
            with self.subTest(case_name=case_name):
                response = client.post("/api/v1/collective/ingest", json=payload)
                self.assertEqual(expected_status, response.status_code, msg=response.text)
                self.assertLess(response.status_code, 500)
                self.assertIn("detail", response.json())

        context_bad = client.post(
            "/api/v1/collective/context",
            json={"query": "need-scope", "include_global": False},
        )
        self.assertEqual(400, context_bad.status_code, msg=context_bad.text)
        self.assertIn("detail", context_bad.json())

        feedback_missing_actor = client.post(
            "/api/v1/collective/feedback",
            json={
                "knowledge_id": "k-any",
                "feedback_type": "execution_signal",
                "feedback_payload": {"ok": True},
            },
        )
        self.assertEqual(422, feedback_missing_actor.status_code, msg=feedback_missing_actor.text)

        feedback_unknown_knowledge = client.post(
            "/api/v1/collective/feedback",
            json={
                "knowledge_id": "k-not-exist",
                "feedback_type": "execution_signal",
                "feedback_payload": {"ok": False},
                "actor": "qa",
            },
        )
        self.assertEqual(404, feedback_unknown_knowledge.status_code, msg=feedback_unknown_knowledge.text)
        self.assertIn("detail", feedback_unknown_knowledge.json())

        protected = ingest_success(
            self,
            client=client,
            knowledge_id="k-contract-feedback-acl",
            scope_type="personal",
            scope_id="u-contract-acl",
            actor_id="owner-contract",
            read_acl=["owner-contract"],
            write_acl=["owner-contract"],
        )
        feedback_forbidden = client.post(
            "/api/v1/collective/feedback",
            json={
                "knowledge_id": "k-contract-feedback-acl",
                "revision_id": protected["revision_id"],
                "feedback_type": "execution_signal",
                "feedback_payload": {"outcome_status": "failed", "rollback_flag": True},
                "actor": "intruder-contract",
                "coordination_mode": "inruntime_a2a",
                "coordination_id": "coord-contract-feedback-acl-1",
            },
        )
        self.assertEqual(403, feedback_forbidden.status_code, msg=feedback_forbidden.text)
        self.assertIn("detail", feedback_forbidden.json())
        client.close()

    def test_idempotent_replay_with_same_coordination_id(self) -> None:
        runtime = build_collective_client(prefix="qa-contract-idempotent")
        self.addCleanup(runtime["tmp"].cleanup)
        skip_if_collective_routes_missing(self, runtime["routes"], suite="collective-contracts")
        client = runtime["client"]

        ingest_payload = {
            "knowledge_id": "k-idempotent-1",
            "scope_type": "personal",
            "scope_id": "u-idempotent",
            "content": {"text": "idempotent ingest"},
            "change_type": "update",
            "changed_by": "agent",
            "actor_id": "qa-idempotent",
            "write_acl": ["qa-idempotent"],
            "coordination_mode": "inruntime_a2a",
            "coordination_id": "coord-idempotent-1",
            "runtime_id": "codex",
            "agent_id": "qa-idempotent",
        }
        first_ingest = client.post("/api/v1/collective/ingest", json=ingest_payload)
        self.assertEqual(200, first_ingest.status_code, msg=first_ingest.text)
        first_result = first_ingest.json().get("result", {})

        replay_ingest = client.post("/api/v1/collective/ingest", json=ingest_payload)
        self.assertEqual(200, replay_ingest.status_code, msg=replay_ingest.text)
        replay_result = replay_ingest.json().get("result", {})
        self.assertEqual(first_result.get("revision_id"), replay_result.get("revision_id"))
        self.assertTrue(bool(replay_result.get("idempotent_replay")))

        feedback_payload = {
            "knowledge_id": "k-idempotent-1",
            "revision_id": first_result.get("revision_id"),
            "feedback_type": "execution_signal",
            "feedback_payload": {"outcome_status": "success"},
            "actor": "qa-idempotent",
            "coordination_mode": "inruntime_a2a",
            "coordination_id": "coord-idempotent-feedback-1",
        }
        first_feedback = client.post("/api/v1/collective/feedback", json=feedback_payload)
        self.assertEqual(200, first_feedback.status_code, msg=first_feedback.text)
        first_feedback_id = first_feedback.json().get("result", {}).get("feedback_id")

        replay_feedback = client.post("/api/v1/collective/feedback", json=feedback_payload)
        self.assertEqual(200, replay_feedback.status_code, msg=replay_feedback.text)
        replay_feedback_result = replay_feedback.json().get("result", {})
        self.assertEqual(first_feedback_id, replay_feedback_result.get("feedback_id"))
        self.assertTrue(bool(replay_feedback_result.get("idempotent_replay")))
        client.close()


if __name__ == "__main__":
    unittest.main()
