# Personal Knowledge Agent 架构合同

## 1. 系统位置

本项目是 DeerFlow 2.0 之上的个人知识生命周期系统。当前 DeerFlow 真实默认服务路径是 Gateway embedded runtime：根目录 `Makefile` 的 `make dev` 调用 `scripts/serve.sh --dev`，后端 `backend/Makefile` 的 `make dev` 启动 `uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --reload`。

`backend/langgraph.json` 注册 `lead_agent: deerflow.agents:make_lead_agent`，用于 LangGraph tooling、Studio 或直接 LangGraph Server 兼容；它不是当前脚本和 Docker 部署的默认服务入口。

## 2. 总体架构

```text
┌─────────────────────────────────────────────┐
│                DeerFlow Frontend            │
│ Import / Library / Ask / Graph / Workflow   │
│ Approval / Artifact / Activity              │
└──────────────────────┬──────────────────────┘
                       │ Gateway API / SSE
┌──────────────────────▼──────────────────────┐
│             DeerFlow Agent Layer            │
│ Lead Agent                                  │
│ Skill: personal-knowledge-workflow          │
│ Custom Subagents                            │
│ Knowledge / Workflow Built-in Tools         │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│        Personal Knowledge Domain Layer      │
│ Ingestion Service                           │
│ Knowledge Extraction Service                │
│ Retrieval Service                           │
│ Evidence & Citation Service                 │
│ Conflict / Revision Service                 │
│ Workflow Service                            │
│ Approval & Action Service                   │
│ Artifact Validation Service                 │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│            Persistence & Indexes            │
│ PostgreSQL                                  │
│ pgvector                                    │
│ PostgreSQL Full-Text Search                 │
│ Entity / Claim / Relation Tables            │
│ DeerFlow User-scoped File Storage           │
└─────────────────────────────────────────────┘
```

## 3. 与 DeerFlow 当前实现的接入位置

### Gateway 和 runtime

当前 Gateway 入口是 `backend/app/gateway/app.py`，运行期依赖初始化在 `backend/app/gateway/deps.py`。`langgraph_runtime()` 初始化 StreamBridge、Persistence Engine、Checkpointer、Store、Run Store、Thread Store、Run Event Store 和 RunManager。

本项目后续 Gateway API 与后台任务应接入 Gateway 层，但不能绕过 `AuthMiddleware`、`CSRFMiddleware`、`require_permission()` 和 Thread/User owner isolation。

### Lead Agent

Lead Agent 入口是 `backend/packages/harness/deerflow/agents/lead_agent/agent.py` 的 `make_lead_agent()`。它负责解析 runtime context、选择模型、加载 custom agent config、聚合 tools、组装 deferred tool setup、构建 middleware，并调用 LangChain `create_agent()`。

主 Prompt 在 `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`。后续不应把所有产品规则硬编码进 `SYSTEM_PROMPT_TEMPLATE`。产品逻辑优先进入 Domain Layer，Agent 只通过 Skill、Tools、Subagents 和有限 prompt policy 使用这些能力。

### Tool 注册与聚合

Tool 聚合入口是 `backend/packages/harness/deerflow/tools/tools.py` 的 `get_available_tools()`。它从 `config.yaml` 的 `tools` 配置加载反射路径，加入 built-in tools、可选 subagent `task`、可选 vision `view_image`、MCP tools 和 ACP tools，并按 tool name 去重。

Knowledge、Workflow、Approval、Validation Tools 后续应作为 Agent 接口接入这一层，但 Tool 层不承担全部领域逻辑。真正业务逻辑必须位于 Domain Service。

### Skill

Skill 加载入口是 `backend/packages/harness/deerflow/skills/storage/local_skill_storage.py`。当前布局为：

```text
skills/public/<name>/SKILL.md
skills/custom/<name>/SKILL.md
```

存储实现递归扫描 `SKILL.md`，并区分 public 内置只读与 custom 可编辑技能。后续计划目录：

```text
skills/public/personal-knowledge-workflow/
├── SKILL.md
├── knowledge_workflow_guide.md
├── evidence_policy.md
├── approval_policy.md
└── artifact_templates/
```

本轮不创建该 Skill。

### Custom Subagents

Subagent 配置在 `backend/packages/harness/deerflow/config/subagents_config.py`，注册解析在 `backend/packages/harness/deerflow/subagents/registry.py`。当前支持 built-in `general-purpose`、`bash` 和 `config.yaml` 的 `subagents.custom_agents`。

固定四个项目子智能体：

- 知识整理子智能体（Knowledge Curator）
- 知识研究子智能体（Knowledge Researcher）
- 冲突审计子智能体（Contradiction Auditor）
- 工作流执行子智能体（Workflow Operator）

本轮不创建这些 Subagent。

### Upload、Artifact、Workspace 和身份隔离

上传路由在 `backend/app/gateway/routers/uploads.py`，共享业务逻辑在 `backend/packages/harness/deerflow/uploads/manager.py`。Artifact 路由在 `backend/app/gateway/routers/artifacts.py`，`present_files` 工具在 `backend/packages/harness/deerflow/tools/builtins/present_file_tool.py`。

用户隔离文件路径由 `backend/packages/harness/deerflow/config/paths.py` 定义。线程数据在用户 bucket 下包含：

```text
user-data/workspace
user-data/uploads
user-data/outputs
acp-workspace
```

后续原始上传文件、Source Snapshot、解析中间文件和生成 Artifact 文件可复用 DeerFlow 用户隔离文件系统。权威知识元数据和索引不能只存在于 thread outputs。

### Memory 的真实定位

DeerFlow Memory 在 `backend/packages/harness/deerflow/agents/memory/`，默认 `FileMemoryStorage` 保存 JSON 结构，包括用户上下文、历史摘要和 facts，并可注入 Prompt。

Memory 不是权威知识库，不能承载 Source、Revision、Chunk、Entity、Claim、Relation、EvidenceSpan 的一致性要求。个人知识系统必须新增独立 Knowledge Persistence。

### Checkpointer、Store、Run Store、Event Store

Checkpointer 入口是 `backend/packages/harness/deerflow/runtime/checkpointer/async_provider.py`，支持 memory、sqlite、postgres。Gateway `langgraph_runtime()` 还初始化：

- Store：LangGraph store；
- Run Store：run 元数据持久化；
- Thread Store：线程元数据和 owner isolation；
- Run Event Store：运行事件与 token usage；
- StreamBridge：运行事件到 SSE；
- RunManager：运行生命周期管理。

这些能力服务于 DeerFlow runtime 和会话运行状态，不等同于项目知识库。

### Frontend

前端入口为 `frontend/src/app/page.tsx`，workspace 入口为 `frontend/src/app/workspace/page.tsx`。Artifact、uploads、threads、skills、MCP、memory 等前端核心逻辑位于 `frontend/src/core/` 和 `frontend/src/components/workspace/`。

后续产品前端应复用 Workspace、Artifact preview、thread/run streaming 基础，但本轮不修改前端。

## 4. 存储合同

存储方案固定为：

- PostgreSQL
- pgvector
- SQLAlchemy 2
- Alembic
- PostgreSQL Full-Text Search
- DeerFlow 用户隔离文件存储

### PostgreSQL 保存

- Source
- SourceSnapshot
- DocumentRevision
- Chunk metadata
- Entity
- Claim
- Relation
- EvidenceSpan
- Artifact metadata
- WorkflowRun
- ApprovalRequest
- ActionExecution
- AuditLog

### pgvector 保存

- Chunk embeddings
- Entity embeddings
- Claim embeddings

### PostgreSQL Full-Text Search 保存或索引

- Chunk content
- Source title 和 metadata 中可检索字段
- Claim text
- Entity canonical name 和 aliases

### DeerFlow 用户隔离文件系统保存

- 原始上传文件；
- Source Snapshot；
- 解析中间文件；
- 生成的 Artifact 文件。

## 5. 确定性代码与 LLM 边界

### 必须由确定性代码负责

- 文件解析；
- hash；
- canonical source identity；
- 去重；
- Revision 创建；
- Chunking；
- 索引；
- workspace isolation；
- 权限检查；
- Retrieval fusion；
- Evidence offset validation；
- Approval state machine；
- 幂等控制；
- Artifact stale marking；
- Schema validation；
- 审计日志；
- Connector 执行结果确认。

### 可以由 LLM 负责

- Entity 提取；
- Claim 提取；
- Relation 提取；
- Query understanding；
- 复杂检索规划；
- LLM reranking；
- 冲突解释；
- 多来源综合；
- Artifact 写作；
- 工作流建议。

### LLM 不能决定

- 用户是否有权限；
- 动作是否真正获得批准；
- 哪个 Revision 是最新版本；
- 两个内容 hash 是否相同；
- 动作是否真正执行成功；
- 数据是否应当被物理删除。

Prompt 不能承担权限、审批、幂等和一致性保证。

## 6. DeerFlow 接入合同

### Knowledge Tools

```text
knowledge_ingest
knowledge_ingestion_status
knowledge_search
knowledge_get_source
knowledge_get_revision
knowledge_get_claims
knowledge_expand_graph
knowledge_compare_revisions
knowledge_find_conflicts
knowledge_generate_update_report
```

### Workflow Tools

```text
workflow_create
workflow_get
workflow_advance
workflow_generate_artifact
```

### Approval / Action Tools

```text
approval_request
approval_get
approval_decide
action_preview
action_execute
```

### Validation Tools

```text
knowledge_artifact_validate
knowledge_provenance_validate
workflow_validate
approval_validate
```

`action_execute` 必须在服务端再次检查 Approval。所有外部副作用操作需要幂等键（idempotency key）。不能只依赖 Agent Prompt。Tool 层只作为 Agent 接口，不承担全部领域逻辑。真正业务逻辑应位于 Domain Service。

## 7. 约束与不变量

- 不绕过 `Paths`、user context、authz 或 permission checks。
- DeerFlow Memory 不能作为权威知识库。
- thread outputs 不能作为权威数据库。
- 不直接在主 `SYSTEM_PROMPT_TEMPLATE` 中硬编码所有产品逻辑。
- 领域逻辑优先进入独立 Domain Layer。
- Artifact 必须能追溯到证据、Revision 和生成输入。
- 外部动作必须经过审批、服务端复核和审计日志。

## 8. 当前仅完成的内容

当前仅完成基线验证与设计合同落库。未实现数据库模型、迁移、API、Tool、Skill、Subagent、前端业务代码或部署配置。
