from __future__ import annotations

import unittest
from pathlib import Path

from flockmem.infra.sqlite.collective_repository import CollectiveRepository
from flockmem.infra.sqlite.db import SQLiteEngine
from flockmem.infra.sqlite.init_schema import init_schema
from flockmem.service.collective.core_loop_service import CoreLoopService
from flockmem.testing.writable_tempdir import WritableTempDir


class CollectiveCoreLoopTests(unittest.TestCase):
    def _build_service(self) -> tuple[CoreLoopService, CollectiveRepository]:
        tmp = WritableTempDir(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db_path = Path(tmp.name) / "collective-core-loop.db"
        engine = SQLiteEngine(db_path)
        init_schema(engine)
        repo = CollectiveRepository(engine)
        return CoreLoopService(repo), repo

    def test_closed_loop_normal_path(self) -> None:
        service, repo = self._build_service()
        ingest = service.ingest(
            {
                "knowledge_id": "k-core-1",
                "scope_type": "personal",
                "scope_id": "u-core",
                "content": {"fact": "retry budget fixed timeout regressions"},
                "change_type": "create",
                "changed_by": "agent",
                "actor_id": "agent-core",
                "read_acl": ["agent-core"],
                "write_acl": ["agent-core"],
                "confidence": 0.9,
                "trust_score": 0.8,
            }
        )
        self.assertEqual("k-core-1", ingest["knowledge_id"])
        self.assertEqual("canonical", ingest["state"])
        self.assertTrue(str(ingest["revision_id"]).strip())

        context = service.context(
            {
                "actor_id": "agent-core",
                "personal_scope_id": "u-core",
                "include_global": False,
                "top_k": 5,
            }
        )
        self.assertEqual(1, context["count"])
        self.assertEqual("k-core-1", context["items"][0]["knowledge_id"])

        feedback = service.feedback(
            {
                "knowledge_id": "k-core-1",
                "revision_id": ingest["revision_id"],
                "feedback_type": "execution_signal",
                "feedback_payload": {
                    "outcome_status": "success",
                    "reuse_hit": True,
                    "retry_count": 0,
                    "tool_error_count": 0,
                },
                "actor": "agent-core",
            }
        )
        self.assertEqual("k-core-1", feedback["knowledge_id"])
        self.assertTrue(str(feedback["feedback_id"]).strip())
        self.assertTrue(feedback["revise_applied"])
        self.assertEqual("keep_canonical", feedback["revise_action"])
        self.assertEqual("canonical", feedback["state"])
        self.assertEqual(ingest["revision_id"], feedback["canonical_revision_id"])

        stored = repo.get_knowledge_item("k-core-1")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual("canonical", stored["state"])
        self.assertEqual(ingest["revision_id"], stored["canonical_revision_id"])
        self.assertGreater(float(stored["trust_score"]), 0.8)

    def test_boundary_rejects_write_acl_violation(self) -> None:
        service, _ = self._build_service()
        service.ingest(
            {
                "knowledge_id": "k-core-acl",
                "scope_type": "team",
                "scope_id": "team-core",
                "content": {"fact": "owner seeded this knowledge"},
                "change_type": "create",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
            }
        )
        with self.assertRaises(PermissionError):
            service.ingest(
                {
                    "knowledge_id": "k-core-acl",
                    "scope_type": "team",
                    "scope_id": "team-core",
                    "content": {"fact": "intruder update attempt"},
                    "change_type": "update",
                    "changed_by": "agent",
                    "actor_id": "intruder-core",
                }
            )

    def test_failed_feedback_rolls_back_to_parent_revision(self) -> None:
        service, repo = self._build_service()
        created = service.ingest(
            {
                "knowledge_id": "k-core-rollback",
                "scope_type": "personal",
                "scope_id": "u-rollback",
                "content": {"fact": "v1 canonical"},
                "change_type": "create",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
                "trust_score": 0.7,
            }
        )
        updated = service.ingest(
            {
                "knowledge_id": "k-core-rollback",
                "scope_type": "personal",
                "scope_id": "u-rollback",
                "content": {"fact": "v2 candidate promoted"},
                "change_type": "update",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
                "trust_score": 0.75,
            }
        )
        self.assertNotEqual(created["revision_id"], updated["revision_id"])

        failed_feedback = service.feedback(
            {
                "knowledge_id": "k-core-rollback",
                "revision_id": updated["revision_id"],
                "feedback_type": "execution_signal",
                "feedback_payload": {
                    "outcome_status": "failed",
                    "rollback_flag": True,
                    "tool_error_count": 2,
                },
                "actor": "owner-core",
            }
        )
        self.assertTrue(failed_feedback["revise_applied"])
        self.assertEqual("rollback_to_parent", failed_feedback["revise_action"])
        self.assertEqual(created["revision_id"], failed_feedback["canonical_revision_id"])
        self.assertEqual("canonical", failed_feedback["state"])

        stored = repo.get_knowledge_item("k-core-rollback")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual("canonical", stored["state"])
        self.assertEqual(created["revision_id"], stored["canonical_revision_id"])

    def test_recovery_after_failed_signal_without_parent(self) -> None:
        service, repo = self._build_service()
        created = service.ingest(
            {
                "knowledge_id": "k-core-recover",
                "scope_type": "personal",
                "scope_id": "u-recover",
                "content": {"fact": "recoverable seed"},
                "change_type": "create",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
            }
        )
        self.assertTrue(str(created["revision_id"]).strip())

        failed = service.feedback(
            {
                "knowledge_id": "k-core-recover",
                "revision_id": created["revision_id"],
                "feedback_type": "execution_signal",
                "feedback_payload": {"outcome_status": "failed", "rollback_flag": False},
                "actor": "owner-core",
            }
        )
        self.assertTrue(failed["revise_applied"])
        self.assertEqual("demote_deprecated", failed["revise_action"])
        self.assertEqual("deprecated", failed["state"])
        self.assertIsNone(failed["canonical_revision_id"])

        stored = repo.get_knowledge_item("k-core-recover")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual("deprecated", stored["state"])
        self.assertIsNone(stored["canonical_revision_id"])

        visible = service.context(
            {
                "actor_id": "owner-core",
                "personal_scope_id": "u-recover",
                "include_global": False,
            }
        )
        self.assertEqual(0, visible["count"])
        self.assertEqual([], visible["items"])

        recovered = service.feedback(
            {
                "knowledge_id": "k-core-recover",
                "revision_id": created["revision_id"],
                "feedback_type": "execution_signal",
                "feedback_payload": {
                    "outcome_status": "success",
                    "reuse_hit": True,
                    "tool_error_count": 0,
                    "retry_count": 0,
                },
                "actor": "owner-core",
            }
        )
        self.assertTrue(recovered["revise_applied"])
        self.assertEqual("promote_canonical", recovered["revise_action"])
        self.assertEqual("canonical", recovered["state"])
        self.assertEqual(created["revision_id"], recovered["canonical_revision_id"])

        visible_again = service.context(
            {
                "actor_id": "owner-core",
                "personal_scope_id": "u-recover",
                "include_global": False,
            }
        )
        self.assertEqual(1, visible_again["count"])
        self.assertEqual("k-core-recover", visible_again["items"][0]["knowledge_id"])

    def test_feedback_replay_compensates_missing_revise(self) -> None:
        service, repo = self._build_service()
        created = service.ingest(
            {
                "knowledge_id": "k-core-replay-fix",
                "scope_type": "personal",
                "scope_id": "u-replay-fix",
                "content": {"fact": "v1"},
                "change_type": "create",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
            }
        )
        updated = service.ingest(
            {
                "knowledge_id": "k-core-replay-fix",
                "scope_type": "personal",
                "scope_id": "u-replay-fix",
                "content": {"fact": "v2"},
                "change_type": "update",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
            }
        )

        # Simulate historical partial failure: feedback committed without revise update.
        repo.insert_feedback(
            knowledge_id="k-core-replay-fix",
            revision_id=updated["revision_id"],
            feedback_type="execution_signal",
            feedback_payload={"outcome_status": "failed", "rollback_flag": True},
            actor="owner-core",
            coordination_mode="inruntime_a2a",
            coordination_id="coord-replay-fix-1",
        )
        before = repo.get_knowledge_item("k-core-replay-fix")
        self.assertIsNotNone(before)
        assert before is not None
        self.assertEqual(updated["revision_id"], before["canonical_revision_id"])

        replay = service.feedback(
            {
                "knowledge_id": "k-core-replay-fix",
                "revision_id": updated["revision_id"],
                "feedback_type": "execution_signal",
                "feedback_payload": {"outcome_status": "failed", "rollback_flag": True},
                "actor": "owner-core",
                "coordination_mode": "inruntime_a2a",
                "coordination_id": "coord-replay-fix-1",
            }
        )
        self.assertTrue(bool(replay.get("idempotent_replay")))
        self.assertEqual("rollback_to_parent", replay.get("revise_action"))
        self.assertEqual(created["revision_id"], replay.get("canonical_revision_id"))

        after = repo.get_knowledge_item("k-core-replay-fix")
        self.assertIsNotNone(after)
        assert after is not None
        self.assertEqual(created["revision_id"], after["canonical_revision_id"])

    def test_stale_failed_replay_does_not_override_newer_canonical(self) -> None:
        service, repo = self._build_service()
        created = service.ingest(
            {
                "knowledge_id": "k-core-stale-replay",
                "scope_type": "personal",
                "scope_id": "u-stale-replay",
                "content": {"fact": "v1"},
                "change_type": "create",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
            }
        )
        failed_revision = service.ingest(
            {
                "knowledge_id": "k-core-stale-replay",
                "scope_type": "personal",
                "scope_id": "u-stale-replay",
                "content": {"fact": "v2-bad"},
                "change_type": "update",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
            }
        )
        first_failed = service.feedback(
            {
                "knowledge_id": "k-core-stale-replay",
                "revision_id": failed_revision["revision_id"],
                "feedback_type": "execution_signal",
                "feedback_payload": {"outcome_status": "failed", "rollback_flag": True},
                "actor": "owner-core",
                "coordination_mode": "inruntime_a2a",
                "coordination_id": "coord-stale-replay-1",
            }
        )
        self.assertFalse(bool(first_failed.get("idempotent_replay")))
        self.assertEqual("rollback_to_parent", first_failed.get("revise_action"))
        self.assertEqual(created["revision_id"], first_failed.get("canonical_revision_id"))

        promoted = service.ingest(
            {
                "knowledge_id": "k-core-stale-replay",
                "scope_type": "personal",
                "scope_id": "u-stale-replay",
                "content": {"fact": "v3-good"},
                "change_type": "update",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
            }
        )

        stale_replay = service.feedback(
            {
                "knowledge_id": "k-core-stale-replay",
                "revision_id": failed_revision["revision_id"],
                "feedback_type": "execution_signal",
                "feedback_payload": {"outcome_status": "failed", "rollback_flag": True},
                "actor": "owner-core",
                "coordination_mode": "inruntime_a2a",
                "coordination_id": "coord-stale-replay-1",
            }
        )
        self.assertTrue(bool(stale_replay.get("idempotent_replay")))
        self.assertFalse(bool(stale_replay.get("revise_applied")))
        self.assertEqual("stale_replay_noop", stale_replay.get("revise_action"))

        stored = repo.get_knowledge_item("k-core-stale-replay")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(promoted["revision_id"], stored.get("canonical_revision_id"))
        self.assertEqual("canonical", stored.get("state"))

    def test_stale_failed_replay_without_revision_id_keeps_newer_canonical(self) -> None:
        service, repo = self._build_service()
        created = service.ingest(
            {
                "knowledge_id": "k-core-stale-replay-no-revision",
                "scope_type": "personal",
                "scope_id": "u-stale-replay-no-revision",
                "content": {"fact": "v1"},
                "change_type": "create",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
            }
        )
        failed_revision = service.ingest(
            {
                "knowledge_id": "k-core-stale-replay-no-revision",
                "scope_type": "personal",
                "scope_id": "u-stale-replay-no-revision",
                "content": {"fact": "v2-bad"},
                "change_type": "update",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
            }
        )
        service.feedback(
            {
                "knowledge_id": "k-core-stale-replay-no-revision",
                "revision_id": failed_revision["revision_id"],
                "feedback_type": "execution_signal",
                "feedback_payload": {"outcome_status": "failed", "rollback_flag": True},
                "actor": "owner-core",
                "coordination_mode": "inruntime_a2a",
                "coordination_id": "coord-stale-replay-no-revision-1",
            }
        )

        promoted = service.ingest(
            {
                "knowledge_id": "k-core-stale-replay-no-revision",
                "scope_type": "personal",
                "scope_id": "u-stale-replay-no-revision",
                "content": {"fact": "v3-good"},
                "change_type": "update",
                "changed_by": "agent",
                "actor_id": "owner-core",
                "write_acl": ["owner-core"],
            }
        )
        stale_replay = service.feedback(
            {
                "knowledge_id": "k-core-stale-replay-no-revision",
                "feedback_type": "execution_signal",
                "feedback_payload": {"outcome_status": "failed", "rollback_flag": True},
                "actor": "owner-core",
                "coordination_mode": "inruntime_a2a",
                "coordination_id": "coord-stale-replay-no-revision-1",
            }
        )
        self.assertTrue(bool(stale_replay.get("idempotent_replay")))
        self.assertFalse(bool(stale_replay.get("revise_applied")))
        self.assertEqual("stale_replay_noop", stale_replay.get("revise_action"))

        stored = repo.get_knowledge_item("k-core-stale-replay-no-revision")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(promoted["revision_id"], stored.get("canonical_revision_id"))
        self.assertEqual("canonical", stored.get("state"))
        self.assertNotEqual(created["revision_id"], stored.get("canonical_revision_id"))


if __name__ == "__main__":
    unittest.main()
