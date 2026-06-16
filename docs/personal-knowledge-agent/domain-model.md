# Personal Knowledge Agent 领域模型合同

## 1. 模型位置

领域模型定义个人知识工作流的权威数据结构。它不复用 DeerFlow Memory 作为知识库，也不把 thread outputs 当数据库。DeerFlow 当前的用户隔离文件系统用于保存文件型内容，PostgreSQL 与 pgvector 保存权威元数据、关系、索引和状态。

每个对象都必须属于一个用户或 workspace 隔离边界。后续实现必须通过 DeerFlow 的 user context、`Paths`、Gateway authz 和 permission checks 访问数据。

## 2. Source

定位：一个规范化的信息来源身份，例如某个上传文件、网页 URL、外部连接器记录或笔记。

核心字段：

```text
- id
- workspace_id
- source_type
- canonical_uri
- title
- author
- published_at
- created_at
- latest_snapshot_id
- status
```

关系：Source 拥有多个 SourceSnapshot 和 DocumentRevision；`latest_snapshot_id` 指向当前最新快照。

生命周期：创建于首次摄取；重复来源进入去重流程；新版本进入 Snapshot 和 Revision 流程；废弃来源只能被标记状态，物理删除必须受权限和审计约束。

不变量：同一 workspace 内 `source_type + canonical_uri` 应可用于来源身份归一；Source 不保存完整内容。

权威数据边界：PostgreSQL 保存 Source 元数据；原始内容保存在 DeerFlow 用户隔离文件系统或外部 connector。

## 3. SourceSnapshot

定位：某个 Source 在某一时间捕获到的原始内容快照。

核心字段：

```text
- id
- source_id
- content_hash
- storage_path
- captured_at
- metadata
- parser_version
```

关系：属于 Source；可生成一个或多个 DocumentRevision；`storage_path` 指向用户隔离文件系统中的快照文件。

生命周期：每次摄取后计算 hash；重复 hash 可复用或标记重复；新 hash 产生新 snapshot。

不变量：`content_hash` 由确定性代码计算；LLM 不得判断两个 snapshot 是否相同。

权威数据边界：PostgreSQL 保存 hash 和路径；文件系统保存快照内容。

## 4. DocumentRevision

定位：SourceSnapshot 经解析和标准化后形成的可索引文档版本。

核心字段：

```text
- id
- source_id
- snapshot_id
- revision_number
- previous_revision_id
- content_hash
- parse_status
- index_status
- created_at
```

关系：属于 Source 和 SourceSnapshot；拥有 Chunk；可被 Artifact、WorkflowRun、ConflictGroup 引用。

生命周期：Snapshot 被解析后创建；解析失败更新 `parse_status`；索引完成更新 `index_status`；新版本通过 `previous_revision_id` 串联。

不变量：`revision_number` 在同一 Source 内单调递增；最新版本由确定性代码维护。

权威数据边界：PostgreSQL 保存 Revision 状态和关系；解析中间文件保存在用户隔离文件系统。

## 5. Chunk

定位：DocumentRevision 的可检索文本单元，支持父子索引（Parent-Child Indexing）。

核心字段：

```text
- id
- revision_id
- parent_chunk_id
- chunk_index
- content
- token_count
- page_number
- section_path
- start_offset
- end_offset
- embedding
```

关系：属于 DocumentRevision；可有父 Chunk；被 EvidenceSpan 引用；embedding 存入 pgvector。

生命周期：Revision 解析成功后由确定性 chunker 创建；Revision 更新时受影响 Chunk 被重新生成或失效。

不变量：offset 必须对应 Revision 解析内容；`chunk_index` 在 revision 内稳定排序；embedding 可重算但不能改变 Chunk 身份语义。

权威数据边界：PostgreSQL 保存 metadata 和 content；pgvector 保存 embedding；全文索引用于 Keyword Retrieval。

## 6. Entity

定位：跨文档归一化实体，例如人物、组织、项目、概念、地点或产品。

核心字段：

```text
- id
- workspace_id
- canonical_name
- entity_type
- aliases
- description
- embedding
```

关系：可参与 Relation；可与 Claim 的 subject/object 对齐；可被 Collection / Topic 收纳。

生命周期：可由 LLM 提取候选，由确定性代码做 schema 校验、去重和合并；用户或后续流程可修正 aliases。

不变量：Entity 是归一化对象，不等于某个单一来源中的表述；合并必须可审计。

权威数据边界：PostgreSQL 保存实体字段；pgvector 保存 embedding。

## 7. Claim

定位：某个来源提出的结构化陈述。

核心字段：

```text
- id
- workspace_id
- normalized_subject
- predicate
- normalized_object
- claim_text
- stance
- confidence
- valid_from
- valid_to
- status
```

关系：由 EvidenceSpan 支持；可关联 Entity；可进入 ConflictGroup；可被 Artifact 引用。

生命周期：由 LLM 从 Chunk 中提取候选；确定性代码验证 schema、EvidenceSpan、confidence 范围和状态；随着 Revision 更新可失效或被替换。

不变量：Claim 表示某个来源提出的陈述，不代表系统无条件认定它是真理。任何系统结论必须说明它基于哪些 Claim 和 EvidenceSpan。

权威数据边界：PostgreSQL 保存 Claim；pgvector 保存 Claim embedding。

## 8. EvidenceSpan

定位：Claim 或 Relation 对应的原文证据片段。

核心字段：

```text
- id
- chunk_id
- claim_id
- start_offset
- end_offset
- quoted_text
- page_number
```

关系：属于 Chunk；支持 Claim；可支持 Relation；ArtifactEvidenceLink 引用它建立产物证据链。

生命周期：随 Claim/Relation 提取创建；Chunk 变化时需要重新验证 offset；无效证据进入 invalidation。

不变量：`quoted_text` 必须与 Chunk content 的 offset 范围一致。Evidence offset validation 必须由确定性代码完成。

权威数据边界：PostgreSQL 保存 EvidenceSpan；原始文本可从 Chunk 与 Revision 追溯。

## 9. Relation

定位：Entity 之间的结构化关系。

核心字段：

```text
- id
- source_entity_id
- relation_type
- target_entity_id
- evidence_span_id
- confidence
```

关系：连接两个 Entity；由 EvidenceSpan 支持；可被 graph retrieval 使用。

生命周期：由 LLM 提取候选；确定性代码验证 endpoint、relation_type、evidence_span_id 和 confidence；源证据失效时关系也应失效或降级。

不变量：Relation 不能没有证据；不能跨越 workspace 隔离。

权威数据边界：PostgreSQL 保存关系与证据引用。

## 10. Artifact

定位：基于知识库生成的用户可见产物，例如 Decision Memo、Email Draft、Knowledge Update Report。

核心字段：

```text
- id
- workspace_id
- artifact_type
- title
- storage_path
- generated_from_revision
- validation_status
- staleness_status
- created_at
```

关系：通过 ArtifactEvidenceLink 连接 EvidenceSpan、Claim、Revision；可作为 WorkflowRun 的结果。

生命周期：生成后必须验证 provenance；新 Revision 影响证据时标记 stale；用户可查看历史版本。

不变量：Artifact 文件可以存在用户隔离文件系统，但 Artifact metadata 和证据链必须在 PostgreSQL。

权威数据边界：PostgreSQL 保存 metadata、validation、staleness；文件系统保存可展示文件。

## 11. WorkflowRun

定位：一次结构化工作流执行，例如阅读综合、会议准备、邮件草稿生成或行动执行流程。

核心字段：

```text
- id
- workspace_id
- workflow_type
- input
- status
- current_step
- result_artifact_ids
- created_at
- completed_at
```

关系：可生成 Artifact；可创建 ApprovalRequest；可写 AuditLog。

生命周期：创建后按步骤推进；失败必须保存错误；完成后记录结果 artifacts。

不变量：WorkflowRun 的状态推进必须由服务端代码控制，不能由 LLM 自行判定。

权威数据边界：PostgreSQL 保存状态、输入、输出引用和错误。

## 12. ApprovalRequest

定位：外部副作用动作执行前的人在回路审批记录。

核心字段：

```text
- id
- workflow_run_id
- action_type
- action_preview
- risk_level
- status
- requested_at
- decided_at
- decided_by
```

关系：属于 WorkflowRun；批准后可创建 ActionExecution。

生命周期：

```text
DRAFT -> AWAITING_APPROVAL -> APPROVED -> EXECUTING -> SUCCEEDED / FAILED
AWAITING_APPROVAL -> REJECTED / CANCELLED
```

不变量：`action_execute` 必须在服务端再次校验 ApprovalRequest；Prompt 中的“已批准”不构成批准。

权威数据边界：PostgreSQL 保存审批状态和决策人。

## 13. ActionExecution

定位：一次外部 connector 或外部系统写操作的执行记录。

核心字段：

```text
- id
- approval_request_id
- connector_type
- idempotency_key
- request_payload
- result_payload
- status
- executed_at
```

关系：属于 ApprovalRequest；产生 AuditLog；可回写 WorkflowRun 状态。

生命周期：只有 ApprovalRequest 合法批准后才能创建；执行成功或失败都必须保存结果。

不变量：所有外部副作用操作必须有 idempotency key；执行结果必须由 connector 返回确认，不能由 LLM 声称成功。

权威数据边界：PostgreSQL 保存请求、结果、状态和幂等键。

## 14. 补充对象

### Collection / Topic

定位：用户或系统组织知识的集合或主题。

核心字段建议：`id`、`workspace_id`、`name`、`description`、`parent_id`、`created_at`、`updated_at`。

关系：可包含 Source、Chunk、Entity、Claim、Artifact。

补充原因：支持项目级知识组织和跨文档主题视图。

### IngestionJob

定位：一次摄取任务。

核心字段建议：`id`、`workspace_id`、`source_input`、`status`、`error`、`created_at`、`completed_at`。

关系：创建 Source、SourceSnapshot、DocumentRevision。

补充原因：摄取可能异步执行，需要可查询状态与错误。

### ExtractionRun

定位：一次结构化知识抽取任务。

核心字段建议：`id`、`revision_id`、`model_name`、`prompt_version`、`status`、`error`、`created_at`、`completed_at`。

关系：产出 Entity、Claim、Relation、EvidenceSpan。

补充原因：LLM 抽取必须可复现、可审计、可重跑。

### IndexingRun

定位：一次索引构建或重建任务。

核心字段建议：`id`、`revision_id`、`index_type`、`status`、`error`、`created_at`、`completed_at`。

关系：更新 Chunk embedding、全文索引、Entity/Claim embedding。

补充原因：索引状态必须独立于解析状态。

### ArtifactEvidenceLink

定位：Artifact 与证据之间的显式链接。

核心字段建议：`id`、`artifact_id`、`evidence_span_id`、`claim_id`、`usage_type`、`created_at`。

关系：连接 Artifact、EvidenceSpan、Claim。

补充原因：支持 provenance validation 和 Artifact Staleness Detection。

### ConflictGroup

定位：互相冲突或存在张力的一组 Claim。

核心字段建议：`id`、`workspace_id`、`topic`、`status`、`summary`、`created_at`、`updated_at`。

关系：包含多个 Claim，可关联 Entity 和 Artifact。

补充原因：支持冲突识别、冲突解释和更新报告。

### AuditLog

定位：关键状态变化和外部动作的审计记录。

核心字段建议：`id`、`workspace_id`、`actor_id`、`event_type`、`target_type`、`target_id`、`payload`、`created_at`。

关系：可关联 WorkflowRun、ApprovalRequest、ActionExecution、Source 或 Artifact。

补充原因：权限、审批、执行和数据变更必须可追溯。
