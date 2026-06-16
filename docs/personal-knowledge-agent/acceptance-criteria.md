# Personal Knowledge Agent 验收标准

## 1. 验收位置

本文件定义最终成品的可验证验收标准。当前仓库本轮只完成设计合同落库，以下条目不是当前已实现状态。

## 2. 可验证验收条目

### AC-01 多来源摄取

Given 用户拥有一个 workspace，When 用户上传 PDF、DOCX、PPTX、XLSX、Markdown、TXT、HTML 或提交网页 URL，Then 系统创建摄取任务并记录来源类型、状态和错误。

验证方式：后端集成测试覆盖每种来源；前端人工验证 Import 流程。

### AC-02 内容指纹、去重、Snapshot 和 Revision

Given 同一来源被重复摄取或内容发生变化，When ingestion pipeline 运行，Then 系统计算 content hash，识别重复或新版本，并创建 SourceSnapshot 和 DocumentRevision。

验证方式：确定性单元测试验证 hash、canonical URI、重复检测和 revision_number。

### AC-03 独立 PostgreSQL + pgvector 知识持久化

Given 系统写入知识对象，When 查询数据库，Then Source、Revision、Chunk、Entity、Claim、Relation、EvidenceSpan、Workflow 和 Approval 数据存在于 PostgreSQL，embedding 存入 pgvector。

验证方式：迁移测试、repository 测试、数据库约束测试。

### AC-04 结构化知识对象

Given 一个成功解析的 DocumentRevision，When extraction run 完成，Then 系统生成 Chunk、Entity、Claim、Relation 和 EvidenceSpan。

验证方式：抽取集成测试验证对象数量、关系完整性和 schema。

### AC-05 多模式检索

Given 用户提出问题，When knowledge_search 执行，Then 支持 Keyword Retrieval、Vector Retrieval、Metadata Retrieval 和 Graph Retrieval。

验证方式：检索单元测试分别固定每类 retriever 的输入和输出。

### AC-06 RRF、父子索引和重排序

Given 多个 retriever 返回候选结果，When retrieval service 融合结果，Then 使用 Reciprocal Rank Fusion（RRF）、Parent-Child Indexing 和 Reranking 生成 Evidence Context Pack。

验证方式：排序 golden test、父子上下文扩展测试、reranking mock 测试。

### AC-07 核心事实和结论可追溯

Given 系统生成分析产物，When 用户查看任一核心事实或结论，Then 可以追溯到 Source、DocumentRevision、Chunk、Claim 和 EvidenceSpan。

验证方式：ArtifactEvidenceLink 测试和人工点击证据验证。

### AC-08 区分事实、归纳、推断、冲突和证据不足

Given Evidence Context Pack 包含支持、冲突和缺口，When 生成 Artifact，Then Artifact 明确区分来源支持的事实、跨来源归纳、Agent 推断、冲突和证据不足内容。

验证方式：Artifact validation test 和人工阅读验收。

### AC-09 冲突识别和版本变化分析

Given 新 Revision 与旧 Revision 或其他来源 Claim 不一致，When conflict/revision service 运行，Then 系统创建或更新 ConflictGroup，并输出变化分析。

验证方式：冲突 fixture 测试、revision diff 测试。

### AC-10 Incremental Update

Given 只有部分 Chunk 发生变化，When 新 Revision 进入系统，Then 只重新处理受影响部分，并保留未受影响知识。

验证方式：增量更新测试验证重处理范围和未变对象稳定性。

### AC-11 Artifact Staleness Detection

Given Artifact 依赖的 Revision、Claim 或 EvidenceSpan 发生变化，When invalidation service 运行，Then 受影响 Artifact 被标记 stale，并生成 Knowledge Update Report。

验证方式：ArtifactEvidenceLink 失效测试。

### AC-12 结构化 WorkflowRun

Given 用户请求一个工作流，When workflow_create 执行，Then 系统创建 WorkflowRun，记录 input、status、current_step 和 result_artifact_ids。

验证方式：Workflow service 单元测试和 API 集成测试。

### AC-13 外部写操作必须经过 Approval

Given 工作流准备发送邮件、创建日程或写入外部系统，When 尚未获得审批，Then 系统只生成 ApprovalRequest 和 action preview，不执行外部动作。

验证方式：未审批 action_execute 拒绝测试。

### AC-14 服务端强制校验 Approval

Given Agent 声称用户已经批准，When 服务端 ApprovalRequest 状态不是 APPROVED，Then action_execute 必须拒绝执行。

验证方式：服务端权限和状态机测试。

### AC-15 外部动作 idempotency

Given 同一个 idempotency_key 被重复提交，When action_execute 重试，Then 系统不会重复产生外部副作用，并返回原执行结果或幂等状态。

验证方式：connector mock 重放测试。

### AC-16 真实 Artifact

Given workflow_generate_artifact 完成，When 用户打开 Artifact，Then 文件存在于 DeerFlow 用户隔离 outputs 或指定存储路径，metadata 存在于 PostgreSQL，并可下载或预览。

验证方式：Artifact API 测试和前端预览测试。

### AC-17 完整前端工作台

Given 用户登录前端，When 进入 workspace，Then 可以访问 Import、Library、Ask、Graph、Workflow、Approval、Artifact 和 Activity。

验证方式：Playwright E2E 和人工验收。

### AC-18 遵循 DeerFlow 用户和 Workspace 隔离

Given 用户 A 与用户 B 存在不同 workspace，When 用户 A 猜测用户 B 的 thread、source、artifact 或 workflow id，Then 服务端返回拒绝或 not found，且不泄露数据。

验证方式：owner isolation 安全测试。

### AC-19 确定性单元测试

Given 不依赖真实 LLM 或外部服务，When 运行单元测试，Then hash、dedup、revision、chunking、retrieval fusion、approval state machine、idempotency 和 validation 全部可重复通过。

验证方式：后端 unit test。

### AC-20 集成测试

Given 本地测试数据库和文件系统，When 运行集成测试，Then 摄取到检索、分析、Artifact、Workflow 和 Approval 的关键路径通过。

验证方式：后端 integration test。

### AC-21 安全测试

Given 恶意输入、路径穿越、跨用户 id、伪造 approval 和重复执行请求，When 服务端处理，Then 权限、路径、状态机、幂等和审计边界保持有效。

验证方式：security test suite。

### AC-22 真实模型 Live E2E

Given 配置了真实模型和必要外部服务，When 运行 Live E2E smoke test，Then 至少完成一个从摄取到证据产物再到审批草稿的真实模型流程。

验证方式：带显式环境变量开关的 live e2e；缺少密钥时标记 skipped 而不是失败。

### AC-23 全栈部署

Given 生产或 Docker 配置完成，When 启动全栈服务，Then Gateway、Frontend、PostgreSQL、pgvector、worker 和文件存储都可用。

验证方式：部署 smoke test、health check、基础 workflow 测试。

### AC-24 完整文档和演示

Given 新用户或维护者阅读文档，When 按 README 和项目说明操作，Then 能理解架构、运行命令、核心闭环、演示数据和部署方式。

验证方式：文档命令验证、demo data 验证、人工走查。
