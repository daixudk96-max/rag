# LightRAG 1.5.6 源码核查 — 侦查员报告独立验证 (2026-09-01)

## 0. 结论与更正声明
- **侦查员 (daa581e6) 报告经协调者全量独立核验, 全部属实, 行号逐一精确。**
- **更正**: 会话中一度判定其行号'疑似幻觉', 实为协调者验证工具 (tools.read) 对大文件**静默截断** (lightrag.py 实际 5979 行, 截断后只见 1234 行) 所致。误判已撤回; 本文档以 pwsh Get-Content 实测行号为准。
- 核验方法: pwsh Select-String 全包 grep (144 hits) + Get-Content 逐段读真实函数体 + METADATA 解析。解压根: .tmp/lightrag/extracted/lightrag/。

## 1. 逐项核验表 (侦查员 claim → 实测)
| Claim | 实测 | 判定 |
|---|---|---|
| ainsert_custom_kg lightrag.py:3237, 签名 (custom_kg: dict, full_doc_id: str=None) | :3237 `async def ainsert_custom_kg(self, custom_kg: dict[str, Any], full_doc_id: str = None)` | ✅ |
| 灌图零 LLM | :3237-3620 函数体内 llm_model_func/use_llm_func/_use_llm/llm_response/chat_func = **0 命中** | ✅ |
| 实体必填 entity_name (预归一) | :3265 `_normalize_custom_kg_entity_name` → :3268 `normalize_entity_name(value)`, entities[] 逐项归一 | ✅ |
| 关系必填 src_id/tgt_id (+description/keywords 传入) | :3291 relationships[] 循环, src_id/tgt_id 强制 normalize | ✅ |
| chunks 必填 content+source_id; 边带 chunk 来源 | :3321 chunks[] 循环: content sanitize + source_id 必取; :3347 chunk_to_source_map[source_id]=chunk_id; full_doc_id 缺省=source_id | ✅ |
| amerge_entities lightrag.py:6489; _merge_entities_impl utils_graph.py:1343-1845 | :6489 `async def amerge_entities` (source_entities, target_entity, merge_strategy dict[str,str]: concatenate/keep_last/join_unique + override kwargs) → utils_graph.py:1848 amerge_entities / :1343 _merge_entities_impl | ✅ |
| REST POST /graph/entities/merge | api/routers/graph_routes.py:675 `@router.post("/graph/entities/merge", dependencies=[Depends(combined_auth)])` | ✅ |
| ingestion 合并 key=normalize_entity_name, 保留大小写 | utils.py:4697 `def normalize_entity_name(input_text: str) -> str` (via normalize_extracted_info: 去内引号/HTML/中文符号→英文/中英文间空格/中文破折号→英文/首尾引号/短数字过滤); 未见 upper() | ✅ |
| hl/ll_keywords 预供短路 operate.py:4437-4438; LLM 点 :4618 附近 | :4437-4438 `if query_param.hl_keywords or query_param.ll_keywords: return ...`; else :4441 `extract_keywords_only` | ✅ |
| get_knowledge_graph lightrag.py:1697, (node_label, max_depth=3, max_nodes=None), 零 LLM | :1697-1722 逐字一致 (max_nodes 上限 self.max_graph_nodes) | ✅ |
| only_chunk_search 不存在 | 全包 grep 0 hits | ✅ |
| PGTableGraphStorage pgtable_impl.py:267 纯 SQL; 表 nodes/edges workspace 进 PK | :267 class; :80/:89 CREATE TABLE lightrag_graph_nodes/lightrag_graph_edges; PK(workspace,namespace,id) / PK(workspace,namespace,src_id,tgt_id); properties JSONB | ✅ |
| Requires-Python>=3.10; 19 核心依赖无 torch/transformers | METADATA: Requires-Python >=3.10; **base 19 + extras 82 = 101** Requires-Dist; 无 torch/transformers/tensorflow | ✅ |
| PG 依赖在 [offline-storage] extra (asyncpg, pgvector); 驱动 asyncpg | METADATA extras 内含 asyncpg/pgvector (82 extras 条目) | ✅ |

## 2. 核验新增事实 (侦查员报告未覆盖)
- **ainsert_custom_kg 无崩溃恢复保证** (lightrag.py:3247-3256 docstring, issue #3400 Phase 5 direct-writer audit): 此路径 OUTSIDE document-level recovery guarantee, 无 full_entities/full_relations 恢复锚, 中途崩溃可留下 graph/vector/tracking 不一致且 recovery 机制无法发现; 需崩溃恢复应走 ainsert / ainsert_custom_chunks (journal 路径)。调用前有 `await self._raise_if_recovery_required()` (:3259-3260)。
- amerge_entities 策略语义: concatenate (文本字段拼接) / keep_last (取最后非空) / join_unique (分隔符去重合并) + kwargs 直接覆写 (如 {"description": ..., "entity_type": ...})。
- 文件真实行数: lightrag.py 5979 / operate.py 5641 / utils_graph.py 1850 / utils.py 5455 / pgtable_impl.py 1453。

## 3. 对 Phase 17 的判定 (核验后维持)
- **判定 A (喂图)**: 可零 LLM 用 ainsert_custom_kg 灌自有图谱。前提: ①VDB upsert 需 embedding 模型 (我们供本地 BGE); ②接受无文档级恢复保证 → 灌库脚本须自建幂等/断点; ③workspace 实例级配置。
- **判定 B (查询)**: naive 模式全程零 LLM; local/global/hybrid/mix 需预供 hl/ll_keywords (operate.py:4437-4438 短路) 或走 aquery_data (强制 only_need_context); get_knowledge_graph / REST graph GET 无条件零 LLM → 我们 BM25+重排管线产出关键词喂入即可零 LLM 检索。
- 存储: PGTableGraphStorage 纯 SQL 表 (无 AGE 扩展) 与项目 PG-only 决策契合; 归一层仍自研 (LightRAG 仅精确同名合并)。

## 4. 工具教训 (重要)
- **tools.read 对大文件静默截断** — 以 read 得到的行数/末行判断文件大小不可靠; 大文件一律 pwsh Get-Content / Select-String 定位+读段, 或先 Measure-Object 取真实行数。
- 本例中该缺陷导致协调者一度误判子代理报告造假; 文件:行号核验必须用不受截断影响的通道。

## 5. 关联
- 决策: 17-DECISION-LIGHTRAG-BACKEND-2026-09-01.md (LightRAG=图+向量一路, BM25+重排融合, 归一自研)。
- 侦查员原报告: .tmp/lightrag/inspection_report.md (101 行)。
- 下一步: Phase 17 规划初稿 (喂图适配器 / 归一层 / BM25 融合 / 查询模式选型)。
## CORRECTION (2026-09-01, W0 89a59fad)

- 本文档前文'疑似幻觉'判定**错误**: 根因 = 协调器 tools.read 对 lightrag.py (6612 行) / utils.py (6380 行) 静默截断 (只读到 ~1234/~1298), 据此的行数比对与整文正则均无效。
- W0 独立复核 + 协调器 pwsh 抽查: 8/8 声称全部 CONFIRMED (行号见主规划 §9)。原侦查报告可信; R1 幻觉风险解除。
