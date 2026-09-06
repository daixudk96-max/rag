# Provenance-Centric Multi-View RAG

## What This Is

一个面向长文档与复杂知识问答的多视图 RAG 内核。系统对原始文档只做一次结构化解析，生成稳定的 `canonical spans`，再派生出 Keyword、Vector、Tree、Graph Evidence 四种检索视图，并通过统一的身份层、版本层、证据层保持长期可追溯和可更新。

v1 收缩版只交付可运行 PoC：PostgreSQL registry + canonical spans + Keyword path + Vector path + 统一 query 入口。

## Core Value

不管切片策略、向量表示或图谱抽取怎么变化，系统都能稳定回到原文证据位置，并且能够安全做版本化更新而不打断检索链路。

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] 只解析一次原文，生成稳定 `canonical spans`
- [ ] 建立 PostgreSQL registry / mapping / provenance / versioning 主干
- [ ] 支持 Keyword path（精确术语检索）
- [ ] 支持 Vector path（轻量语义检索）
- [ ] 提供统一 query 入口并返回结构化证据

### Out of Scope

- 独立 Neo4j 图层 — v1 不引入，避免过度设计
- 独立 Milvus/Qdrant 向量库 — v1 先用 PostgreSQL + pgvector 验证主干
- Deep Hybrid 主链 — 后置到 v2
- HitDistributionAnalyzer / Expansion Policy — 后置到 v2
- 独立 reranker — 后置到 v2
- 复杂 entity alias resolution — 后置到 v2

## Context

当前目录已经完成多轮研究和路线图收敛，关键结论如下：
- 统一的不是 chunk，而是 `doc_id / version_id / span_id`
- PostgreSQL 适合作为 source of truth
- Keyword path 应作为独立能力存在，不能只靠向量检索
- v1 应收缩为最小可运行 PoC，先验证 provenance 主干

现有参考文档包括：
- `plans/provenance-centric-multi-view-rag-roadmap.md`
- `plans/phase-1-v1-poc-plan.md`
- `storage-schema-draft.md`
- `storage-alignment-and-update-strategy.md`
- `system-setup-flow.md`

## Constraints

- **Architecture**: v1 必须收缩，不允许一次性引入四层重系统
- **Storage**: v1 只允许 PostgreSQL 作为唯一数据库事实层与检索底座
- **Parsing**: 原文只允许一次解析，必须基于统一的 normalization contract
- **Identity**: 禁止把 `chunk_id` 当全局主身份
- **Updates**: 版本化写入，不允许原地覆盖旧数据

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 统一 `span_id`，不统一 chunk | 切片策略可以变化，但证据坐标必须稳定 | ✓ Good |
| PostgreSQL 先做 source of truth | 先验证主干逻辑，避免多库同步复杂度 | ✓ Good |
| v1 只做 Keyword + Vector | 足够验证主干，又不过度设计 | ✓ Good |
| Deep Hybrid 后置 | 复杂度最高，等主干跑通后再引入 | ✓ Good |
| Docling 作为解析器 | 结构元数据保留最强，且已验证适配性 | ✓ Good |

## Evolution

在进入 Phase 1 实施前，必须冻结：
- identity contract
- normalization contract
- entity canonicalization 最小规则

后续每次阶段切换都要检查：
1. `What This Is` 是否仍准确
2. Active requirements 是否需要调整
3. 新决策是否要写入 Key Decisions
4. Out of Scope 是否需要补充

---
*Last updated: 2026-05-11 after AUTOD phase-1 planning initialization*