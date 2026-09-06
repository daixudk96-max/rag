# Phase 17 任务板 (轻量, 代替 trellis 面板 — 面板被 allowlist 挡, 用户可在 Web 设置加 E:/github/rag 后迁移)

主规划: 17-PLAN-MASTER-2026-09-01.md | 更新: 2026-09-02 | W0-W3 DONE (W3 修复轮 73 passed 复验过); W4a DONE (2026-09-01); D2 v2 量化覆盖门 0.90 (主规划 §11/§14); W4b DONE (2026-09-01, 55 tests 复验过); W5a DONE (2026-09-02, 116 tests 复验过); W5b DONE (2026-09-02, 修复轮 252 focused 复验过); W6 DONE; W6.5 DONE (2026-09-02, 修复轮 74 focused 复验过, 组合 1405/3/1); W7 DONE (2026-09-03, 评审修复轮 28 focused 复验过, 组合 1433/3/1); W7-LIVE DONE; FIX-17 DONE (2026-09-03, ingest_entities 8 真实入库 + F2 失败写证据, focused 97/组合 1502/3 既有/okf 5 既有, live 重跑 gate exit 0 + demo RC 0, LLM 临时 deepseek-v4-flash) (2026-09-03, 真实 live gate exit 0 + demo RC 0, 4 路终审 0C/0H); W5 债务波: W5a DONE (2026-09-04, focused 97 复验过) + W5b DONE (2026-09-04, 4 路评审 + 修复轮 108 focused 复验过, 组合 3/1513/1) + W5c DONE (2026-09-04, RED 9→GREEN 114 复验过, 组合 3/1519/1) — W5 债务波全波关闭; W8/VER DONE (2026-09-04, 验证编排器 run_phase17_verification.py verified 9/0, focused 136 复验过, 组合 3/1541/1)

| Wave | 内容 | 状态 | 执行者 |
|---|---|---|---|
| W0 | LightRAG API 只读复核 (反幻觉) | DONE 8/8 CONFIRMED | lightrag-api-verify (89a59fad-8e83-4378-ad3c-231e7908e06e) |
| W1 | lightrag wheelhouse+hash lock 备料 | DONE 79whl/75.95MiB lock=dbd4c8b7 | lightrag-wheelhouse-prep (a9583fab-dabe-46ab-96ad-b70f2b8adec9) |
| W2 | UIE→MentionCandidate 适配器+批量抽取器 (TDD) | DONE 修复轮 36 passed 复验过 | uie-adapter-tdd (5ab90766-953a-44fc-8970-771274bfeab3) |
| W3 | 试抽分流器 (TDD, 细案 §14) | DONE 修复轮 73 passed 复验过 | extraction-trial-router-tdd (2df17afe-6e78-4b1d-bb5a-6bd48953b4de) |
| W4 | 归一 v1 (TDD, W4a+W4b, 主规划 §16/§17/§18) | DONE (2026-09-01) W4a 112 tests + W4b 55 tests 复验过 | entity-identity-v1-tdd + w4b-fuzzy-recall-transcriber |
| W5 | 复核篮子 (TDD; W5a 归一复核篮 + W5b 关系核对篮) | DONE (2026-09-02) W5a 116 tests + W5b 136 tests (修复轮后 252 focused 复验过) | basket-transcriber (353abcf4, 7df7898f) |
| W6 | LightRAG 集成+BM25 融合 (TDD) | DONE (2026-09-02) wave-1 15 tests + wave-2 9 tests + fix-round 15 tests = focused 39 复验过; 组合 1331/3/1 | graph-transcriber (f9e62316) |
| W6.5 | LLM 适配器 (TDD; TrialEngine + ReviewerEngine 双插座, 主规划 §22 R3) | DONE (2026-09-02) 初版 69 tests + 修复轮 4M 全修 = focused 74 复验过; 组合 1405/3/1; 子包 llm_openai 避开既有 llm 包 eager import; W6.5-R 拆分传输/适配器三分 (74 复验过) | llm-adapter-transcriber (f9e62316→中断, d96ceb3e) |
| W7 | disposable PG 验收门+端到端 demo | DONE (2026-09-03) wave-1 12 + wave-2 11 + 修复轮 5 = focused 28 复验过; 组合 1433/3/1 | graph-transcriber (c9077a5e) + 协调器备稿 |
| W7-LIVE | 真实 live 验收门+demo (PG 容器 + 真实 LLM + DashScope + LightRAG PG 后端; FIX-1..16 适配 LightRAG 1.5.6 真实 API) | DONE (2026-09-03) 正式门 evidence=20a4de97 (executed, recall 3, fusion 0.0167); demo report=9ea91f0d (RC 0, 两 batch executed); 4 路终审 0C/0H | 实现者 9ee90670 + 协调器路由 |
| W5a/FIX | follow-up 债务波 a: F3 桥接去重 (live_bridge.py 单源 8 符号) + F9 超时对称 + F10 语言杂项 + fusion F401 | DONE (2026-09-04) focused 97 复验过; 组合 3/1502/1; 零测试编辑 | transcriber (7023e83d) |
| W5b/FIX | follow-up 债务波 b: F5 批级 digest 内容作用域文档 id + F7 expected-DB 等值+三门 parity + F8 workdir/model dir 绝对路径校验 + F13 docstring; 评审修复轮: pathlib 换防 (3.11 根相对 LEGACY 窗口关闭) + UUID.version==5 + skip 负向断言 | DONE (2026-09-04) focused 105→修复轮 108 复验过; 组合 3/1513/1; 4 路评审 0C/1M (M 前提修正, hardening applied) | transcriber (7023e83d) |
| W5c | follow-up 债务波 c: F4a demo 非逐字实体 skip-and-record ((bundle, skipped) tuple + BatchOutcome.skipped_entities + 报告行) + F4b prompt JSON 示例 _LLM_IE_EXAMPLE (valid JSON) + F6 runner evidence invariants recall_ge_1 (19→20 键) | DONE (2026-09-04) RED 9 verbatim→GREEN 114 复验过; 组合 3/1519/1 | transcriber (7023e83d) |
| W8/VER | Phase 17 验证编排器 (16-18 模式): run_phase17_verification.py 消费盘上证据 (9 检查 fail-closed 聚合: 契约 19 键/状态/exit/recall>=1/ingest>0/route + 7 归档 sha pin) + 22 tests + 17-VERIFICATION.md (五节含显式 non-claims); live selectors gate_rerun/demo_rerun 默认拒绝 | DONE (2026-09-04) RED 19 err verbatim→GREEN 136 复验过; 实跑 verified 9/0; 组合 3/1541/1 | transcriber (7023e83d) |

R3 已定 (主规划 §22): 生产 LLM 引擎 = 商用 API (OpenAI 兼容 chat completions, 本机中转站 127.0.0.1:8317, LLM_MODEL=gpt-5.4-mini); 适配器已交付 = llamaindex_runtime/llm_openai/{client,trial_engine,relation_reviewer}.py (W6.5-R 拆分后) (W6.5)。
