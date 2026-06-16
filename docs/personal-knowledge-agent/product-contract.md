# Personal Knowledge Agent 产品合同

## 1. 系统位置

个人知识智能体（Personal Knowledge Agent）建立在 DeerFlow 2.0 之上。DeerFlow 当前已经提供 Gateway embedded runtime、Lead Agent、Tool 聚合、Skill 加载、Subagent、Memory、Sandbox、Upload、Artifact、身份认证和用户隔离文件存储。本项目在这些能力之上新增独立的个人知识生命周期系统。

本项目的产品边界已经确定。本文件是后续实现、测试、评审和验收的合同，不是路线探索文档。

## 2. 一句话定义

把用户分散的文件、网页、笔记和外部信息，转化为一个持续更新、能够追溯证据、能够发现关系并推动实际工作的个人知识系统。

## 3. 完整闭环

```text
信息进入
-> 解析与标准化
-> 去重和版本识别
-> 知识结构化
-> 混合检索
-> 基于证据的分析
-> 生成工作产物
-> 请求用户审批
-> 执行现实动作
-> 新信息进入后持续更新
```

核心价值：

> 知识不是只被存储，而是进入一条能够持续研究、判断、产出和行动的工作流。

## 4. 非目标

本产品不是：

- 普通 RAG 聊天机器人；
- 单纯文件问答系统；
- DeerFlow Memory 的加强版；
- 笔记编辑器；
- 没有边界的通用个人助手；
- 不经用户审批就自动执行外部写操作的自主 Agent。

## 5. 当前 DeerFlow 能力与新增能力边界

当前 DeerFlow 已有能力：

- Gateway embedded runtime，入口为 `backend/app/gateway/app.py`；
- Lead Agent 工厂，入口为 `backend/packages/harness/deerflow/agents/lead_agent/agent.py`；
- Tool 聚合，入口为 `backend/packages/harness/deerflow/tools/tools.py`；
- Skill 扫描与加载，入口为 `backend/packages/harness/deerflow/skills/storage/local_skill_storage.py`；
- Custom Subagent 配置，入口为 `backend/packages/harness/deerflow/config/subagents_config.py` 与 `backend/packages/harness/deerflow/subagents/registry.py`；
- 上传与 Artifact，入口为 `backend/app/gateway/routers/uploads.py`、`backend/app/gateway/routers/artifacts.py` 和 `backend/packages/harness/deerflow/uploads/manager.py`；
- 用户隔离文件路径，入口为 `backend/packages/harness/deerflow/config/paths.py`；
- Memory，入口为 `backend/packages/harness/deerflow/agents/memory/`；
- Checkpointer，入口为 `backend/packages/harness/deerflow/runtime/checkpointer/async_provider.py`。

本项目必须新增：

- 权威知识持久化；
- 摄取、解析、去重、版本、Chunk、Entity、Claim、Relation、EvidenceSpan；
- 混合检索和证据上下文包；
- 基于证据的产出验证；
- Workflow、Approval、Action、Audit；
- 持续更新、冲突识别、Artifact 陈旧检测。

DeerFlow Memory 不能作为权威知识库。DeerFlow thread outputs 不能作为权威数据库。

## 6. 六个必须形成的闭环

### 6.1 知识摄取闭环

支持来源：

- PDF
- DOCX
- PPTX
- XLSX
- Markdown
- TXT
- HTML
- 网页 URL
- DeerFlow 上传文件
- 后续通过 MCP 或连接器接入的外部数据源

固定流程：

```text
Source
-> SourceSnapshot
-> DocumentRevision
-> Parsed Content
-> Chunk
-> Index
```

必须支持：

- 来源身份识别；
- 内容指纹；
- 重复检测；
- Snapshot；
- Revision；
- Parser 版本；
- 解析状态；
- 索引状态；
- 新旧版本差异。

结构性问题：

摄取闭环解决的是“同一信息是否已经存在、这次进入的是新来源还是新版本、哪个解析器产生了当前知识”的问题。任何后续分析都必须能追溯到 SourceSnapshot 与 DocumentRevision。

### 6.2 结构化知识闭环

核心对象：

- Chunk
- Entity
- Claim
- Relation
- EvidenceSpan
- Collection / Topic

结构化知识的目的：

- 跨文档关系发现；
- 相同观点聚合；
- 冲突识别；
- 来源追踪；
- 版本更新；
- 精确检索。

Claim 表示某个来源提出的陈述，不代表系统无条件认定它是真理。系统可以基于多个 Claim 做归纳、比较和冲突解释，但必须保留 Claim 与 EvidenceSpan 的证据关系。

### 6.3 检索与分析闭环

最终检索结构固定为：

```text
用户问题
-> Query Understanding
-> Metadata Filtering
-> Keyword Retrieval
-> Vector Retrieval
-> Entity / Claim Retrieval
-> Reciprocal Rank Fusion
-> Parent Context Expansion
-> LLM Reranking
-> Evidence Context Pack
```

术语合同：

- 关键词检索（Keyword Retrieval）：基于词项、短语、全文索引和过滤条件召回候选内容。
- 向量检索（Vector Retrieval）：基于 embedding 相似度召回 Chunk、Entity 或 Claim。
- 混合检索（Hybrid Retrieval）：组合关键词检索、向量检索、元数据过滤和图谱检索。
- 倒数排名融合（Reciprocal Rank Fusion，RRF）：把多个检索器的排序结果融合为统一候选排序。
- 父子索引（Parent-Child Indexing）：用小 Chunk 做召回，用父级上下文扩展为可供分析的证据上下文。
- 重排序（Reranking）：对融合后的候选证据进行二次排序，可由确定性规则或 LLM 参与。
- 证据上下文包（Evidence Context Pack）：提供给分析和写作阶段的证据集合，包含引用来源、EvidenceSpan、版本和限制说明。

### 6.4 基于证据的产出闭环

支持生成：

- Topic Dossier
- Project Context Pack
- Reading Synthesis
- Comparison Report
- Decision Memo
- Meeting Preparation
- Learning Plan
- Task List
- Email Draft
- Calendar Proposal
- Knowledge Update Report

所有产出必须区分：

- 来源支持的事实；
- 跨来源归纳结论；
- Agent 推断；
- 冲突；
- 未解决问题；
- 证据不足内容。

Artifact 不是任意文本输出。Artifact 必须记录生成所依据的 Source、DocumentRevision、Chunk、Claim 和 EvidenceSpan，并可以被后续更新流程标记为 stale。

### 6.5 知识到行动闭环

标准流程：

```text
检索知识
-> 生成分析产物
-> 生成行动草稿
-> 创建 ApprovalRequest
-> 用户审批
-> 执行动作
-> 保存执行结果和审计记录
```

所有外部副作用操作必须经过人在回路审批（Human-in-the-Loop Approval）。

ApprovalRequest 状态机固定为：

```text
DRAFT
-> AWAITING_APPROVAL
-> APPROVED
-> EXECUTING
-> SUCCEEDED / FAILED
```

以及：

```text
AWAITING_APPROVAL
-> REJECTED / CANCELLED
```

服务端必须在 `action_execute` 时再次校验 Approval 状态、权限、风险级别和幂等键。Prompt 中的承诺不能代替服务端校验。

### 6.6 持续更新闭环

固定流程：

```text
计算内容指纹
-> 判断新来源、重复来源或新版本
-> 对比 Revision
-> 找到变化 Chunk
-> 重新处理受影响部分
-> 更新 Entity / Claim / Relation
-> 标记冲突
-> 标记受影响 Artifact 为 stale
-> 生成 Knowledge Update Report
```

必须支持：

- 增量更新（Incremental Update）
- 知识失效（Invalidation）
- 产物陈旧检测（Artifact Staleness Detection）

持续更新闭环保证知识系统不是一次性索引，而是随新信息进入不断维护版本、冲突和产物有效性。

## 7. 权威边界

权威数据必须保存在项目新增的 Knowledge Persistence 中。DeerFlow 上传文件和 outputs 可以保存原始文件、快照文件、解析中间文件和 Artifact 文件，但不能成为唯一事实来源。

任何涉及权限、审批、幂等、Revision 最新性、数据一致性和外部执行结果确认的判断，必须由确定性服务端代码负责，不能交给 LLM 或 Prompt。
