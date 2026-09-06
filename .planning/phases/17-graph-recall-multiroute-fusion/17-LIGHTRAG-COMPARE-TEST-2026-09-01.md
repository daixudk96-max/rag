# LightRAG 双路线实测对比 — 沙盒实验存档 (2026-09-01)

## 测试设计
- 同 6 句语料 (T1-T6) 入库、同 6 问查询; lightrag-hku 1.5.6, 本地隔离 venv .tmp/lightrag-venv; repo 零修改 (只写 .tmp/lightrag_compare/)。
- Path A (原版默认): ainsort 走 LLM 抽实体关系 (entity<|#|> 文本协议) + 查询 LLM 挑词; '教授'=本地 PP-UIE-0.5B 常驻服务 (CPU, 不联网, 无 API key)。
- Path B (我们): UIE 已有抽取 (.tmp/wire/uie_mentions.json) + 同句共现边 + 同名同类型归并 → ainsert_custom_kg; 查询 jieba+子串确定性挑词 → QueryParam(hl/ll_keywords) 纸条; 全程 0 次 LLM。
- 共用确定性字符 n-gram 哈希嵌入 (128 维, 无模型无网络) — 设计修正: 初版 md5 随机向量会使两路检索均成噪声, 经 runner 侦查后批准替换 (coordinator 批示 5cb4ab0d)。

## 实测结果 (协调者独立复核: 直接解析两路 graphml + results.json 逐字段核对, 与 runner 报告一致)
| 路线 | 建库 | 查询 | LLM 调用 | 实体 P/R | 关系 P/R | 6 问命中 |
|---|---|---|---|---|---|---|
| A 原版 (LLM) | 1239.54s, 18 次 LLM | 639.66s (每问 ~106s) | 18 | 0/0 | 0/0 | 0/6 |
| B 我们 (零 LLM) | 0.03s | 0.02s | 0 | 1.0/1.0 (11 实体) | 1.0 (13 边) | 6/6 |
- Path A 图文件实测 0 nodes/0 edges (空图); 18 次 LLM 调用全部返回成功但输出不遵循 entity<|#|>name<|#|>type<|#|>desc 协议 → 解析 0 实体; 关键词 JSON 修复失败触发原版兜底 'Forced low_level_keywords to origin query', 空图下仍无结果。
- Path B graphml 实测 11 节点/13 边, 实体名逐字匹配 gold: Mate60, 上海, 北京, 华为, 小米, 手机, 李雷, 杭州, 比亚迪, 王小明, 韩梅梅。

## 诚实边界 (三条, 全部写入报告)
1. Path A 教授为 0.5B 客串 = 最弱教授下界; GPT 级教授建图会更好, 但需 API key+联网+按次付费; 本测考的是路线结构而非教授上限。
2. 嵌入为确定性哈希假向量 (两路同函数, 公平); 语义泛化不可考, 生产换 BGE。
3. Path A 失败根因 = 0.5B 输出格式 vs LightRAG 文本解析协议不匹配, 非环境故障。

## 对 Phase 17 的意义
- 验证既定架构: LightRAG 作图仓库 (ainsert_custom_kg 零 LLM 灌入) + 我们的专用小模型/规则产料 + BM25/切词产关键词走 hl/ll_keywords 纸条 = 可行且全面占优 (质量/速度/成本/可复现)。
- 工程坑 (Phase 17 PLAN 需吸收): ①必须 await rag.initialize_storages(); ②tiktoken 首用联网 → import 前 monkeypatch (离线部署关键); ③本地小模型 CPU 单次 ~100s, 并发须 llm_model_max_async=1+长超时 (若未来授权真 LLM); ④子进程管道 UTF-8 用 stdout.buffer 字节写。

## 产物
- runner 交付: .tmp/lightrag_compare/{report.md, results.json, path_a_stage.json, path_b_stage.json, path_a_run.log, path_b_run.log} + .tmp/lightrag-venv。
- runner: lightrag-compare-runner (13a8ea0d-84fc-45df-a1ab-d94abddf53a6); 协调者独立核验 2026-09-01 (graphml 解析 + results.json 全字段) 通过。

## Round 2 (2026-09-01, 用户裁决重赛): 教授 = Claude 子代理 (文件队列, 零联网零 API)
- 用户判定 Round 1 对原版不公 (0.5B 最弱教授下界, 不能代表原版); Round 2 重赛 Path A, 教授=子代理本人按文件队列实时作答 (queue/ 18 组 pending→responses→done 审计), gleaning 关闭 (18 调用封顶), 全新 path_a2_ws。
- 实测 (协调者独立复核: path_a2_ws graphml 直读 + results_round2.json 逐字段 + hit 字段逐条): A-Claude = 11 实体 P=R=1.0 (graphml 实体名与 gold 逐字一致), 10 条语义关系 P=1.0 R=0.769 (10/13, 缺 3 条无直接语义陈述的共现边), 6/6 全中; 建库 111.03s, 查询 231.82s (含教授轮询 ~12s/调用), LLM 调用 18 次 0 失败。
- 三行终表: A-0.5B (0 实体 / 0/6 / 建库 1239.5s / 查询 639.7s) | A-Claude (11 实体 / 10 语义关系 / 6/6 / 111s / 232s) | B-我们 (11 实体 / 13 共现边 / 6/6 / 0.03s / 0.02s / 0 次 LLM)。
- 判定: 教授质量 = 原版路线胜负手 (Round 1 的 0/6 是教授太弱, 非路线不可用); 原版+好教授质量可打平且语义关系更优, 但每问必请教授 (慢 ~4 个数量级 + 按次费 + 结果随教授变化); 我们的零 LLM 路线在成本/速度/确定性全面占优, 关系语义深度可由 UIE 关系抽取模式补足 (先前 UIE 评测已证: 张三→所属公司→腾讯公司), 无需教授。
- 事故记录: attempt-1 字节级 tiktoken stub 与 _prefix_span_via_boundary 不兼容 (中文 3 字节/char → IndexError), doc4/6 合并失败丢 3 关系; 修 per-char token 后全新重跑; 事故期 Q4 曾诚实回答'上下文无打电话信息'。
- 诚实偏置声明: 教授=Claude 子代理, 与出题/判卷同源 (自我一致性偏置); 嵌入仍为 n-gram 哈希假向量 (两路同函数); 查询/建库时长含教授轮询, 引擎本身毫秒级。
- 工程坑 (Phase 17 PLAN 吸收): initialize_storages 必须 await; tiktoken stub 必须 per-char (字节级触发 _prefix_span_via_boundary IndexError); Start-Job 随父 pwsh 退出被杀→Start-Process cmd /c 分离; tools.write 拒写已删路径→[IO.File]::WriteAllText 无 BOM UTF8。
- 审计: queue/ 18 对应; path_a2_run.log 非 UTF-8 (工具拒读, 知情); repo 零修改, 全部产物 .tmp/lightrag_compare/。

## Round 3 (2026-09-01): B2 = UIE 关系模式建图 (schema 先锁定)
- 用户追问 Path B 之前只用了 UIE 实体模式 → Round 3 让 UIE 关系模式上场。schema 跑前锁定 8 项: 所在地/所属公司/任职于/发布/总部位于/使用/通话/前往 (flat 8 + 按主语类型门控, 写死 b2_extract.py); gold=7 条手工语义关系, 同一把尺 (只扫边 keywords 关系标签字段; 因'在'字子串假阳性收紧过尺子)。
- 协调者独立核验 (path_b2_ws graphml 直读 11 nodes/14 edges + report_round3.md 88 行): **B2 = 14 语义边, 7/7 gold 全召回 (R=1.0), P=0.5 (7 条噪声幻觉: 华为→总部位于→北京[错,应杭州]、华为→发布→李雷、通话反向边、T5 一对堆 4 关系等, verbatim 落盘 uie_noise); 建库 0.04s + 6 问 0.06s, 0 LLM / 42 UIE (加载 57.6s + 抽取 264.9s, 零 API), 6/6 命中**。
- 终局四行表 (同一把尺): A-0.5B (0 边/0-6) | A-Claude (10 边, P=0.7 R=1.0, 6/6, 111s+232s, 18 LLM) | B1 共现 (13 边, typed P=0, pair 7/13, 6/6, 0.03s+0.02s) | B2 UIE (14 边, P=0.5 R=1.0, 6/6, 0.04s+0.06s, 0 LLM)。
- 判定: ①单子方法成立 — 8 项菜单把 7 gold 全召回, 印证'维护量=业务问题种类'论证; ②B2 与 A-Claude 都有噪声 (P=0.5 vs 0.7), 差异不悬殊; 噪声清除走'证据回核对+复核篮子'(每条关系带出处句, 华为总部位于北京 与原文 T6 矛盾可直接杀) — 正是归一研究 REVIEW 出口设计; ③成本/速度/确定性 B 路线全面占优 (快 4 个数量级, 零 API)。
- 产物: .tmp/lightrag_compare/{report_round3.md(88行), results_round3.json, path_b2_stage.json(graphml 11/14), uie_relations.json(42 次原始输出), b2_extract.py, path_b2.py, report_round3.py}。runner: 13a8ea0d 三轮完成, 已 finished。
