# MiniMem 作为 OpenClaw 多智能体语义通信中枢方案（简版）

## 1. 可行性结论

结论：**可行，且可先用“配置优先”方式落地**。

当前仓库已经具备通信中枢的核心能力：

1. OpenClaw 插件支持自动注入与自动回写（`before_agent_start` / `agent_end`）。
2. 支持 `groupStrategy`（`shared` / `per_role` / `per_user`）进行多智能体隔离与共享切换。
3. 检索支持 `keyword/vector/hybrid/rrf/agentic`，可做语义级路由与证据回溯。
4. MCP 桥已经暴露 `search_memories / write_memory / chat_with_memory / graph_*`，可跨 Agent 复用。

这意味着：OpenClaw 各 Agent 可以把 MiniMem 当作“语义消息总线 + 共享记忆层”。

## 2. 配置方案（先跑起来）

目标：先实现“共享语义上下文 + 每个 Agent 可追溯读写”。

### 2.1 推荐拓扑

1. 一个 MiniMem 服务实例（中心）。
2. 一个 OpenClaw memory 插件实例（默认 `shared` 组）。
3. 每个 Agent 写入时带 `sender`，统一落到同一共享 `group_id`。
4. 关键场景下手动指定 `group_id` 进行子主题分流（如 `hub:research`、`hub:ops`）。

### 2.2 OpenClaw 插件建议配置

```json
{
  "plugins": {
    "slots": { "memory": "minimem-memory" },
    "entries": {
      "minimem-memory": {
        "enabled": true,
        "config": {
          "baseUrl": "http://127.0.0.1:20195",
          "groupStrategy": "shared",
          "sharedGroupId": "shared:openclaw-hub",
          "defaultRetrieveMethod": "agentic",
          "defaultDecisionMode": "rule",
          "defaultTopK": 8,
          "autoInjectOnStart": true,
          "autoCaptureOnEnd": true,
          "autoCaptureCompression": true,
          "autoSenderFromAgent": true
        }
      }
    }
  }
}
```

### 2.3 运行约定（必须）

1. `sender` 统一命名：`planner` / `coder` / `reviewer` / `executor`。
2. `group_id` 统一规范：`shared:openclaw-hub`（主总线）+ 可选子主题组。
3. 只把“可复用结论”写入共享组，过程噪声写入私有组（避免污染召回）。
4. 每次检索都要求 `context_for_agent` 注入并显示引用来源（可审计）。

## 3. MiniMem 演进方案（分阶段）

## Phase A（配置与流程，1-2 天）

不改代码，直接上线：

1. 按上面的 `shared` 配置跑通多 Agent 协作链路。
2. 给每个 Agent 增加写入规则：只写“决策、结论、约束、待办”。
3. 建立组路由约定：主组共享、子组分域、敏感信息私有组。

交付物：可运行的语义通信闭环（读-写-追溯）。

## Phase B（轻量增强，3-5 天）

在 MiniMem 记忆模型上加轻量结构化字段：

1. `channel`（如 `plan/execute/review`）
2. `intent`（如 `question/decision/action/risk`）
3. `task_id` / `thread_id`
4. `confidence`（写入方自评）
5. `ttl_sec`（短期协作消息自动衰减）

并在检索接口增加这些字段的可选过滤。

收益：降低跨 Agent 召回噪声，提升“对当前任务有用”的召回占比。

## Phase C（语义通信中枢化，1-2 周）

新增“中枢能力”：

1. 订阅式读取：按 `channel + group_id + task_id` 拉取增量消息。
2. 去重与冲突收敛：同义结论折叠，冲突保留并标注来源。
3. 重要消息升级：高置信度决策自动进入 `profile/knowledge` 层。
4. 图谱增强：将 Agent 间“结论依赖关系”写入图谱，支持追因。

收益：从“记忆库”升级为“语义协作总线”。

## 4. 风险与控制

1. 噪声污染：强制写入准入规则（只写结论，不写全部中间推理）。
2. 召回串话：共享组外，按子组/任务组隔离。
3. 性能抖动：保留 `rule` 决策模式兜底，`agentic` 只用于关键检索。
4. 可解释性不足：强制展示引用片段与来源（sender/group/source）。

## 5. 验证指标（建议）

1. 协作任务成功率（端到端）。
2. Recall@K（命中“其他 Agent 已产出关键信息”的比例）。
3. Top-K 噪声率（无关记忆占比）。
4. 平均检索时延（P50/P95）。
5. 引用可追溯率（答案中可定位到 memory 的比例）。

---

这个方案的核心原则是：**先用现有能力跑通，再做小步结构化增强，最后再中枢化**。这样复杂度最低，且每一步都可验证回报。
