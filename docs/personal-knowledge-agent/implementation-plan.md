# Personal Knowledge Agent 实施顺序

## 0. 仓库基线与施工规则

目标：确认 DeerFlow 2.0 当前真实基线、扩展点、命令和测试状态。

新增模块：无。

主要文件或目录建议：`docs/personal-knowledge-agent/`。

输入：当前仓库、Git 状态、官方 Makefile、后端/前端入口、测试命令。

输出：基线记录、施工约束、已验证扩展点。

前置依赖：无。

完成条件：记录 Git commit、remote、真实入口、官方命令和当前测试结果。

重点测试：`make help`、`make doctor`、`make check`、后端 lint/test、前端命令可用性检查。

不允许做的事情：不创建配置、不读取 secret、不实现业务代码、不修改非文档文件。

本轮基线结果：

- `git status --short --branch`：`## main...upstream/main`
- `git status --porcelain=v1 --untracked-files=all`：初始为空。
- `git rev-parse HEAD`：`d2cc991d55b05421885923c1791273daec270005`
- `git describe --tags --always --dirty`：`v2.0.0-rc0-1-gd2cc991d`
- `git remote -v`：`upstream https://github.com/bytedance/deer-flow.git`
- `git log -1`：`2026-06-15 17:59:25 +0800`，`make ai follow-up suggestions optional (#3591)`
- `make help`：通过。
- `make check`：失败，缺少 `pnpm` 和 `nginx`；Node.js 25.9.0 和 uv 0.11.17 可用。
- `make doctor`：第一次因 uv cache 沙箱权限失败；提权后运行，创建后端 `.venv`，诊断为缺 `pnpm`、`nginx`、`.env`、`frontend/.env`、`config.yaml`。
- `cd backend && make lint`：通过，`ruff check` 和 `ruff format --check` 均通过。
- `cd backend && make test`：第一次因 uv cache 沙箱权限失败；提权后完整运行，结果 `1 failed, 4441 passed, 16 skipped, 11 warnings in 181.39s`。唯一失败为 `tests/test_gateway_lifespan_shutdown.py::test_shutdown_is_bounded_when_channel_stop_hangs`，实际 7.04s，期望小于 7.0s。
- 前端 `pnpm lint/typecheck/build/test`：未运行，因为 `pnpm` 不存在，且本轮禁止安装依赖。

## 1. 产品合同和设计文档

目标：把已确定产品合同、架构、领域模型、施工顺序和验收标准落库。

新增模块：文档。

主要文件或目录建议：

```text
docs/personal-knowledge-agent/
```

输入：已确定产品合同、当前 DeerFlow 2.0 扩展点核实结果。

输出：`product-contract.md`、`architecture.md`、`domain-model.md`、`implementation-plan.md`、`acceptance-criteria.md`。

前置依赖：Step 0。

完成条件：五份文档存在，内容区分 DeerFlow 已有能力、本项目新增能力和未实现内容。

重点测试：`find docs/personal-knowledge-agent -maxdepth 1 -type f -print | sort`、`git diff --check`、`git diff --stat`、`git diff -- docs/personal-knowledge-agent`。

不允许做的事情：不写业务代码、不创建 Skill、不创建 Subagent、不修改 Prompt、不修改 API。

## 2. Knowledge Persistence

目标：建立权威知识持久化层。

新增模块：SQLAlchemy 2 models、repositories、Alembic migrations、pgvector support。

主要文件或目录建议：

```text
backend/packages/harness/deerflow/personal_knowledge/
backend/packages/harness/deerflow/personal_knowledge/persistence/
backend/tests/test_personal_knowledge_*.py
```

输入：Domain Model。

输出：PostgreSQL 表、pgvector 字段、repository 接口、迁移。

前置依赖：Step 1。

完成条件：Source、Snapshot、Revision、Chunk metadata、Entity、Claim、Relation、EvidenceSpan、Artifact metadata、WorkflowRun、ApprovalRequest、ActionExecution、AuditLog 可持久化。

重点测试：repository 单元测试、迁移测试、用户隔离测试、约束测试。

不允许做的事情：不把 Memory JSON 当知识库；不把 outputs 当数据库。

## 3. Ingestion Pipeline

目标：把多种来源转为 SourceSnapshot、DocumentRevision、Parsed Content 和 Chunk。

新增模块：ingestion service、parser adapters、hash/canonical URI、dedup/version service、job status。

主要文件或目录建议：

```text
backend/packages/harness/deerflow/personal_knowledge/ingestion/
backend/packages/harness/deerflow/personal_knowledge/parsers/
```

输入：上传文件、URL、Markdown、TXT、HTML、后续 connector data。

输出：Source、SourceSnapshot、DocumentRevision、Chunk。

前置依赖：Step 2。

完成条件：支持内容指纹、重复检测、Snapshot、Revision、parser_version、parse_status、index_status。

重点测试：文件类型解析、hash 稳定性、重复来源、新版本、解析失败。

不允许做的事情：不让 LLM 判断 hash 或 Revision 最新性。

## 4. Structured Knowledge Extraction

目标：从 Chunk 中抽取 Entity、Claim、Relation、EvidenceSpan。

新增模块：extraction service、LLM extraction adapters、schema validation、evidence offset validation。

主要文件或目录建议：

```text
backend/packages/harness/deerflow/personal_knowledge/extraction/
```

输入：DocumentRevision 和 Chunk。

输出：Entity、Claim、Relation、EvidenceSpan、ExtractionRun。

前置依赖：Step 3。

完成条件：Claim 不被当作真理；所有 Claim/Relation 有 EvidenceSpan；抽取结果可审计和重跑。

重点测试：schema validation、offset validation、无证据拒绝、LLM 输出异常。

不允许做的事情：不让 LLM 绕过证据校验。

## 5. Hybrid Retrieval Engine

目标：实现固定检索链路。

新增模块：retrieval service、keyword retriever、vector retriever、graph/entity/claim retriever、RRF、parent context expansion、reranking、Evidence Context Pack。

主要文件或目录建议：

```text
backend/packages/harness/deerflow/personal_knowledge/retrieval/
```

输入：用户问题、metadata filter、workspace_id。

输出：Evidence Context Pack。

前置依赖：Step 4。

完成条件：支持 Keyword Retrieval、Vector Retrieval、Metadata Filtering、Entity/Claim Retrieval、RRF、Parent-Child Indexing、Reranking。

重点测试：融合排序、权限过滤、证据包完整性、空结果、冲突结果。

不允许做的事情：不返回跨用户数据；不让 Prompt 自行拼接未验证证据包。

## 6. Evidence-grounded Analysis

目标：基于 Evidence Context Pack 生成可追溯分析产物。

新增模块：analysis service、citation service、artifact writer、provenance validator。

主要文件或目录建议：

```text
backend/packages/harness/deerflow/personal_knowledge/analysis/
backend/packages/harness/deerflow/personal_knowledge/artifacts/
```

输入：Evidence Context Pack、workflow input。

输出：Topic Dossier、Decision Memo、Email Draft 等 Artifact。

前置依赖：Step 5。

完成条件：产物区分事实、归纳、推断、冲突、未解决问题和证据不足内容。

重点测试：引用完整性、证据不足标记、ArtifactEvidenceLink、validation_status。

不允许做的事情：不生成没有证据链的核心事实结论。

## 7. Conflict / Revision / Incremental Update

目标：支持版本变化、冲突识别、增量更新和 Artifact stale marking。

新增模块：revision diff service、conflict service、invalidation service、update report generator。

主要文件或目录建议：

```text
backend/packages/harness/deerflow/personal_knowledge/update/
```

输入：新 SourceSnapshot、新 DocumentRevision。

输出：受影响 Chunk、更新后的 Entity/Claim/Relation、ConflictGroup、stale Artifact、Knowledge Update Report。

前置依赖：Step 6。

完成条件：支持 Incremental Update、Invalidation、Artifact Staleness Detection。

重点测试：新版本 diff、Claim 失效、冲突组、Artifact stale。

不允许做的事情：不全量重建替代增量语义；不隐藏冲突。

## 8. Workflow Domain Layer

目标：建立结构化 WorkflowRun 和工作流推进服务。

新增模块：workflow service、workflow templates、state transition validation。

主要文件或目录建议：

```text
backend/packages/harness/deerflow/personal_knowledge/workflows/
```

输入：用户目标、检索结果、Artifact 请求。

输出：WorkflowRun、current_step、result_artifact_ids。

前置依赖：Step 6。

完成条件：WorkflowRun 可创建、推进、失败、完成并保留审计。

重点测试：状态机、重复推进、失败恢复、权限隔离。

不允许做的事情：不让 LLM 直接改状态。

## 9. Approval and Action Execution

目标：所有外部副作用动作经过审批、幂等和审计。

新增模块：approval service、action service、connector adapters、idempotency control、audit log writer。

主要文件或目录建议：

```text
backend/packages/harness/deerflow/personal_knowledge/approval/
backend/packages/harness/deerflow/personal_knowledge/actions/
```

输入：WorkflowRun、action_preview、用户审批。

输出：ApprovalRequest、ActionExecution、AuditLog。

前置依赖：Step 8。

完成条件：`action_execute` 服务端复核 Approval；外部动作支持 idempotency。

重点测试：未批准拒绝、重复执行幂等、connector 失败、审计日志。

不允许做的事情：不经审批执行外部写操作。

## 10. DeerFlow Skill / Tools / Subagents

目标：把领域服务通过 DeerFlow Agent Layer 暴露给 Lead Agent。

新增模块：Skill、Knowledge Tools、Workflow Tools、Approval/Action Tools、Validation Tools、四个 Custom Subagents 配置。

主要文件或目录建议：

```text
skills/public/personal-knowledge-workflow/
backend/packages/harness/deerflow/personal_knowledge/tools/
```

输入：Domain Services。

输出：Agent 可调用工具和技能说明。

前置依赖：Step 9。

完成条件：Tool 只调用 Domain Service；Prompt 不承担权限和一致性。

重点测试：tool args schema、权限、审批复核、Skill frontmatter、Subagent 配置。

不允许做的事情：不在 Tool 内复制全部领域逻辑。

## 11. Gateway API and Background Jobs

目标：提供前端和异步任务所需 API。

新增模块：Gateway routers、job endpoints、SSE events、background worker hooks。

主要文件或目录建议：

```text
backend/app/gateway/routers/personal_knowledge.py
```

输入：前端请求、上传文件、workflow 操作。

输出：API response、job status、stream events。

前置依赖：Step 10。

完成条件：API 使用 auth middleware、CSRF、require_permission、owner isolation。

重点测试：OpenAPI schema、authz、owner isolation、job status、错误处理。

不允许做的事情：不创建绕过 Gateway auth 的私有入口。

## 12. Product Frontend

目标：实现 Import / Library / Ask / Graph / Workflow / Approval / Artifact / Activity 工作台。

新增模块：frontend pages、components、core API clients、state hooks。

主要文件或目录建议：

```text
frontend/src/app/workspace/
frontend/src/core/personal-knowledge/
frontend/src/components/workspace/
```

输入：Gateway API。

输出：完整前端工作台。

前置依赖：Step 11。

完成条件：用户可摄取、检索、查看证据、生成 Artifact、审批动作、查看活动。

重点测试：unit、Playwright、Artifact preview、approval flow。

不允许做的事情：不在前端绕过服务端审批。

## 13. Security / Permission / Audit Review

目标：审查权限、隔离、审批、connector、审计和数据删除边界。

新增模块：安全测试、审计报告、威胁模型文档。

主要文件或目录建议：

```text
backend/tests/test_personal_knowledge_security.py
docs/personal-knowledge-agent/security-review.md
```

输入：已实现后端、前端、工具、连接器。

输出：安全评审结论和测试。

前置依赖：Step 12。

完成条件：无跨用户读取、无未审批副作用、无未审计执行。

重点测试：权限绕过、ID 猜测、路径穿越、重复执行、恶意 LLM 输出。

不允许做的事情：不接受仅靠 Prompt 的安全保证。

## 14. Evaluation and Test System

目标：建立确定性、集成、安全和真实模型 Live E2E 测试体系。

新增模块：fixtures、golden tests、retrieval eval、live e2e smoke tests。

主要文件或目录建议：

```text
backend/tests/personal_knowledge/
frontend/tests/e2e/
```

输入：测试数据、模型配置、可选外部服务。

输出：可重复测试和 Live E2E 报告。

前置依赖：Step 13。

完成条件：覆盖摄取、抽取、检索、分析、审批、行动、更新。

重点测试：deterministic unit、integration、security、real model live e2e。

不允许做的事情：不把 Live E2E 作为唯一正确性证明。

## 15. Documentation / Demo / Deployment

目标：完善 README、架构图、演示数据、部署说明和操作手册。

新增模块：用户文档、开发文档、部署文档、demo fixtures。

主要文件或目录建议：

```text
docs/personal-knowledge-agent/
frontend/public/demo/
```

输入：完整产品实现和测试结果。

输出：可交付文档、演示数据和部署说明。

前置依赖：Step 14。

完成条件：全栈部署可运行；用户能按文档完成核心闭环。

重点测试：文档命令验证、demo data 验证、部署 smoke test。

不允许做的事情：不把未实现能力写成已完成。
