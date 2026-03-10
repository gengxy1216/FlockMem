from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from flockmem.api.redaction import redact_sensitive
from flockmem.infra.sqlite.db import SQLiteEngine

SUPPORTED_LOCALES = ("zh-CN", "en-US")
DEFAULT_LOCALE = "zh-CN"
_FILE_SPECS = (
    ("agents_md", "AGENTS.md"),
    ("agent_md", "AGENT.md"),
    ("soul_md", "SOUL.md"),
    ("claude_md", "CLAUDE.md"),
    ("memory_file", "MEMORY"),
)
_LOCALE_TEXT: dict[str, dict[str, str]] = {
    "zh-CN": {
        "card.assistants_total": "已接入助手",
        "card.subassistants_active": "活跃子助手",
        "card.memories_24h": "24 小时新增记忆",
        "card.feedback_24h": "24 小时新增反馈",
        "card.issues_total": "待处理问题",
        "status.ok": "正常",
        "status.attention": "注意",
        "status.offline": "离线",
        "status.incomplete": "未完成",
        "status_reason.recent_activity": "最近有活动",
        "status_reason.stale_activity": "近期无活动，需要留意",
        "status_reason.no_recent_activity": "较长时间无活动",
        "status_reason.awaiting_mapping": "等待补全归属信息",
        "recognition.registered": "已识别",
        "recognition.observed": "已观察到",
        "recognition.pending_identification": "待识别",
        "file.recognized": "已识别",
        "file.missing": "缺失",
        "file.unreadable": "无法读取",
        "file.not_in_scope": "未纳入当前接入配置",
        "feedback.result.remembered": "已记住",
        "feedback.result.pending": "待处理",
        "feedback.result.rejected": "未采纳",
        "feedback.result.rolled_back": "已回退",
        "feedback.link.linked": "已关联记忆",
        "feedback.link.not_linked": "尚未关联记忆",
        "feedback.link.multiple": "关联多条记忆",
        "feedback.reason.success": "反馈已进入当前采用结果",
        "feedback.reason.pending": "反馈已接收，等待后续处理",
        "feedback.reason.rejected": "反馈已记录，但未被采纳",
        "feedback.reason.rolled_back": "反馈曾生效，但已回退",
        "feedback.summary.execution_signal": "执行反馈",
        "feedback.summary.user_correction": "用户修正",
        "feedback.summary.generic": "反馈记录",
        "chat.answer.placeholder": "已收到你的问题。当前这次回答没有引用到历史记忆；当系统找到相关记忆时，Chat 页面会同步展示参考来源。",
        "chat.explain.no_memory": "本次回答没有用到历史记忆，所以这里只展示基础回答说明。",
        "chat.group.final": "最终回答说明",
        "chat.group.hit_only": "命中但未采用",
        "chat.group.shared": "共享补充",
        "chat.group.personal": "你的历史记录",
        "issue.pending_identification": "存在待识别的子助手，需要补充接入信息",
        "issue.no_files_in_scope": "当前尚未纳入可检测的本地说明文件目录",
        "activity.memory_created": "新增记忆",
        "activity.feedback_created": "新增反馈",
        "activity.assistant_seen": "助手活动",
        "settings.card.answer": "当前回答设置",
        "settings.card.search": "当前检索设置",
        "settings.card.raw": "RAW 模式",
        "settings.tab.answer": "回答",
        "settings.tab.search": "检索",
        "settings.tab.organize": "记忆整理",
        "settings.tab.answer_desc": "决定新对话默认使用哪一路回答服务。",
        "settings.tab.search_desc": "决定系统如何找回并排序历史记忆。",
        "settings.tab.organize_desc": "决定新内容如何整理成后续可复用的记忆。",
        "settings.item.chat_provider": "默认回答服务",
        "settings.item.chat_model": "回答模型",
        "settings.item.embedding_provider": "记忆查找服务",
        "settings.item.embedding_model": "记忆查找模型",
        "settings.item.extractor_provider": "内容整理服务",
        "settings.item.extractor_model": "内容整理模型",
        "settings.item.retrieval_profile": "检索风格",
        "settings.item.recall_mode": "深度回想",
        "settings.item.search_trace_enabled": "保留来源说明",
        "settings.item.graph_enabled": "关系补充",
        "settings.raw.title": "RAW 模式",
        "settings.raw.description": "可查看完整配置原文；敏感字段会自动打码。",
        "settings.raw.path": "配置文件位置",
        "settings.raw.updated_at": "最近更新时间",
        "settings.raw.size": "配置大小",
        "settings.raw.note": "RAW 适合高级排查或批量调整。",
        "settings.bool.on": "开启",
        "settings.bool.off": "关闭",
    },
    "en-US": {
        "card.assistants_total": "Connected assistants",
        "card.subassistants_active": "Active subassistants",
        "card.memories_24h": "Memories in 24h",
        "card.feedback_24h": "Feedback in 24h",
        "card.issues_total": "Issues to review",
        "status.ok": "Healthy",
        "status.attention": "Attention",
        "status.offline": "Offline",
        "status.incomplete": "Incomplete",
        "status_reason.recent_activity": "Recently active",
        "status_reason.stale_activity": "No recent activity; needs review",
        "status_reason.no_recent_activity": "Inactive for a while",
        "status_reason.awaiting_mapping": "Waiting for ownership mapping",
        "recognition.registered": "Registered",
        "recognition.observed": "Observed",
        "recognition.pending_identification": "Pending identification",
        "file.recognized": "Recognized",
        "file.missing": "Missing",
        "file.unreadable": "Unreadable",
        "file.not_in_scope": "Not included in current access setup",
        "feedback.result.remembered": "Remembered",
        "feedback.result.pending": "Pending",
        "feedback.result.rejected": "Rejected",
        "feedback.result.rolled_back": "Rolled back",
        "feedback.link.linked": "Linked to memory",
        "feedback.link.not_linked": "Not linked to memory yet",
        "feedback.link.multiple": "Linked to multiple memories",
        "feedback.reason.success": "The feedback is part of the current adopted result",
        "feedback.reason.pending": "The feedback was received and is waiting for follow-up",
        "feedback.reason.rejected": "The feedback was recorded but not adopted",
        "feedback.reason.rolled_back": "The feedback once took effect but was rolled back",
        "feedback.summary.execution_signal": "Execution feedback",
        "feedback.summary.user_correction": "User correction",
        "feedback.summary.generic": "Feedback record",
        "chat.answer.placeholder": "Your question was received. This reply did not use past memory yet. When relevant memory is found, Chat will show the sources here.",
        "chat.explain.no_memory": "This reply did not use past memory, so only the basic answer notes are shown here.",
        "chat.group.final": "Final answer notes",
        "chat.group.hit_only": "Hit but not used",
        "chat.group.shared": "Shared additions",
        "chat.group.personal": "Your own history",
        "issue.pending_identification": "There are pending subassistants that still need mapping information",
        "issue.no_files_in_scope": "No local instruction directory is currently allowed for scanning",
        "activity.memory_created": "Memory added",
        "activity.feedback_created": "Feedback added",
        "activity.assistant_seen": "Assistant activity",
        "settings.card.answer": "Answer setup",
        "settings.card.search": "Search setup",
        "settings.card.raw": "RAW mode",
        "settings.tab.answer": "Answer",
        "settings.tab.search": "Search",
        "settings.tab.organize": "Memory shaping",
        "settings.tab.answer_desc": "Choose the answer service used by new chats.",
        "settings.tab.search_desc": "Control how past memory is found and ranked.",
        "settings.tab.organize_desc": "Control how new content is turned into reusable memory.",
        "settings.item.chat_provider": "Default answer service",
        "settings.item.chat_model": "Answer model",
        "settings.item.embedding_provider": "Memory search service",
        "settings.item.embedding_model": "Memory search model",
        "settings.item.extractor_provider": "Content organizer",
        "settings.item.extractor_model": "Organizer model",
        "settings.item.retrieval_profile": "Search style",
        "settings.item.recall_mode": "Deep recall",
        "settings.item.search_trace_enabled": "Keep source notes",
        "settings.item.graph_enabled": "Relationship support",
        "settings.raw.title": "RAW mode",
        "settings.raw.description": "View the full config payload with sensitive fields redacted.",
        "settings.raw.path": "Config path",
        "settings.raw.updated_at": "Last updated",
        "settings.raw.size": "Config size",
        "settings.raw.note": "RAW is best for advanced troubleshooting or bulk edits.",
        "settings.bool.on": "On",
        "settings.bool.off": "Off",
    },
}


def _parse_accept_language(raw: str | None) -> str | None:
    value = str(raw or "").strip()
    if not value:
        return None
    token = value.split(",")[0].strip().lower()
    if token.startswith("en"):
        return "en-US"
    if token.startswith("zh"):
        return "zh-CN"
    return None


def normalize_locale(locale: str | None, accept_language: str | None = None) -> str:
    requested = str(locale or "").strip()
    if requested in SUPPORTED_LOCALES:
        return requested
    parsed = _parse_accept_language(accept_language)
    if parsed in SUPPORTED_LOCALES:
        return parsed
    lowered = requested.lower()
    if lowered.startswith("en"):
        return "en-US"
    if lowered.startswith("zh"):
        return "zh-CN"
    return DEFAULT_LOCALE


def _t(locale: str, key: str, default: str | None = None) -> str:
    table = _LOCALE_TEXT.get(locale, _LOCALE_TEXT[DEFAULT_LOCALE])
    return str(table.get(key) or default or key)


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _safe_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _safe_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return list(raw)
    return []


def _source_name(runtime_id: str | None) -> str:
    token = str(runtime_id or "").strip()
    if not token:
        return "system"
    mapping = {
        "codex": "Codex",
        "claude": "Claude",
        "claude_code": "Claude Code",
        "openclaw": "OpenClaw",
        "openai": "OpenAI",
    }
    return mapping.get(token.lower(), token)


def _trim_text(value: Any, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _coerce_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    token = str(value or "").strip().lower()
    if not token:
        return fallback
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return fallback


def _parse_timestamp(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except Exception:
        return None


def _bool_text(locale: str, enabled: Any) -> str:
    return _t(locale, "settings.bool.on" if bool(enabled) else "settings.bool.off")


def _service_text(locale: str, value: Any) -> str:
    token = str(value or "").strip()
    if not token:
        return "-"
    mapping = {
        "siliconflow": "SiliconFlow",
        "openai": "OpenAI",
        "custom": "自定义服务" if locale == "zh-CN" else "Custom service",
        "local": "本地服务" if locale == "zh-CN" else "Local service",
        "chat_model": "沿用对话服务" if locale == "zh-CN" else "Use chat service",
        "rule": "规则整理" if locale == "zh-CN" else "Rule-based",
    }
    return mapping.get(token, token)


def _search_style_text(locale: str, value: Any) -> str:
    token = str(value or "").strip()
    if not token:
        return "-"
    mapping = {
        "agentic": "智能判断" if locale == "zh-CN" else "Smart choice",
        "hybrid": "综合查找" if locale == "zh-CN" else "Balanced",
        "rrf": "综合排序" if locale == "zh-CN" else "Blended ranking",
        "keyword": "关键词优先" if locale == "zh-CN" else "Keyword first",
        "vector": "语义优先" if locale == "zh-CN" else "Meaning first",
    }
    return mapping.get(token, token)


def _setting_value_text(locale: str, item_code: str, value_code: Any) -> str:
    if item_code in {"chat_provider", "embedding_provider", "extractor_provider"}:
        return _service_text(locale, value_code)
    if item_code == "retrieval_profile":
        return _search_style_text(locale, value_code)
    text = str(value_code or "").strip()
    return text or "-"


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    token = str(value or "").strip().lower()
    if not token:
        return default
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    elif value is None:
        values = []
    else:
        values = [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _path_list(value: Any) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for item in _string_list(value):
        try:
            path = Path(item).resolve()
        except Exception:
            continue
        token = str(path)
        if token in seen:
            continue
        seen.add(token)
        out.append(path)
    return out


def _assistant_id(source_code: str, assistant_name: str, subassistant_name: str | None = None) -> str:
    base = f"{source_code}:{assistant_name}"
    child = str(subassistant_name or "").strip()
    if not child:
        return base
    return f"{base}:{child}"


def _memory_identity(row: dict[str, Any]) -> str:
    for key in ("id", "memory_id", "event_id"):
        token = str(row.get(key) or "").strip()
        if token:
            return token
    summary = str(row.get("summary") or row.get("episode") or "").strip()
    if summary:
        return summary[:120]
    return uuid.uuid4().hex


def _assistant_registry_id(
    source_code: str,
    assistant_name: str,
    subassistant_name: str | None = None,
) -> str:
    parts = [str(source_code or "").strip() or "system", str(assistant_name or "").strip()]
    child = str(subassistant_name or "").strip()
    if child:
        parts.append(child)
    return ":".join(parts)


def _assistant_status(
    *,
    locale: str,
    recognition_state: str,
    last_seen_at: int | None,
) -> tuple[str, str, str, str]:
    now = int(time.time())
    if recognition_state == "pending_identification":
        return (
            "incomplete",
            _t(locale, "status.incomplete"),
            "awaiting_mapping",
            _t(locale, "status_reason.awaiting_mapping"),
        )
    if not last_seen_at:
        return (
            "attention",
            _t(locale, "status.attention"),
            "stale_activity",
            _t(locale, "status_reason.stale_activity"),
        )
    age = now - int(last_seen_at)
    if age <= 86400:
        return (
            "ok",
            _t(locale, "status.ok"),
            "recent_activity",
            _t(locale, "status_reason.recent_activity"),
        )
    if age <= 86400 * 7:
        return (
            "attention",
            _t(locale, "status.attention"),
            "stale_activity",
            _t(locale, "status_reason.stale_activity"),
        )
    return (
        "offline",
        _t(locale, "status.offline"),
        "no_recent_activity",
        _t(locale, "status_reason.no_recent_activity"),
    )


class PanelService:
    def __init__(self, engine: SQLiteEngine) -> None:
        self.engine = engine

    def overview(
        self,
        *,
        locale: str,
        scan_roots: list[Path] | None = None,
        config_repo: Any | None = None,
        settings: Any | None = None,
    ) -> dict[str, Any]:
        assistants_payload = self.assistants(
            locale=locale,
            scan_roots=scan_roots,
            config_repo=config_repo,
            settings=settings,
        )
        assistant_items = list(assistants_payload.get("items", []))
        now = int(time.time())
        since = now - 86400
        memory_count = self._count(
            "SELECT COUNT(1) AS count FROM episodic_memory WHERE is_deleted=0 AND created_at>=?",
            (since,),
        )
        feedback_count = self._count(
            "SELECT COUNT(1) AS count FROM knowledge_feedback WHERE created_at>=?",
            (since,),
        )
        assistant_count = sum(
            1 for item in assistant_items if item.get("assistant_role") == "primary"
        )
        active_subassistant_count = sum(
            1
            for item in assistant_items
            if item.get("assistant_role") == "subassistant"
            and item.get("status_code") == "ok"
        )
        issue_count = sum(
            1
            for item in assistant_items
            if item.get("status_code") in {"attention", "offline", "incomplete"}
        )
        cards = [
            self._metric_card(locale, "assistants_total", assistant_count),
            self._metric_card(locale, "subassistants_active", active_subassistant_count),
            self._metric_card(locale, "memories_24h", memory_count),
            self._metric_card(locale, "feedback_24h", feedback_count),
            self._metric_card(locale, "issues_total", issue_count),
        ]
        return {
            "locale": locale,
            "assistant_count": assistant_count,
            "active_subassistant_count": active_subassistant_count,
            "memory_count_24h": memory_count,
            "feedback_count_24h": feedback_count,
            "issue_count": issue_count,
            "cards": cards,
            "recent_issues": self._recent_issues(locale=locale, items=assistant_items),
            "recent_activity": self._recent_activity(locale=locale),
        }

    def assistants(
        self,
        *,
        locale: str,
        scan_roots: list[Path] | None = None,
        config_repo: Any | None = None,
        settings: Any | None = None,
    ) -> dict[str, Any]:
        return self._build_assistant_payload(
            locale=locale,
            scan_roots=scan_roots,
            config_repo=config_repo,
            settings=settings,
        )

    def assistant_detail(
        self,
        *,
        assistant_id: str,
        locale: str,
        scan_roots: list[Path] | None = None,
        config_repo: Any | None = None,
        settings: Any | None = None,
    ) -> dict[str, Any] | None:
        payload = self._build_assistant_payload(
            locale=locale,
            scan_roots=scan_roots,
            config_repo=config_repo,
            settings=settings,
        )
        items = payload.get("items") if isinstance(payload, dict) else []
        item = next(
            (
                dict(row)
                for row in items
                if str(row.get("assistant_id") or "").strip() == str(assistant_id or "").strip()
            ),
            None,
        )
        if item is None:
            return None
        identity_names = [
            str(item.get("assistant_name") or "").strip(),
            str(item.get("primary_assistant_name") or "").strip(),
            str(item.get("subassistant_name") or "").strip(),
        ]
        filtered_names = [name for name in identity_names if name and name != "pending"]
        recent_memories = [
            memory
            for memory in self.memories(locale=locale, limit=30).get("items", [])
            if str(memory.get("sender_name") or "").strip() in filtered_names
        ][:10]
        recent_feedback = [
            feedback
            for feedback in self.feedback(locale=locale).get("items", [])
            if str(feedback.get("sender_name") or "").strip() in filtered_names
            or any(str(name).strip() in filtered_names for name in feedback.get("target_names", []))
        ][:10]
        item["recent_memories"] = recent_memories
        item["recent_feedback"] = recent_feedback
        item["recent_errors"] = []
        return item

    def settings(
        self,
        *,
        locale: str,
        settings: Any,
        runtime_model_config: dict[str, Any] | None,
        runtime_policy_repo: Any,
        config_repo: Any | None = None,
    ) -> dict[str, Any]:
        model_config = dict(runtime_model_config or {})
        policy = runtime_policy_repo.get("default") if runtime_policy_repo else None
        policy_dict = policy.to_dict() if policy else {}
        active_profile = str(
            getattr(settings, "retrieval_profile", "") or policy_dict.get("profile") or "agentic"
        ).strip() or "agentic"
        panel_doc = self._panel_doc(config_repo=config_repo, settings=settings)
        authorized_scan_roots = [
            str(path)
            for path in self._authorized_scan_roots(config_repo=config_repo, settings=settings)
        ]
        assistant_auto_sync_enabled = _coerce_bool(
            panel_doc.get("assistant_auto_sync_enabled"),
            True,
        )
        assistant_registry_count = len(
            self._assistant_registry_items(
                config_repo=config_repo,
                settings=settings,
                scan_roots=None,
            )
        )
        provider_options = (
            model_config.get("chat_provider_options")
            if isinstance(model_config.get("chat_provider_options"), dict)
            else {}
        )
        common_items = [
            self._settings_item(
                locale=locale,
                item_code="chat_provider",
                value_code=str(model_config.get("chat_provider") or ""),
                control_type="select",
                raw_path="models.chat.provider",
                impact_text=(
                    "会影响新对话默认使用哪一路回答服务。"
                    if locale == "zh-CN"
                    else "Controls which answer service new chats use by default."
                ),
                options=self._provider_options(locale=locale, provider_options=provider_options),
            ),
            self._settings_item(
                locale=locale,
                item_code="chat_model",
                value_code=str(model_config.get("chat_model") or ""),
                control_type="text",
                raw_path="models.chat.model",
                impact_text=(
                    "会影响新对话默认使用的回答模型。"
                    if locale == "zh-CN"
                    else "Controls the default answer model for new chats."
                ),
            ),
            self._settings_item(
                locale=locale,
                item_code="retrieval_profile",
                value_code=active_profile,
                control_type="select",
                raw_path="settings.retrieval_profile",
                impact_text=(
                    "决定系统更偏向综合查找、关键词优先还是语义优先。"
                    if locale == "zh-CN"
                    else "Controls whether the system prefers blended, keyword-first, or meaning-first search."
                ),
                options=self._retrieval_profile_options(locale=locale),
            ),
        ]
        assistant_items = [
            self._settings_item(
                locale=locale,
                item_code="authorized_scan_roots",
                label_text="本地说明文件目录" if locale == "zh-CN" else "Local file folders",
                value_code="\n".join(authorized_scan_roots),
                value_text=(
                    "、".join(authorized_scan_roots)
                    if authorized_scan_roots and locale == "zh-CN"
                    else (
                        ", ".join(authorized_scan_roots)
                        if authorized_scan_roots
                        else ("尚未添加额外目录" if locale == "zh-CN" else "No extra folders added")
                    )
                ),
                control_type="list",
                raw_path="panel.authorized_scan_roots",
                impact_text=(
                    "影响哪些目录会参与 AGENTS.md / SOUL.md / MEMORY 等本地说明文件检测。"
                    if locale == "zh-CN"
                    else "Controls which folders are checked for AGENTS.md / SOUL.md / MEMORY and related local files."
                ),
            ),
            self._settings_item(
                locale=locale,
                item_code="assistant_auto_sync_enabled",
                label_text="自动同步助手状态" if locale == "zh-CN" else "Auto sync assistant status",
                value_code=str(bool(assistant_auto_sync_enabled)).lower(),
                value_text=_bool_text(locale, assistant_auto_sync_enabled),
                control_type="toggle",
                raw_path="panel.assistant_auto_sync_enabled",
                impact_text=(
                    "开启后，面板会优先根据最近活动刷新助手状态。"
                    if locale == "zh-CN"
                    else "When enabled, the panel refreshes assistant status from recent activity first."
                ),
            ),
            self._settings_item(
                locale=locale,
                item_code="registered_assistant_count",
                label_text="已登记助手数量" if locale == "zh-CN" else "Registered assistants",
                value_code=str(assistant_registry_count),
                value_text=str(assistant_registry_count),
                control_type="readonly",
                raw_path="panel.assistant_registry",
                impact_text=(
                    "这是当前已经登记在助手接入视图中的助手数量。"
                    if locale == "zh-CN"
                    else "This is the number of assistants currently registered in the assistant access view."
                ),
                visual_editable=False,
            ),
        ]
        memory_items = [
            self._settings_item(
                locale=locale,
                item_code="recall_mode",
                value_code=str(bool(getattr(settings, "recall_mode", False))).lower(),
                value_text=_bool_text(locale, getattr(settings, "recall_mode", False)),
                control_type="toggle",
                raw_path="settings.recall_mode",
                impact_text=(
                    "开启后会加强长链路回想，通常需要重启后完全生效。"
                    if locale == "zh-CN"
                    else "When enabled, long-range recall is stronger and usually needs a restart to fully apply."
                ),
            ),
            self._settings_item(
                locale=locale,
                item_code="embedding_provider",
                value_code=str(model_config.get("embedding_provider") or ""),
                control_type="select",
                raw_path="models.embedding.provider",
                impact_text=(
                    "决定系统用哪一路服务查找历史记忆。修改后通常需要重启后再观察效果。"
                    if locale == "zh-CN"
                    else "Controls which service searches past memory. Changes usually need a restart before evaluation."
                ),
                options=self._simple_provider_options(
                    locale=locale,
                    values=("local", "openai", "siliconflow", "custom"),
                ),
            ),
            self._settings_item(
                locale=locale,
                item_code="embedding_model",
                value_code=str(model_config.get("embedding_model") or ""),
                control_type="text",
                raw_path="models.embedding.model",
                impact_text=(
                    "决定系统查找记忆时使用的模型。"
                    if locale == "zh-CN"
                    else "Controls the model used to search memory."
                ),
            ),
            self._settings_item(
                locale=locale,
                item_code="extractor_provider",
                value_code=str(model_config.get("extractor_provider") or ""),
                control_type="select",
                raw_path="models.extractor.provider",
                impact_text=(
                    "决定新内容如何被整理成可复用记忆。"
                    if locale == "zh-CN"
                    else "Controls how new content is shaped into reusable memory."
                ),
                options=self._simple_provider_options(
                    locale=locale,
                    values=("rule", "chat_model", "openai", "siliconflow", "custom"),
                ),
            ),
            self._settings_item(
                locale=locale,
                item_code="extractor_model",
                value_code=str(model_config.get("extractor_model") or ""),
                control_type="text",
                raw_path="models.extractor.model",
                impact_text=(
                    "决定整理阶段默认使用的模型。"
                    if locale == "zh-CN"
                    else "Controls the default model used during memory shaping."
                ),
            ),
        ]
        sharing_items = [
            self._settings_item(
                locale=locale,
                item_code="graph_enabled",
                value_code=str(bool(getattr(settings, "graph_enabled", False))).lower(),
                value_text=_bool_text(locale, getattr(settings, "graph_enabled", False)),
                control_type="toggle",
                raw_path="settings.graph_enabled",
                impact_text=(
                    "开启后会补充关系线索，帮助回答补足上下文。"
                    if locale == "zh-CN"
                    else "Adds relationship hints to help answers fill in context."
                ),
            ),
            self._settings_item(
                locale=locale,
                item_code="search_trace_enabled",
                value_code=str(bool(getattr(settings, "search_trace_enabled", False))).lower(),
                value_text=_bool_text(
                    locale,
                    getattr(settings, "search_trace_enabled", False),
                ),
                control_type="toggle",
                raw_path="settings.search_trace_enabled",
                impact_text=(
                    "开启后会保留更完整的来源说明。"
                    if locale == "zh-CN"
                    else "Keeps fuller source notes for later explanation."
                ),
            ),
        ]
        advanced_items = [
            self._settings_item(
                locale=locale,
                item_code="chat_runtime_provider",
                label_text="当前回答服务" if locale == "zh-CN" else "Current answer service",
                value_code=str(model_config.get("chat_provider") or ""),
                value_text=_service_text(locale, model_config.get("chat_provider") or ""),
                control_type="readonly",
                raw_path="models.chat.provider",
                visual_editable=False,
                impact_text=(
                    "用于快速确认当前运行中的回答服务。"
                    if locale == "zh-CN"
                    else "Quickly shows the answer service currently in use."
                ),
            ),
            self._settings_item(
                locale=locale,
                item_code="config_path",
                label_text="配置文件位置" if locale == "zh-CN" else "Config file path",
                value_code=str(getattr(settings, "config_path", "")),
                value_text=str(getattr(settings, "config_path", "")),
                control_type="readonly",
                raw_path="settings.config_path",
                visual_editable=False,
                impact_text=(
                    "高级排查时可直接前往 RAW 模式查看完整配置。"
                    if locale == "zh-CN"
                    else "Use RAW mode for full configuration inspection when troubleshooting."
                ),
            ),
        ]
        tabs = [
            {
                "tab_code": "common",
                "title": "常用" if locale == "zh-CN" else "Common",
                "description": (
                    "最常用的回答与查找设置。"
                    if locale == "zh-CN"
                    else "The most common answer and search choices."
                ),
                "items": common_items,
            },
            {
                "tab_code": "assistants",
                "title": "助手接入" if locale == "zh-CN" else "Assistants",
                "description": (
                    "配置助手登记与本地说明文件检测范围。"
                    if locale == "zh-CN"
                    else "Configure assistant registration and local file scan coverage."
                ),
                "items": assistant_items,
            },
            {
                "tab_code": "memory",
                "title": "记忆偏好" if locale == "zh-CN" else "Memory",
                "description": (
                    "决定系统如何找回和整理记忆。"
                    if locale == "zh-CN"
                    else "Controls how the system recalls and shapes memory."
                ),
                "items": memory_items,
            },
            {
                "tab_code": "sharing",
                "title": "共享设置" if locale == "zh-CN" else "Sharing",
                "description": (
                    "决定来源说明和关系补充如何进入回答。"
                    if locale == "zh-CN"
                    else "Controls how source notes and relationship hints enter answers."
                ),
                "items": sharing_items,
            },
            {
                "tab_code": "advanced",
                "title": "高级" if locale == "zh-CN" else "Advanced",
                "description": (
                    "显示运行信息，并引导进入 RAW 模式。"
                    if locale == "zh-CN"
                    else "Shows runtime information and points advanced users to RAW mode."
                ),
                "items": advanced_items,
            },
        ]
        cards = [
            {
                "card_code": "common",
                "label": "当前回答" if locale == "zh-CN" else "Current answer",
                "value": _setting_value_text(
                    locale,
                    "chat_provider",
                    model_config.get("chat_provider") or "",
                ),
            },
            {
                "card_code": "memory",
                "label": "当前检索" if locale == "zh-CN" else "Current search",
                "value": _setting_value_text(locale, "retrieval_profile", active_profile),
            },
            {
                "card_code": "assistants",
                "label": "助手接入" if locale == "zh-CN" else "Assistants",
                "value": (
                    f"{assistant_registry_count} 个已登记"
                    if locale == "zh-CN"
                    else f"{assistant_registry_count} registered"
                ),
            },
            {
                "card_code": "raw",
                "label": _t(locale, "settings.card.raw"),
                "value": _bool_text(locale, True),
            },
        ]
        items_index = {
            str(item.get("setting_key") or item.get("item_code") or ""): item
            for tab in tabs
            for item in tab.get("items", [])
            if str(item.get("setting_key") or item.get("item_code") or "").strip()
        }
        return {
            "locale": locale,
            "cards": cards,
            "tabs": tabs,
            "items_index": items_index,
            "runtime_policy": {"tenant_id": "default", "policy": policy_dict},
            "raw_mode": {
                "enabled": True,
                "path": str(getattr(settings, "config_path", "")),
                "title": _t(locale, "settings.raw.title"),
                "description": _t(locale, "settings.raw.description"),
                "note": _t(locale, "settings.raw.note"),
            },
        }

    def settings_raw(
        self,
        *,
        locale: str,
        settings: Any,
        config_repo: Any,
    ) -> dict[str, Any]:
        payload = config_repo.get_raw_config(settings) if config_repo else {}
        redacted = redact_sensitive(payload)
        config_path = Path(getattr(config_repo, "config_path", getattr(settings, "config_path", "")))
        stat = config_path.stat() if config_path and config_path.exists() else None
        return {
            "locale": locale,
            "title": _t(locale, "settings.raw.title"),
            "description": _t(locale, "settings.raw.description"),
            "config": redacted,
            "raw_json": json.dumps(redacted, ensure_ascii=False, indent=2),
            "path": str(config_path),
            "updated_at": int(stat.st_mtime) if stat else None,
            "size_bytes": int(stat.st_size) if stat else None,
            "fields": [
                {
                    "field_code": "path",
                    "label": _t(locale, "settings.raw.path"),
                    "value": str(config_path),
                },
                {
                    "field_code": "updated_at",
                    "label": _t(locale, "settings.raw.updated_at"),
                    "value": int(stat.st_mtime) if stat else None,
                },
                {
                    "field_code": "size",
                    "label": _t(locale, "settings.raw.size"),
                    "value": int(stat.st_size) if stat else None,
                },
            ],
            "note": _t(locale, "settings.raw.note"),
        }

    def feedback(self, *, locale: str) -> dict[str, Any]:
        rows = self._feedback_rows(limit=100)
        items = [self._feedback_item(locale=locale, row=row) for row in rows]

        summary = {
            "total": len(items),
            "remembered_count": sum(1 for item in items if item["result_code"] == "remembered"),
            "pending_count": sum(1 for item in items if item["result_code"] == "pending"),
            "rejected_count": sum(1 for item in items if item["result_code"] == "rejected"),
            "rolled_back_count": sum(
                1 for item in items if item["result_code"] == "rolled_back"
            ),
        }
        return {"locale": locale, "summary": summary, "items": items}

    def feedback_detail(self, *, feedback_id: str, locale: str) -> dict[str, Any] | None:
        row = self._feedback_row(feedback_id=feedback_id)
        if not row:
            return None
        item = self._feedback_item(locale=locale, row=row)
        payload = _safe_json(row.get("feedback_payload"))
        item["payload"] = payload
        item["knowledge_id"] = str(row.get("knowledge_id") or "")
        item["revision_id"] = str(row.get("revision_id") or "")
        item["scope_type"] = str(row.get("scope_type") or "")
        item["scope_id"] = str(row.get("scope_id") or "")
        item["runtime_id"] = str(row.get("runtime_id") or "")
        item["agent_id"] = str(row.get("agent_id") or "")
        item["subagent_id"] = str(row.get("subagent_id") or "")
        item["team_id"] = str(row.get("team_id") or "")
        item["session_id"] = str(row.get("session_id") or "")
        return item

    def memories(
        self,
        *,
        locale: str,
        query: str | None = None,
        user_id: str | None = None,
        group_id: str | None = None,
        sender: str | None = None,
        target: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        rows = self._memory_rows(
            query=query,
            user_id=user_id,
            group_id=group_id,
            sender=sender,
            target=target,
            limit=limit,
        )
        items = [self._memory_item(locale=locale, row=row) for row in rows]
        summary = {
            "total": len(items),
            "remembered_count": sum(1 for item in items if item["status_code"] == "remembered"),
            "disabled_count": sum(1 for item in items if item["status_code"] == "disabled"),
            "shared_count": sum(1 for item in items if item["share_scope_code"] == "team_shared"),
        }
        return {"locale": locale, "summary": summary, "items": items}

    def memory_detail(self, *, memory_id: str, locale: str) -> dict[str, Any] | None:
        row = self.engine.query_one(
            """
            SELECT
              id,
              event_id,
              source_message_id,
              user_id,
              group_id,
              timestamp,
              role,
              sender,
              sender_name,
              group_name,
              episode,
              summary,
              subject,
              importance_score,
              scene_id,
              storage_tier,
              memory_category,
              is_deleted,
              created_at,
              updated_at
            FROM episodic_memory
            WHERE id=?
            """,
            (memory_id,),
        )
        if not row:
            return None
        item = self._memory_item(locale=locale, row=row)
        item["content"] = str(row.get("episode") or "")
        item["event_id"] = str(row.get("event_id") or "")
        item["source_message_id"] = str(row.get("source_message_id") or "")
        item["scene_id"] = row.get("scene_id")
        item["related_feedback"] = self._memory_feedback(locale=locale, memory_id=memory_id, limit=10)
        item["facts"] = [
            str(fact.get("fact") or "").strip()
            for fact in self.engine.query_all(
                "SELECT fact FROM memory_fact WHERE memory_id=? ORDER BY id ASC LIMIT 20",
                (memory_id,),
            )
            if str(fact.get("fact") or "").strip()
        ]
        return item

    def chat(
        self,
        *,
        question: str,
        locale: str,
        chat_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = dict(chat_result or {})
        citations = result.get("citations") if isinstance(result.get("citations"), list) else []
        retrieved = (
            result.get("retrieved_memories") if isinstance(result.get("retrieved_memories"), list) else []
        )
        used_ids = {
            str(item.get("id") or item.get("event_id") or item.get("summary") or "").strip()
            for item in citations
            if isinstance(item, dict)
        }
        used_source_cards = [
            self._chat_source_card(locale=locale, row=item, used_in_answer=True)
            for item in citations
            if isinstance(item, dict)
        ]
        hit_only_source_cards = [
            self._chat_source_card(locale=locale, row=item, used_in_answer=False)
            for item in retrieved
            if isinstance(item, dict)
            and str(item.get("id") or item.get("event_id") or item.get("summary") or "").strip()
            not in used_ids
        ]
        explain_cards = self._chat_explain_cards(
            locale=locale,
            citations=citations,
            retrieved=retrieved,
            chat_result=result,
        )
        explain_groups = self._group_explain_cards(locale=locale, explain_cards=explain_cards)
        return {
            "trace_id": uuid.uuid4().hex,
            "question": question,
            "answer": str(result.get("answer") or _t(locale, "chat.answer.placeholder")),
            "used_memory": bool(used_source_cards),
            "memory_hit_count": len(retrieved),
            "memory_used_count": len(used_source_cards),
            "used_source_cards": used_source_cards,
            "hit_only_source_cards": hit_only_source_cards,
            "explain_cards": explain_cards,
            "explain_groups": explain_groups,
            "provider": str(result.get("provider") or ""),
            "model": str(result.get("model") or ""),
            "conversation_id": str(result.get("conversation_id") or ""),
            "locale": locale,
            "generated_at": int(time.time()),
        }

    def _metric_card(self, locale: str, card_code: str, value: int) -> dict[str, Any]:
        return {
            "card_code": card_code,
            "label": _t(locale, f"card.{card_code}"),
            "value": int(value),
        }

    def _settings_item(
        self,
        *,
        locale: str,
        item_code: str,
        value_code: str,
        value_text: str | None = None,
        label_text: str | None = None,
        control_type: str = "text",
        raw_path: str | None = None,
        impact_text: str | None = None,
        visual_editable: bool = True,
        options: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        text = (
            str(value_text).strip()
            if value_text is not None
            else _setting_value_text(locale, item_code, value_code)
        ) or "-"
        return {
            "item_code": item_code,
            "setting_key": item_code,
            "label": str(label_text or _t(locale, f"settings.item.{item_code}")),
            "value_code": str(value_code or ""),
            "value_text": text,
            "control_type": control_type,
            "raw_path": raw_path,
            "impact_text": str(impact_text or "").strip(),
            "visual_editable": bool(visual_editable),
            "options": list(options or []),
        }

    def normalize_assistant_registry_entry(
        self,
        *,
        payload: dict[str, Any],
        scan_roots: list[Path] | None = None,
    ) -> dict[str, Any] | None:
        source_code = str(payload.get("source_code") or payload.get("source") or "").strip() or "system"
        assistant_name = str(payload.get("assistant_name") or payload.get("assistant") or "").strip()
        subassistant_name = str(
            payload.get("subassistant_name") or payload.get("subassistant") or ""
        ).strip()
        if not assistant_name:
            return None
        resolved_roots = self._normalize_workspace_roots(
            payload.get("workspace_roots"),
            fallback_roots=scan_roots,
        )
        item = {
            "assistant_id": _assistant_registry_id(
                source_code,
                assistant_name,
                subassistant_name or None,
            ),
            "source_code": source_code,
            "assistant_name": assistant_name,
            "subassistant_name": subassistant_name or None,
            "workspace_roots": resolved_roots,
            "note": str(payload.get("note") or "").strip(),
        }
        return item

    def serialize_assistant_registry_items(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for item in items:
            assistant_name = str(item.get("assistant_name") or "").strip()
            if not assistant_name:
                continue
            serialized.append(
                {
                    "source_code": str(item.get("source_code") or "").strip() or "system",
                    "assistant_name": assistant_name,
                    "subassistant_name": (
                        str(item.get("subassistant_name") or "").strip() or None
                    ),
                    "workspace_roots": [
                        str(path).strip()
                        for path in _safe_list(item.get("workspace_roots"))
                        if str(path).strip()
                    ],
                    "note": str(item.get("note") or "").strip(),
                }
            )
        return serialized

    def _provider_options(
        self,
        *,
        locale: str,
        provider_options: dict[str, Any],
    ) -> list[dict[str, Any]]:
        values = list(provider_options.keys()) or ["openai"]
        return self._simple_provider_options(locale=locale, values=values)

    def _simple_provider_options(
        self,
        *,
        locale: str,
        values: tuple[str, ...] | list[str],
    ) -> list[dict[str, Any]]:
        return [
            {
                "value_code": str(value),
                "value_text": _service_text(locale, value),
            }
            for value in values
            if str(value).strip()
        ]

    def _retrieval_profile_options(self, *, locale: str) -> list[dict[str, Any]]:
        values = ("agentic", "hybrid", "rrf", "keyword", "vector")
        return [
            {
                "value_code": value,
                "value_text": _search_style_text(locale, value),
            }
            for value in values
        ]

    def _build_assistant_payload(
        self,
        *,
        locale: str,
        scan_roots: list[Path] | None,
        config_repo: Any | None,
        settings: Any | None,
    ) -> dict[str, Any]:
        authorized_roots = self._authorized_scan_roots(
            config_repo=config_repo,
            settings=settings,
        )
        default_roots = self._normalize_scan_roots([*(scan_roots or []), *authorized_roots])
        registry_items = self._assistant_registry_items(
            config_repo=config_repo,
            settings=settings,
            scan_roots=default_roots,
        )
        items: dict[str, dict[str, Any]] = {}
        child_links: dict[str, list[str]] = {}

        for registry_item in registry_items:
            assistant_roots = self._normalize_scan_roots(
                [
                    *[
                        Path(path)
                        for path in _safe_list(registry_item.get("workspace_roots"))
                        if str(path).strip()
                    ],
                    *authorized_roots,
                ]
            )
            assistant = self._base_assistant_item(
                locale=locale,
                source_code=str(registry_item.get("source_code") or "system"),
                assistant_name=str(registry_item.get("assistant_name") or ""),
                subassistant_name=registry_item.get("subassistant_name"),
                workspace_roots=[str(path) for path in assistant_roots],
                note=str(registry_item.get("note") or ""),
                recognition_state="registered",
                registration_source="panel_registry",
            )
            items[str(assistant["assistant_id"])] = assistant
            parent_assistant_id = str(assistant.get("parent_assistant_id") or "").strip()
            assistant_id = str(assistant.get("assistant_id") or "").strip()
            if parent_assistant_id and assistant_id:
                child_links.setdefault(parent_assistant_id, [])
                if assistant_id not in child_links[parent_assistant_id]:
                    child_links[parent_assistant_id].append(assistant_id)

        for row in self._assistant_events():
            source_code = str(row.get("runtime_id") or "").strip() or "system"
            assistant_name = str(row.get("agent_id") or "").strip()
            subassistant_name = str(row.get("subagent_id") or "").strip()
            seen_at = _safe_int(row.get("created_at")) or 0

            if assistant_name:
                assistant_id = _assistant_registry_id(source_code, assistant_name)
                assistant = items.get(assistant_id)
                if assistant is None:
                    assistant = self._base_assistant_item(
                        locale=locale,
                        source_code=source_code,
                        assistant_name=assistant_name,
                        workspace_roots=[],
                        recognition_state="observed",
                        registration_source="collective_event",
                    )
                    items[assistant_id] = assistant
                assistant["last_seen_at"] = max(int(assistant.get("last_seen_at") or 0), seen_at)

            if subassistant_name:
                parent_assistant_id = (
                    _assistant_registry_id(source_code, assistant_name) if assistant_name else None
                )
                child_assistant_name = assistant_name or "pending"
                child_id = _assistant_registry_id(source_code, child_assistant_name, subassistant_name)
                child = items.get(child_id)
                recognition_state = "observed" if parent_assistant_id else "pending_identification"
                if child is None:
                    child = self._base_assistant_item(
                        locale=locale,
                        source_code=source_code,
                        assistant_name=child_assistant_name,
                        subassistant_name=subassistant_name,
                        workspace_roots=[],
                        recognition_state=recognition_state,
                        registration_source="collective_event",
                    )
                    items[child_id] = child
                child["last_seen_at"] = max(int(child.get("last_seen_at") or 0), seen_at)
                if parent_assistant_id:
                    child["parent_assistant_id"] = parent_assistant_id
                    child["parent_assistant_name"] = assistant_name
                    child_links.setdefault(parent_assistant_id, [])
                    if child_id not in child_links[parent_assistant_id]:
                        child_links[parent_assistant_id].append(child_id)

        final_items: list[dict[str, Any]] = []
        for assistant in items.values():
            assistant["children"] = child_links.get(str(assistant.get("assistant_id") or ""), [])
            self._attach_assistant_activity(assistant)
            self._apply_assistant_status(assistant=assistant, locale=locale)
            assistant["recent_check_status_code"] = assistant["status_code"]
            assistant["recent_check_status_text"] = assistant["status_text"]
            assistant["child_count"] = len(assistant["children"])
            final_items.append(assistant)

        final_items.sort(
            key=lambda item: (
                0 if item.get("assistant_role") == "primary" else 1,
                0 if item.get("recognition_state") == "registered" else 1,
                0 if item.get("recognition_state") != "pending_identification" else 1,
                -int(item.get("last_seen_at") or 0),
                str(item.get("assistant_name") or ""),
                str(item.get("subassistant_name") or ""),
            )
        )
        summary = {
            "assistant_count": len(final_items),
            "primary_count": sum(
                1 for item in final_items if item.get("assistant_role") == "primary"
            ),
            "subassistant_count": sum(
                1 for item in final_items if item.get("assistant_role") == "subassistant"
            ),
            "registered_count": sum(
                1 for item in final_items if item.get("recognition_state") == "registered"
            ),
            "observed_count": sum(
                1 for item in final_items if item.get("recognition_state") == "observed"
            ),
            "pending_identification_count": sum(
                1
                for item in final_items
                if item.get("recognition_state") == "pending_identification"
            ),
        }
        return {"locale": locale, "summary": summary, "items": final_items}

    def _assistant_registry_items(
        self,
        *,
        config_repo: Any | None,
        settings: Any | None,
        scan_roots: list[Path] | None,
    ) -> list[dict[str, Any]]:
        panel_doc = self._panel_doc(config_repo=config_repo, settings=settings)
        raw_items = _safe_list(panel_doc.get("assistant_registry"))
        items: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            normalized = self.normalize_assistant_registry_entry(
                payload=raw_item,
                scan_roots=scan_roots,
            )
            if normalized is None:
                continue
            items.append(normalized)
        return items

    def _authorized_scan_roots(
        self,
        *,
        config_repo: Any | None,
        settings: Any | None,
    ) -> list[Path]:
        panel_doc = self._panel_doc(config_repo=config_repo, settings=settings)
        return self._normalize_scan_roots(
            [Path(path) for path in _safe_list(panel_doc.get("authorized_scan_roots")) if str(path).strip()]
        )

    def _panel_doc(self, *, config_repo: Any | None, settings: Any | None) -> dict[str, Any]:
        if not config_repo or settings is None:
            return {}
        payload = config_repo.get_raw_config(settings)
        if not isinstance(payload, dict):
            return {}
        panel_doc = payload.get("panel")
        return dict(panel_doc) if isinstance(panel_doc, dict) else {}

    def _normalize_workspace_roots(
        self,
        raw_roots: Any,
        *,
        fallback_roots: list[Path] | None,
    ) -> list[str]:
        roots: list[Path] = []
        for raw in _safe_list(raw_roots):
            try:
                roots.append(Path(str(raw)).resolve())
            except Exception:
                continue
        normalized = self._normalize_scan_roots(roots)
        return [str(path) for path in normalized]

    def _base_assistant_item(
        self,
        *,
        locale: str,
        source_code: str,
        assistant_name: str,
        workspace_roots: Any,
        recognition_state: str,
        registration_source: str,
        subassistant_name: str | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        roots = self._normalize_scan_roots(
            [Path(path) for path in _safe_list(workspace_roots) if str(path).strip()]
        )
        assistant_role = "subassistant" if str(subassistant_name or "").strip() else "primary"
        assistant_id = _assistant_registry_id(source_code, assistant_name, subassistant_name)
        has_stable_parent = assistant_role == "subassistant" and str(assistant_name or "").strip() not in {
            "",
            "pending",
        }
        parent_assistant_id = (
            _assistant_registry_id(source_code, assistant_name) if has_stable_parent else None
        )
        parent_assistant_name = assistant_name if has_stable_parent else None
        display_name = str(subassistant_name or assistant_name).strip()
        return {
            "assistant_id": assistant_id,
            "source_code": source_code,
            "source_name": _source_name(source_code),
            "assistant_name": display_name,
            "primary_assistant_name": assistant_name,
            "subassistant_name": str(subassistant_name or "").strip() or None,
            "assistant_role": assistant_role,
            "parent_assistant_id": parent_assistant_id,
            "parent_assistant_name": parent_assistant_name,
            "registration_source": registration_source,
            "recognition_state": recognition_state,
            "recognition_text": _t(locale, f"recognition.{recognition_state}"),
            "workspace_roots": [str(path) for path in roots],
            "note": note,
            "last_seen_at": None,
            "last_feedback_at": None,
            "memory_count_private": 0,
            "memory_count_shared": 0,
            "last_memory_used_at": None,
            "local_files": self._scan_local_files(locale=locale, scan_roots=roots),
            "children": [],
        }

    def _attach_assistant_activity(self, assistant: dict[str, Any]) -> None:
        source_code = str(assistant.get("source_code") or "").strip() or "system"
        assistant_role = str(assistant.get("assistant_role") or "primary")
        primary_name = str(assistant.get("primary_assistant_name") or assistant.get("assistant_name") or "").strip()
        subassistant_name = str(assistant.get("subassistant_name") or "").strip()
        if assistant_role == "subassistant" and subassistant_name:
            feedback_row = self.engine.query_one(
                """
                SELECT MAX(created_at) AS max_created_at, COUNT(1) AS feedback_count
                FROM knowledge_feedback
                WHERE COALESCE(runtime_id, 'system')=? AND subagent_id=?
                """,
                (source_code, subassistant_name),
            )
        else:
            feedback_row = self.engine.query_one(
                """
                SELECT MAX(created_at) AS max_created_at, COUNT(1) AS feedback_count
                FROM knowledge_feedback
                WHERE COALESCE(runtime_id, 'system')=? AND agent_id=?
                """,
                (source_code, primary_name),
            )
        if feedback_row:
            assistant["last_feedback_at"] = _safe_int(feedback_row.get("max_created_at"))
        memory_sender = subassistant_name or primary_name
        memory_row = self.engine.query_one(
            """
            SELECT
              COUNT(1) AS memory_count,
              MAX(updated_at) AS max_updated_at,
              SUM(
                CASE
                  WHEN COALESCE(group_id, '') <> '' AND COALESCE(group_id, '') <> ?
                  THEN 1
                  ELSE 0
                END
              ) AS shared_count
            FROM episodic_memory
            WHERE is_deleted=0 AND (
              sender=?
              OR sender_name=?
              OR user_id=?
            )
            """,
            (
                f"default:{memory_sender}" if memory_sender else "",
                memory_sender,
                memory_sender,
                memory_sender,
            ),
        )
        if memory_row:
            total = int(memory_row.get("memory_count") or 0)
            shared_count = int(memory_row.get("shared_count") or 0)
            assistant["memory_count_private"] = max(0, total - shared_count)
            assistant["memory_count_shared"] = max(0, shared_count)
            assistant["last_memory_used_at"] = _safe_int(memory_row.get("max_updated_at"))

    def _count(self, sql: str, params: tuple[Any, ...]) -> int:
        row = self.engine.query_one(sql, params)
        if not row:
            return 0
        return int(row.get("count") or 0)

    def _assistant_events(self) -> list[dict[str, Any]]:
        return self.engine.query_all(
            """
            SELECT runtime_id, agent_id, subagent_id, created_at
            FROM knowledge_revision
            WHERE COALESCE(agent_id, '') <> '' OR COALESCE(subagent_id, '') <> ''
            UNION ALL
            SELECT runtime_id, agent_id, subagent_id, created_at
            FROM knowledge_feedback
            WHERE COALESCE(agent_id, '') <> '' OR COALESCE(subagent_id, '') <> ''
            """
        )

    def _normalize_scan_roots(self, scan_roots: list[Path] | None) -> list[Path]:
        seen: set[str] = set()
        normalized: list[Path] = []
        for raw in scan_roots or []:
            try:
                path = Path(raw).resolve()
            except Exception:
                continue
            token = str(path)
            if token in seen:
                continue
            seen.add(token)
            normalized.append(path)
        return normalized

    def _clone_local_files(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(item) for item in items]

    def _scan_local_files(
        self,
        *,
        locale: str,
        scan_roots: list[Path],
    ) -> list[dict[str, Any]]:
        if not scan_roots:
            return self._default_local_files(locale=locale)
        checked_at = int(time.time())
        items: list[dict[str, Any]] = []
        for file_key, display_name in _FILE_SPECS:
            matched_path: Path | None = None
            readable = False
            for root in scan_roots:
                candidate = root / display_name
                if not candidate.exists():
                    continue
                matched_path = candidate
                try:
                    readable = candidate.is_file()
                    if readable:
                        candidate.read_text(encoding="utf-8")
                except Exception:
                    readable = False
                break
            exists = matched_path is not None
            if exists and readable:
                status_code = "recognized"
            elif exists:
                status_code = "unreadable"
            else:
                status_code = "missing"
            items.append(
                {
                    "file_key": file_key,
                    "display_name": display_name,
                    "file_path": str(matched_path) if matched_path else None,
                    "exists": exists,
                    "readable": readable,
                    "included_in_access": True,
                    "status_code": status_code,
                    "status_text": _t(locale, f"file.{status_code}"),
                    "last_checked_at": checked_at,
                }
            )
        return items

    def _default_local_files(self, *, locale: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for file_key, display_name in _FILE_SPECS:
            items.append(
                {
                    "file_key": file_key,
                    "display_name": display_name,
                    "file_path": None,
                    "exists": False,
                    "readable": False,
                    "included_in_access": False,
                    "status_code": "not_in_scope",
                    "status_text": _t(locale, "file.not_in_scope"),
                    "last_checked_at": None,
                }
            )
        return items

    def _apply_assistant_status(self, *, assistant: dict[str, Any], locale: str) -> None:
        recognition_state = str(assistant.get("recognition_state") or "observed")
        status_code, status_text, reason_code, reason_text = _assistant_status(
            locale=locale,
            recognition_state=recognition_state,
            last_seen_at=_safe_int(assistant.get("last_seen_at")),
        )
        assistant["status_code"] = status_code
        assistant["status_text"] = status_text
        assistant["status_reason_code"] = reason_code
        assistant["status_reason_text"] = reason_text

    def _recent_issues(
        self, *, locale: str, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        pending_count = sum(
            1
            for item in items
            if item.get("recognition_state") == "pending_identification"
        )
        if pending_count:
            issues.append(
                {
                    "issue_code": "pending_identification",
                    "severity_code": "attention",
                    "severity_text": _t(locale, "status.attention"),
                    "message": _t(locale, "issue.pending_identification"),
                    "count": pending_count,
                }
            )
        if items and all(
            all(file_item.get("status_code") == "not_in_scope" for file_item in item["local_files"])
            for item in items
        ):
            issues.append(
                {
                    "issue_code": "no_files_in_scope",
                    "severity_code": "attention",
                    "severity_text": _t(locale, "status.attention"),
                    "message": _t(locale, "issue.no_files_in_scope"),
                    "count": len(items),
                }
            )
        return issues

    def _recent_activity(self, *, locale: str) -> list[dict[str, Any]]:
        rows = self.engine.query_all(
            """
            SELECT kind_code, title, created_at
            FROM (
              SELECT
                'memory_created' AS kind_code,
                COALESCE(summary, sender, '') AS title,
                created_at
              FROM episodic_memory
              WHERE is_deleted=0
              UNION ALL
              SELECT
                'feedback_created' AS kind_code,
                COALESCE(actor, feedback_type, '') AS title,
                created_at
              FROM knowledge_feedback
              UNION ALL
              SELECT
                'assistant_seen' AS kind_code,
                COALESCE(subagent_id, agent_id, runtime_id, '') AS title,
                created_at
              FROM knowledge_revision
              WHERE COALESCE(agent_id, '') <> '' OR COALESCE(subagent_id, '') <> ''
            )
            ORDER BY created_at DESC
            LIMIT 8
            """
        )
        activity: list[dict[str, Any]] = []
        for row in rows:
            kind_code = str(row.get("kind_code") or "")
            activity.append(
                {
                    "activity_code": kind_code,
                    "activity_text": _t(locale, f"activity.{kind_code}", kind_code),
                    "title": _trim_text(row.get("title")),
                    "created_at": _safe_int(row.get("created_at")),
                }
            )
        return activity

    def _feedback_rows(self, *, limit: int) -> list[dict[str, Any]]:
        return self.engine.query_all(
            """
            SELECT
              f.feedback_id,
              f.knowledge_id,
              f.revision_id,
              f.feedback_type,
              f.feedback_payload,
              f.actor,
              f.runtime_id,
              f.agent_id,
              f.subagent_id,
              f.team_id,
              f.session_id,
              f.created_at,
              i.scope_type,
              i.scope_id
            FROM knowledge_feedback f
            LEFT JOIN knowledge_item i ON i.knowledge_id = f.knowledge_id
            ORDER BY f.created_at DESC, f.feedback_id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        )

    def _feedback_row(self, *, feedback_id: str) -> dict[str, Any] | None:
        return self.engine.query_one(
            """
            SELECT
              f.feedback_id,
              f.knowledge_id,
              f.revision_id,
              f.feedback_type,
              f.feedback_payload,
              f.actor,
              f.runtime_id,
              f.agent_id,
              f.subagent_id,
              f.team_id,
              f.session_id,
              f.created_at,
              i.scope_type,
              i.scope_id
            FROM knowledge_feedback f
            LEFT JOIN knowledge_item i ON i.knowledge_id = f.knowledge_id
            WHERE f.feedback_id=?
            """,
            (feedback_id,),
        )

    def _feedback_item(self, *, locale: str, row: dict[str, Any]) -> dict[str, Any]:
        payload = _safe_json(row.get("feedback_payload"))
        result_code = self._feedback_result_code(payload=payload)
        memory_ids = [str(item).strip() for item in _safe_list(payload.get("applied_memory_ids")) if str(item).strip()]
        memory_link_state_code = self._feedback_link_state(
            applied_memory_ids=memory_ids,
            memory_summary=payload.get("memory_summary"),
            memory_id=payload.get("memory_id"),
        )
        target_names = [
            value
            for value in (
                str(row.get("agent_id") or "").strip(),
                str(row.get("subagent_id") or "").strip(),
                str(row.get("scope_id") or "").strip(),
            )
            if value
        ]
        feedback_type = str(row.get("feedback_type") or "").strip() or "generic"
        created_at = _safe_int(row.get("created_at"))
        processed_at = self._feedback_processed_at(payload=payload)
        memory_summary = str(payload.get("memory_summary") or "").strip()
        if not memory_summary:
            if memory_link_state_code == "not_linked":
                memory_summary = _t(locale, "feedback.link.not_linked")
            elif memory_ids:
                memory_summary = ", ".join(memory_ids[:3])
            else:
                memory_summary = str(row.get("knowledge_id") or "")
        return {
            "feedback_id": str(row.get("feedback_id") or ""),
            "summary": self._feedback_summary(locale=locale, feedback_type=feedback_type),
            "sender_name": str(row.get("actor") or "").strip() or "system",
            "target_names": target_names,
            "memory_summary": _trim_text(memory_summary),
            "result_code": result_code,
            "result_text": _t(locale, f"feedback.result.{result_code}"),
            "memory_link_state_code": memory_link_state_code,
            "memory_link_state_text": _t(locale, f"feedback.link.{memory_link_state_code}"),
            "result_reason_text": self._feedback_reason(locale=locale, result_code=result_code),
            "created_at": created_at,
            "processed_at": processed_at,
            "applied_memory_ids": memory_ids,
            "timeline_items": self._feedback_timeline(
                locale=locale,
                created_at=created_at,
                processed_at=processed_at,
                result_code=result_code,
            ),
        }

    def _memory_rows(
        self,
        *,
        query: str | None,
        user_id: str | None,
        group_id: str | None,
        sender: str | None,
        target: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        sql = [
            """
            SELECT
              id,
              event_id,
              source_message_id,
              user_id,
              group_id,
              timestamp,
              role,
              sender,
              sender_name,
              group_name,
              episode,
              summary,
              subject,
              importance_score,
              scene_id,
              storage_tier,
              memory_category,
              is_deleted,
              created_at,
              updated_at
            FROM episodic_memory
            WHERE 1=1
            """
        ]
        if str(user_id or "").strip():
            sql.append("AND user_id=?")
            params.append(str(user_id).strip())
        if str(group_id or "").strip():
            sql.append("AND group_id=?")
            params.append(str(group_id).strip())
        if str(sender or "").strip():
            sql.append("AND (sender=? OR sender_name=?)")
            params.extend([str(sender).strip(), str(sender).strip()])
        if str(target or "").strip():
            sql.append("AND (user_id=? OR group_id=? OR group_name=?)")
            params.extend([str(target).strip(), str(target).strip(), str(target).strip()])
        if str(query or "").strip():
            like = f"%{str(query).strip()}%"
            sql.append(
                """
                AND (
                  summary LIKE ?
                  OR episode LIKE ?
                  OR subject LIKE ?
                  OR sender LIKE ?
                  OR sender_name LIKE ?
                  OR group_id LIKE ?
                  OR group_name LIKE ?
                )
                """
            )
            params.extend([like, like, like, like, like, like, like])
        sql.append("ORDER BY updated_at DESC, created_at DESC, id DESC LIMIT ?")
        params.append(max(1, min(200, int(limit))))
        return self.engine.query_all("\n".join(sql), tuple(params))

    def _memory_item(self, *, locale: str, row: dict[str, Any]) -> dict[str, Any]:
        summary = str(row.get("summary") or row.get("episode") or "").strip()
        sender_name = (
            str(row.get("sender_name") or "").strip()
            or str(row.get("sender") or "").strip()
            or str(row.get("user_id") or "").strip()
            or "system"
        )
        target_names = [
            value
            for value in (
                str(row.get("user_id") or "").strip(),
                str(row.get("group_name") or "").strip(),
                str(row.get("group_id") or "").strip(),
            )
            if value
        ]
        return {
            "memory_id": str(row.get("id") or ""),
            "summary": _trim_text(summary, limit=160),
            "sender_name": sender_name,
            "target_names": target_names,
            "source_code": self._memory_source_code(row=row),
            "source_text": self._memory_source_text(locale=locale, row=row),
            "share_scope_code": self._memory_share_scope_code(row=row),
            "share_scope_text": self._memory_share_scope_text(locale=locale, row=row),
            "status_code": self._memory_status_code(row=row),
            "status_text": self._memory_status_text(locale=locale, row=row),
            "updated_at": _safe_int(row.get("updated_at")) or _safe_int(row.get("timestamp")),
            "created_at": _safe_int(row.get("created_at")) or _safe_int(row.get("timestamp")),
            "importance_score": float(row.get("importance_score") or 0.0),
            "subject": str(row.get("subject") or "").strip(),
            "storage_tier": str(row.get("storage_tier") or "").strip(),
            "memory_category": str(row.get("memory_category") or "").strip(),
        }

    def _memory_feedback(
        self,
        *,
        locale: str,
        memory_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self._feedback_rows(limit=max(10, limit * 4)):
            item = self._feedback_item(locale=locale, row=row)
            if memory_id in item.get("applied_memory_ids", []) or str(memory_id) == str(
                _safe_json(row.get("feedback_payload")).get("memory_id") or ""
            ):
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def _memory_source_code(self, *, row: dict[str, Any]) -> str:
        event_id = str(row.get("event_id") or "").strip()
        source_message_id = str(row.get("source_message_id") or "").strip()
        storage_tier = str(row.get("storage_tier") or "").strip().lower()
        if event_id.startswith("live:") or source_message_id.startswith("live:"):
            return "live_chat"
        if storage_tier in {"graph", "hybrid"}:
            return "organized"
        return "conversation"

    def _memory_source_text(self, *, locale: str, row: dict[str, Any]) -> str:
        mapping = {
            "conversation": "对话" if locale == "zh-CN" else "Conversation",
            "organized": "自动整理" if locale == "zh-CN" else "Organized",
            "live_chat": "当前会话" if locale == "zh-CN" else "Current chat",
        }
        return mapping.get(self._memory_source_code(row=row), mapping["conversation"])

    def _memory_share_scope_code(self, *, row: dict[str, Any]) -> str:
        user_id = str(row.get("user_id") or "").strip()
        group_id = str(row.get("group_id") or "").strip()
        if group_id and user_id and group_id != f"default:{user_id}":
            return "team_shared"
        return "private"

    def _memory_share_scope_text(self, *, locale: str, row: dict[str, Any]) -> str:
        mapping = {
            "private": "仅自己" if locale == "zh-CN" else "Only this user",
            "team_shared": "团队共享" if locale == "zh-CN" else "Shared in group",
        }
        code = self._memory_share_scope_code(row=row)
        return mapping.get(code, mapping["private"])

    def _memory_status_code(self, *, row: dict[str, Any]) -> str:
        return "disabled" if int(row.get("is_deleted") or 0) else "remembered"

    def _memory_status_text(self, *, locale: str, row: dict[str, Any]) -> str:
        mapping = {
            "remembered": "已记住" if locale == "zh-CN" else "Remembered",
            "disabled": "已停用" if locale == "zh-CN" else "Disabled",
        }
        code = self._memory_status_code(row=row)
        return mapping.get(code, mapping["remembered"])

    def _chat_source_card(
        self,
        *,
        locale: str,
        row: dict[str, Any],
        used_in_answer: bool,
    ) -> dict[str, Any]:
        sender_name = (
            str(row.get("sender_name") or "").strip()
            or str(row.get("sender") or "").strip()
            or str(row.get("subject") or "").strip()
            or "system"
        )
        target_names = [
            value
            for value in (
                str(row.get("user_id") or "").strip(),
                str(row.get("group_id") or "").strip(),
                str(row.get("subject") or "").strip(),
            )
            if value
        ]
        group_code = "shared" if target_names and len(target_names) > 1 else "personal"
        return {
            "source_id": str(row.get("id") or row.get("event_id") or uuid.uuid4().hex),
            "title": _trim_text(
                row.get("citation_snippet") or row.get("summary") or row.get("episode"),
                limit=160,
            ),
            "summary": _trim_text(row.get("summary") or row.get("episode"), limit=160),
            "sender_name": sender_name,
            "target_name": " / ".join(target_names[:2]),
            "target_names": target_names,
            "source_code": str(row.get("source") or self._memory_source_code(row=row)),
            "source_text": self._memory_source_text(locale=locale, row=row),
            "share_scope_text": self._memory_share_scope_text(locale=locale, row=row),
            "used_in_answer": bool(used_in_answer),
            "match_score": float(row.get("citation_match_score") or row.get("score") or 0.0),
            "group_code": group_code,
            "group_text": _t(locale, f"chat.group.{group_code}"),
            "created_at": _safe_int(row.get("timestamp")),
        }

    def _chat_explain_cards(
        self,
        *,
        locale: str,
        citations: list[dict[str, Any]],
        retrieved: list[dict[str, Any]],
        chat_result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        if citations:
            cards.append(
                {
                    "reason_code": "used_memory",
                    "reason_text": (
                        f"本次回答参考了 {len(citations)} 条历史记忆。"
                        if locale == "zh-CN"
                        else f"This answer used {len(citations)} past memory items."
                    ),
                    "group_code": "final",
                    "group_text": _t(locale, "chat.group.final"),
                }
            )
        elif retrieved:
            cards.append(
                {
                    "reason_code": "hit_only",
                    "reason_text": (
                        f"系统找到了 {len(retrieved)} 条相关内容，但最终回答没有直接采用。"
                        if locale == "zh-CN"
                        else f"The system found {len(retrieved)} relevant items, but the final answer did not directly use them."
                    ),
                    "group_code": "hit_only",
                    "group_text": _t(locale, "chat.group.hit_only"),
                }
            )
        else:
            cards.append(
                {
                    "reason_code": "no_memory_used",
                    "reason_text": _t(locale, "chat.explain.no_memory"),
                    "group_code": "final",
                    "group_text": _t(locale, "chat.group.final"),
                }
            )
        live_count = int(
            (chat_result.get("memory_filter") or {}).get("live_segment_count") or 0
        )
        if live_count > 0:
            cards.append(
                {
                    "reason_code": "live_segment",
                    "reason_text": (
                        f"另外参考了当前会话中的 {live_count} 条最近片段。"
                        if locale == "zh-CN"
                        else f"It also checked {live_count} recent snippets from the current chat."
                    ),
                    "group_code": "personal",
                    "group_text": _t(locale, "chat.group.personal"),
                }
            )
        if bool(chat_result.get("boundary_detected")):
            cards.append(
                {
                    "reason_code": "memory_saved",
                    "reason_text": (
                        "这轮对话形成了新的本地记录。"
                        if locale == "zh-CN"
                        else "This turn created a new local note."
                    ),
                    "group_code": "shared",
                    "group_text": _t(locale, "chat.group.shared"),
                }
            )
        return cards

    def _group_explain_cards(
        self,
        *,
        locale: str,
        explain_cards: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for card in explain_cards:
            group_code = str(card.get("group_code") or "final")
            current = grouped.get(group_code)
            if current is None:
                grouped[group_code] = {
                    "group_code": group_code,
                    "group_text": str(card.get("group_text") or _t(locale, f"chat.group.{group_code}")),
                    "item_count": 1,
                }
                continue
            current["item_count"] = int(current.get("item_count") or 0) + 1
        return list(grouped.values())

    def _feedback_result_code(self, *, payload: dict[str, Any]) -> str:
        outcome_status = str(
            payload.get("outcome_status")
            or payload.get("result")
            or payload.get("status")
            or payload.get("decision")
            or ""
        ).strip().lower()
        if outcome_status in {"rolled_back", "rollback"}:
            return "rolled_back"
        if outcome_status in {"rejected", "ignored", "declined"}:
            return "rejected"
        if outcome_status in {"success", "accepted", "applied"}:
            return "remembered"
        return "pending"

    def _feedback_processed_at(self, *, payload: dict[str, Any]) -> int | None:
        for key in ("processed_at", "decided_at", "applied_at", "completed_at", "remembered_at"):
            parsed = _parse_timestamp(payload.get(key))
            if parsed:
                return parsed
        return None

    def _feedback_link_state(
        self,
        *,
        applied_memory_ids: list[Any],
        memory_summary: Any,
        memory_id: Any,
    ) -> str:
        if len(applied_memory_ids) > 1:
            return "multiple"
        if applied_memory_ids:
            return "linked"
        if str(memory_id or "").strip():
            return "linked"
        if str(memory_summary or "").strip():
            return "linked"
        return "not_linked"

    def _feedback_summary(self, *, locale: str, feedback_type: str) -> str:
        key = f"feedback.summary.{feedback_type}"
        if key in _LOCALE_TEXT.get(locale, {}):
            return _t(locale, key)
        return _t(locale, "feedback.summary.generic")

    def _feedback_reason(self, *, locale: str, result_code: str) -> str:
        mapping = {
            "remembered": "feedback.reason.success",
            "pending": "feedback.reason.pending",
            "rejected": "feedback.reason.rejected",
            "rolled_back": "feedback.reason.rolled_back",
        }
        return _t(locale, mapping.get(result_code, "feedback.reason.pending"))

    def _feedback_timeline(
        self,
        *,
        locale: str,
        created_at: int | None,
        processed_at: int | None,
        result_code: str,
    ) -> list[dict[str, Any]]:
        items = []
        if created_at:
            items.append(
                {
                    "event_code": "created",
                    "event_text": _t(locale, "activity.feedback_created"),
                    "created_at": created_at,
                }
            )
        if processed_at:
            items.append(
                {
                    "event_code": result_code,
                    "event_text": _t(locale, f"feedback.result.{result_code}"),
                    "created_at": processed_at,
                }
            )
        return items
