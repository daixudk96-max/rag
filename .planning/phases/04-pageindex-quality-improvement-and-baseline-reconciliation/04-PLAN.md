---
phase: 04-pageindex-quality-improvement-and-baseline-reconciliation
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/ROADMAP.md
  - .planning/STATE.md
  - .planning/workspace-memory.json
  - verification/phase3-real-validation/validation_status.json
  - verification/phase3-real-validation/level_assessment.json
  - verification/phase3-real-validation/FINAL-REPORT.md
  - verification/phase3-real-validation/judgment_completed.csv
  - verification/phase3-real-validation/run_validation.py
  - llamaindex_runtime/tree/reasoning_backend.py
  - llamaindex_runtime/tree/pageindex_adapter.py
  - llamaindex_runtime/client/pageindex_client.py
requirements:
  - P4-QUAL-01
  - P4-QUAL-02
  - P4-QUAL-03
  - P4-QUAL-04
must_haves:
  truths:
    - 项目对当前真实 Level 只有一个权威口径，不再同时存在 Level 2 与 Level 3 双真相。
    - Phase 4 使用的文档域与业务查询域明确匹配，不再用竞品分析文档回答技术系统问题。
    - 真实树结构达到至少 3 层，并能支撑更具体的小节命中。
    - 真实证据链统计可解释且达到既定阈值，重新验证后才能决定是否进入 Level 3/4。
  key_links:
    - from: verification/phase3-real-validation/validation_status.json
      to: .planning/STATE.md
      via: baseline reconciliation
      pattern: Level_2|Level_3|tree_max_level|mapped_chunks
    - from: llamaindex_runtime/tree/reasoning_backend.py
      to: verification/phase3-real-validation/judgment_completed.csv
      via: real retrieval quality rerun
      pattern: retrieve_tree_hits|top1_relevance|stability
    - from: llamaindex_runtime/tree/pageindex_adapter.py
      to: verification/phase3-real-validation/validation_status.json
      via: tree depth and evidence restoration
      pattern: _flatten_embedded_tree|level_no|heading_path
---

<objective>
将项目从“真实质量已验证但未达标”的状态推进到“质量改进可执行”的 Phase 4。该阶段的目标不是新增框架，而是先统一基线，再修复文档/查询错配、树结构深度、证据链完整性，最后在冻结阈值下重新做真实验证。
</objective>

<context>
- Phase 1 已完成技术链修复
- Phase 2 已完成验证框架与阈值冻结
- Phase 3 已完成真实验证，并暴露：当前系统在真实条件下仍未达到 readiness
- 当前 planning 真相与 artifact 真相冲突，需要先统一 authoritative baseline
</context>

<tasks>
<task type="auto">
  <name>WS0: 基线对账与状态统一</name>
  <files>.planning/ROADMAP.md, .planning/STATE.md, .planning/workspace-memory.json, verification/phase3-real-validation/validation_status.json, verification/phase3-real-validation/level_assessment.json, verification/phase3-real-validation/FINAL-REPORT.md</files>
  <action>统一当前项目关于真实质量结果的权威口径。解释并消除 STATE/workspace-memory 与 level_assessment.json 的分歧，明确 Phase 4 规划应以 Level 2 作为保守基线。将 ROADMAP 中的当前活动阶段切换为 Phase 4，并让 STATE 与 workspace-memory 指向同一 focus、同一 blocker 列表、同一下一步。</action>
  <verify>
    <automated>检查 ROADMAP.md、STATE.md、workspace-memory.json 中的当前阶段、Level 基线、下一步描述是否一致</automated>
  </verify>
  <acceptance_criteria>不存在一份文件写 Phase 3 Active、另一份文件写 Phase 3 Complete Level 2、第三份文件又暗示 Level 3 ready 的冲突叙述。</acceptance_criteria>
  <done>形成单一 authoritative baseline，并完成 Phase 4 正式切换。</done>
</task>

<task type="auto">
  <name>WS1: 文档/查询域对齐与树深修复</name>
  <files>verification/phase3-real-validation/run_validation.py, verification/phase3-real-validation/judgment_completed.csv, llamaindex_runtime/tree/reasoning_backend.py, llamaindex_runtime/tree/pageindex_adapter.py, llamaindex_runtime/client/pageindex_client.py</files>
  <action>重新定义 Phase 4 使用的真实验证语料与查询域，使业务查询和文档主题匹配。并行修复树结构深度，使真实导入后的树至少达到 3 层，减少 root/大章节主导 top1 的情况。重点区分 donor 输出、adapter flattening 和 runtime 使用逻辑，不要再把所有问题混成单一“检索差”。</action>
  <verify>
    <automated>重新生成真实验证输入集与树结构状态快照，确认 tree_depth >= 3，且验证文档域与查询域匹配</automated>
  </verify>
  <acceptance_criteria>新的验证对象不再是竞品分析文档去回答技术系统问题；真实树结构可证明达到至少 3 层；top1 命中不再系统性偏向 root 节点。</acceptance_criteria>
  <done>Phase 4 的真实验证输入和树结构基础准备完成。</done>
</task>

<task type="auto">
  <name>WS2: 证据链恢复与真实复验</name>
  <files>verification/phase3-real-validation/validation_status.json, verification/phase3-real-validation/level_assessment.json, verification/phase3-real-validation/judgment_completed.csv, verification/phase3-real-validation/FINAL-REPORT.md, llamaindex_runtime/tree/reasoning_backend.py, llamaindex_runtime/tree/pageindex_adapter.py</files>
  <action>恢复真实 chunk / mapping / heading_path 统计口径，使 validation_status 能反映真实 ingestion 与 provenance 状态；然后沿用 Phase 2 冻结阈值和人工 judgment 流程重新做真实质量验证，输出新的 level_assessment 与最终 go/no-go closeout 结论。</action>
  <verify>
    <automated>重新生成 validation_status、judgment_completed、level_assessment，并核对 frozen thresholds 的判定逻辑未被放松</automated>
  </verify>
  <acceptance_criteria>validation_status 中的 chunks、mapped_chunks、tree_max_level、heading_path_rate 等字段均为可解释真实值；最终 Level 判断与人工 judgment 一致，且只能在所有 frozen thresholds 通过时判定为 Level 4。</acceptance_criteria>
  <done>Phase 4 真实复验完成，项目获得新的 authoritative readiness judgment。</done>
</task>
</tasks>

<verification>
- ROADMAP / STATE / workspace-memory 的当前阶段与 Level 描述一致
- 重新定义后的验证对象与查询域一致
- tree_depth >= 3
- validation_status 不再出现 chunks=0、mapped_chunks=0 这类空快照
- 新的 level_assessment 严格沿用 Phase 2 冻结阈值
</verification>

<success_criteria>
- Phase 4 被 Prime 正式识别并成为当前活动阶段
- authoritative baseline 完成统一
- 验证对象与查询域对齐
- 真实树结构达到至少 3 层
- 证据链统计恢复到可用口径
- 完成一次新的真实质量复验并给出 Level 结论
</success_criteria>

<output>
After completion, create `E:/github/rag/.planning/phases/04-pageindex-quality-improvement-and-baseline-reconciliation/04-SUMMARY.md`
</output>
