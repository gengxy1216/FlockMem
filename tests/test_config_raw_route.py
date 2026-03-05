from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from evermemos_lite.bootstrap.app_factory import create_app
from evermemos_lite.config.settings import LiteSettings
from evermemos_lite.testing.writable_tempdir import WritableTempDir


class ConfigRawRouteTests(unittest.TestCase):
    def _build_client(self) -> tuple[TestClient, LiteSettings]:
        tmp = WritableTempDir(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        data_dir = Path(tmp.name) / "mem-data"
        env = {
            "LITE_DATA_DIR": str(data_dir),
            "LITE_CONFIG_DIR": str(Path(tmp.name) / "mem-config"),
            "LITE_CHAT_PROVIDER": "openai",
            "LITE_CHAT_BASE_URL": "https://chat.example/v1",
            "LITE_CHAT_API_KEY": "chat-key",
            "LITE_CHAT_MODEL": "model-base",
            "LITE_EMBEDDING_PROVIDER": "openai",
            "LITE_EMBEDDING_BASE_URL": "https://embed.example/v1",
            "LITE_EMBEDDING_API_KEY": "embed-key",
            "LITE_EMBEDDING_MODEL": "embed-model-a",
            "LITE_EXTRACTOR_PROVIDER": "rule",
            "LITE_RERANK_PROVIDER": "chat_model",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = LiteSettings.from_env()
        app = create_app(settings)
        return TestClient(app), settings

    def test_get_raw_config_returns_config_doc_and_path(self) -> None:
        client, settings = self._build_client()
        resp = client.get("/api/v1/config/raw")
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        self.assertEqual("ok", body.get("status"))
        result = body.get("result", {})
        self.assertTrue(str(result.get("path", "")).endswith("config.json"))
        self.assertEqual(
            "model-base",
            result.get("config", {}).get("models", {}).get("chat", {}).get("model"),
        )
        self.assertEqual(
            "chat_model",
            result.get("config", {}).get("models", {}).get("rerank", {}).get("provider"),
        )
        self.assertEqual(
            "https://chat.example/v1",
            result.get("config", {}).get("models", {}).get("rerank", {}).get("base_url"),
        )
        self.assertIsInstance(
            result.get("config", {}).get("models", {}).get("embedding"), dict
        )
        self.assertIsInstance(
            result.get("config", {}).get("models", {}).get("rerank"), dict
        )
        self.assertNotIn("chat_model", result.get("config", {}).get("models", {}))
        self.assertNotIn("rerank_provider", result.get("config", {}).get("models", {}))

    def test_put_raw_config_updates_runtime_model_and_reports_restart_required(self) -> None:
        client, settings = self._build_client()
        current = client.get("/api/v1/config/raw").json()["result"]["config"]
        next_config = dict(current)
        next_models = dict(next_config.get("models", {}))
        next_models["chat"] = {
            "provider": "openai",
            "base_url": "https://chat.example/v1",
            "api_key": "chat-key",
            "model": "model-from-raw",
        }
        next_models["rerank"] = {
            "provider": "custom-rerank",
            "base_url": "https://rerank.example/v1",
            "api_key": "rerank-key",
            "model": "rerank-model-a",
        }
        next_config["models"] = next_models
        next_settings = dict(next_config.get("settings", {}))
        next_settings["search_trace_enabled"] = True
        next_config["settings"] = next_settings

        resp = client.put("/api/v1/config/raw", json={"config": next_config})
        self.assertEqual(200, resp.status_code)
        body = resp.json()
        result = body.get("result", {})
        self.assertTrue(bool(result.get("saved")))
        self.assertTrue(bool(result.get("restart_required")))

        model_resp = client.get("/api/v1/model-config").json()
        self.assertEqual("model-from-raw", model_resp["result"]["chat_model"])
        self.assertEqual("custom-rerank", model_resp["result"]["rerank_provider"])
        self.assertEqual("https://rerank.example/v1", model_resp["result"]["rerank_base_url"])
        self.assertEqual("rerank-model-a", model_resp["result"]["rerank_model"])

        raw_after = client.get("/api/v1/config/raw").json()["result"]["config"]
        self.assertNotIn("chat_model", raw_after.get("models", {}))
        self.assertNotIn("rerank_provider", raw_after.get("models", {}))


if __name__ == "__main__":
    unittest.main()
